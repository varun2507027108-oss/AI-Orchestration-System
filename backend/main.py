import sys
import os
import uuid
import logging
import asyncio
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import settings
from db import init_db, get_latest_artifact, get_decision_log
from graph import create_graph, init_saver
from tools.pdf_export import export_to_pdf
from tools.notion import create_notion_page, translate_artifact_to_notion_blocks, append_notion_blocks
from langgraph.types import Command

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Request schemas
class CreateSessionRequest(BaseModel):
    startup_name: str
    idea: str
    github_repo: Optional[str] = ""

class GateDecisionRequest(BaseModel):
    decision: str  # "continue" | "revise"
    revised_idea: Optional[str] = None

class ExportRequest(BaseModel):
    target: str  # "pdf" | "notion"

# Active sessions registry to handle race conditions on quick state queries
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}

# Lifespan context manager for LangGraph SqliteSaver checkpointer
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with init_saver("checkpoints.db") as saver:
        app.state.saver = saver
        app.state.graph = create_graph(saver)
        logger.info("LangGraph Saver and compiled state-graph successfully initialized.")
        yield

app = FastAPI(
    title="AI Founder Orchestration System API",
    description="Backend service managing the multi-agent startup validation lifecycle.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS
origins = [o.strip() for o in settings.ALLOWED_ORIGIN.split(",") if o.strip()]
if not origins:
    origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated export files statically
os.makedirs("exports", exist_ok=True)
app.mount("/exports", StaticFiles(directory="exports"), name="exports")

async def run_graph_in_background(graph: Any, initial_state: Dict[str, Any], config: Dict[str, Any]):
    try:
        await graph.ainvoke(initial_state, config=config)
        logger.info(f"Graph execution completed/paused for thread: {config['configurable']['thread_id']}")
    except Exception as e:
        logger.exception(f"Error executing graph in background for thread {config['configurable']['thread_id']}: {e}")

async def resume_graph_in_background(graph: Any, command: Command, config: Dict[str, Any]):
    try:
        await graph.ainvoke(command, config=config)
        logger.info(f"Graph resumed and finished/paused for thread: {config['configurable']['thread_id']}")
    except Exception as e:
        logger.exception(f"Error resuming graph in background for thread {config['configurable']['thread_id']}: {e}")

@app.post("/sessions")
async def create_session(payload: CreateSessionRequest):
    session_id = str(uuid.uuid4())
    logger.info(f"Creating new session: {session_id} for startup: {payload.startup_name}")

    ACTIVE_SESSIONS[session_id] = {
        "startup_name": payload.startup_name,
        "idea": payload.idea,
        "github_repo": payload.github_repo
    }

    initial_state = {
        "session_id": session_id,
        "startup_name": payload.startup_name,
        "idea": payload.idea,
        "github_repo": payload.github_repo,
        "status": "running",
        "stages": {
            "startup_advisor": {"status": "pending", "version": 0},
            "market_research": {"status": "pending", "version": 0},
            "product_manager": {"status": "pending", "version": 0},
            "architect": {"status": "pending", "version": 0},
            "engineering_manager": {"status": "pending", "version": 0},
            "marketing": {"status": "pending", "version": 0}
        }
    }

    config = {"configurable": {"thread_id": session_id}}
    asyncio.create_task(run_graph_in_background(app.state.graph, initial_state, config))

    return {"session_id": session_id}

@app.get("/sessions/{id}")
async def get_session(id: str):
    config = {"configurable": {"thread_id": id}}
    snapshot = await app.state.graph.aget_state(config)
    state_values = snapshot.values or {}
    
    if not state_values:
        details = ACTIVE_SESSIONS.get(id)
        if not details:
            raise HTTPException(status_code=404, detail="Session not found")
        state_values = {
            "session_id": id,
            "startup_name": details["startup_name"],
            "idea": details["idea"],
            "github_repo": details["github_repo"],
            "status": "running",
            "stages": {
                "startup_advisor": {"status": "pending", "version": 0},
                "market_research": {"status": "pending", "version": 0},
                "product_manager": {"status": "pending", "version": 0},
                "architect": {"status": "pending", "version": 0},
                "engineering_manager": {"status": "pending", "version": 0},
                "marketing": {"status": "pending", "version": 0}
            },
            "failed_stages": []
        }
    
    status = state_values.get("status", "running")
    is_interrupted = len(snapshot.tasks) > 0 and any(t.interrupts for t in snapshot.tasks)
    
    gate_payload = None
    if is_interrupted:
        status = "awaiting_gate"
        for task in snapshot.tasks:
            if task.interrupts:
                gate_payload = task.interrupts[0].value
                break
    elif not snapshot.next and status == "running" and snapshot.values:
        status = "complete"

    active_stage = None
    if status == "running":
        stages_dict = state_values.get("stages", {})
        for stage, info in stages_dict.items():
            if info.get("status") == "running":
                active_stage = stage
                break
        if not active_stage and snapshot.next:
            active_stage = snapshot.next[0]

    stages_list = ["startup_advisor", "market_research", "product_manager", "architect", "engineering_manager", "marketing"]
    artifacts_dict = {}
    for s in stages_list:
        art = await asyncio.to_thread(get_latest_artifact, id, s)
        if art:
            artifacts_dict[s] = art

    return {
        "session_id": id,
        "startup_name": state_values.get("startup_name"),
        "idea": state_values.get("idea"),
        "github_repo": state_values.get("github_repo"),
        "status": status,
        "active_stage": active_stage,
        "stages": state_values.get("stages", {}),
        "failed_stages": state_values.get("failed_stages", []),
        "gate": gate_payload,
        "artifacts": artifacts_dict
    }

@app.post("/sessions/{id}/gate-decision")
async def post_gate_decision(id: str, payload: GateDecisionRequest):
    config = {"configurable": {"thread_id": id}}
    snapshot = await app.state.graph.aget_state(config)
    
    if not snapshot.values and id not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    is_interrupted = len(snapshot.tasks) > 0 and any(t.interrupts for t in snapshot.tasks)
    if not is_interrupted:
        raise HTTPException(status_code=400, detail="Session is not currently awaiting a gate decision")

    if payload.decision == "revise" and not payload.revised_idea:
        raise HTTPException(status_code=422, detail="revised_idea is required when decision is 'revise'")

    resume_command = Command(resume={"decision": payload.decision, "revised_idea": payload.revised_idea})
    asyncio.create_task(resume_graph_in_background(app.state.graph, resume_command, config))

    return {"status": "success"}

@app.get("/sessions/{id}/artifacts/{stage}")
async def get_stage_artifact(id: str, stage: str):
    valid_stages = ["startup_advisor", "market_research", "product_manager", "architect", "engineering_manager", "marketing"]
    if stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid stage name. Must be one of {valid_stages}")

    artifact = await asyncio.to_thread(get_latest_artifact, id, stage)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact not found for stage: {stage}")

    return artifact

@app.get("/sessions/{id}/decision-log")
async def get_session_decision_log(id: str):
    logs = await asyncio.to_thread(get_decision_log, id)
    return logs

@app.post("/sessions/{id}/export")
async def export_session(id: str, payload: ExportRequest):
    config = {"configurable": {"thread_id": id}}
    snapshot = await app.state.graph.aget_state(config)
    
    if not snapshot.values and id not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    state_values = snapshot.values
    startup_name = state_values.get("startup_name", "Startup")

    stages_list = ["startup_advisor", "market_research", "product_manager", "architect", "engineering_manager", "marketing"]
    artifacts_dict = {}
    for s in stages_list:
        art = await asyncio.to_thread(get_latest_artifact, id, s)
        if art:
            artifacts_dict[s] = art

    if not artifacts_dict:
        raise HTTPException(status_code=400, detail="No artifacts are generated yet for this session. Cannot export.")

    if payload.target == "pdf":
        try:
            # Wrap synchronous PDF generation in a thread to avoid blocking the event loop
            pdf_path = await asyncio.to_thread(export_to_pdf, startup_name, id, artifacts_dict, output_dir="exports")
            filename = os.path.basename(pdf_path)
            download_url = f"/exports/{filename}"
            return {
                "status": "success",
                "file_path": pdf_path,
                "download_url": download_url
            }
        except Exception as e:
            logger.exception(f"Error generating PDF export: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to generate PDF report: {str(e)}")

    elif payload.target == "notion":
        try:
            page_id = await create_notion_page(startup_name, id)
            if not page_id:
                raise HTTPException(status_code=502, detail="Failed to create parent Notion page. Check NOTION_TOKEN and NOTION_DATABASE_ID configuration.")

            all_blocks = []
            for stage_name in stages_list:
                payload_data = artifacts_dict.get(stage_name)
                if payload_data:
                    blocks = translate_artifact_to_notion_blocks(stage_name, payload_data)
                    all_blocks.extend(blocks)

            if all_blocks:
                success = await append_notion_blocks(page_id, all_blocks)
                if not success:
                    raise HTTPException(status_code=502, detail="Created page, but failed to append content blocks.")

            notion_url = f"https://notion.so/{page_id.replace('-', '')}"
            return {
                "status": "success",
                "notion_url": notion_url
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error exporting to Notion: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to export to Notion: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail="Invalid target. Must be 'pdf' or 'notion'")