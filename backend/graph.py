# AI Founder Orchestration System - LangGraph Workflow
import sys
import os
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from groq import AsyncGroq
import google.generativeai as genai
from openai import AsyncOpenAI

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import settings
from models import (
    GraphState,
    ValidationResult,
    MarketResearchReport,
    PRD,
    ArchitectureSpec,
    IssuesAndSprintPlan,
    MarketingAssets
)
from db import save_artifact, add_decision_log, get_latest_artifact_version, get_latest_artifact, get_decision_log

logger = logging.getLogger(__name__)

# --- LangGraph Helper functions ---

def init_saver(db_path: str = "checkpoints.db") -> AsyncSqliteSaver:
    return AsyncSqliteSaver.from_conn_string(db_path)

def update_stage(stages: Optional[Dict[str, Any]], stage_name: str, status: str, version: int = 0) -> Dict[str, Any]:
    current = dict(stages or {})
    current[stage_name] = {"status": status, "version": version}
    return current

# --- LLM Query Helpers with Exponential Backoff Retry ---

async def call_with_retry(func, *args, **kwargs):
    for attempt in range(3):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed with error: {e}")
            if attempt == 2:
                raise e
            await asyncio.sleep(2 ** attempt)

async def query_groq(system_instruction: str, user_prompt: str, schema: Any, api_key: Optional[str] = None) -> Dict[str, Any]:
    key_to_use = api_key or settings.GROQ_API_KEY
    if not key_to_use:
        raise ValueError("GROQ_API_KEY is not configured.")
    
    client = AsyncGroq(api_key=key_to_use)
    prompt = f"{user_prompt}\n\nReturn a JSON object matching this schema:\n{schema.schema_json()}"
    
    async def _call():
        await asyncio.sleep(1.0)  # Rate limit safety delay
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            temperature=0.1
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        schema(**parsed)  # validate structure
        return parsed
        
    return await call_with_retry(_call)

async def query_gemini(system_instruction: str, user_prompt: str, schema: Any, api_key: Optional[str] = None) -> Dict[str, Any]:
    key_to_use = api_key or settings.GEMINI_API_KEY
    if not key_to_use:
        raise ValueError("GEMINI_API_KEY is not configured.")
    
    genai.configure(api_key=key_to_use)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction
    )
    
    async def _call():
        await asyncio.sleep(1.0)  # Rate limit safety delay
        response = await model.generate_content_async(
            user_prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.1
            )
        )
        content = response.text
        parsed = json.loads(content)
        return parsed
        
    return await call_with_retry(_call)

async def query_nim(system_instruction: str, user_prompt: str, schema: Any, api_key: Optional[str] = None) -> Dict[str, Any]:
    key_to_use = api_key or settings.NVIDIA_NIM_API_KEY
    if not key_to_use:
        raise ValueError("NVIDIA_NIM_API_KEY is not configured.")
        
    client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=key_to_use
    )
    
    prompt = f"{user_prompt}\n\nReturn a JSON object matching this schema:\n{schema.schema_json()}"
    
    async def _call():
        await asyncio.sleep(1.0)  # Rate limit safety delay
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            model="nvidia/llama-3.1-nemotron-70b-instruct",
            response_format={"type": "json_object"},
            temperature=0.1
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        schema(**parsed)
        return parsed
        
    return await call_with_retry(_call)

# --- Node Implementations ---

async def startup_advisor_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["startup_advisor"] = {"status": "running", "version": 0}
    
    # Check if we are resuming from a continue decision
    if state.gate_decision == "continue":
        add_decision_log(state.session_id, "startup_advisor", "Idea approved to continue by founder.")
        return {
            "gate_decision": None,
            "gate_resolved": True,
            "status": "running",
            "stages": {"startup_advisor": {"status": "complete", "version": get_latest_artifact_version(state.session_id, "startup_advisor")}}
        }

    # Determine what idea to validate
    idea_to_validate = state.revised_idea if state.gate_decision == "revise" else state.idea
    
    system_instruction = (
        "You are the Startup Advisor. Your task is to evaluate the founder's startup idea. "
        "Assess the risk level (risk_score between 0.0 and 1.0), verdict (e.g. Approved, Needs Revision), "
        "provide detailed reasoning, and list any red flags. You must return a JSON object matching the ValidationResult schema."
    )
    prompt = f"Evaluate this startup idea: '{idea_to_validate}' for a project named '{state.startup_name}'."
    
    # Check if we already validated this specific idea in a previous execution of this node
    logs = get_decision_log(state.session_id)
    is_resume = any(f"Validated idea '{idea_to_validate}':" in l["reasoning"] for l in logs)
    
    result = None
    version = 0
    
    if is_resume:
        art_data = get_latest_artifact(state.session_id, "startup_advisor")
        if art_data:
            result = ValidationResult(**art_data)
            version = get_latest_artifact_version(state.session_id, "startup_advisor")
        else:
            is_resume = False

    try:
        if not is_resume:
            api_key = settings.ADVISOR_API_KEY or settings.GROQ_API_KEY
            # Check if we are running in dry-run or mock mode (e.g. during skeleton testing or empty key)
            if not api_key:
                is_risky = "risk" in idea_to_validate.lower() or "fail" in idea_to_validate.lower() or "trigger_gate" in idea_to_validate.lower()
                if is_risky:
                    result = ValidationResult(
                        verdict="Needs Revision",
                        risk_score=0.8,
                        reasoning="Startup idea contains high-risk concepts (Mocked).",
                        red_flags=["High risk keywords detected", "Target market competition"]
                    )
                else:
                    result = ValidationResult(
                        verdict="Excellent idea",
                        risk_score=0.2,
                        reasoning="Straightforward business model and target (Mocked).",
                        red_flags=[]
                    )
            else:
                result_dict = await query_groq(system_instruction, prompt, ValidationResult, api_key=api_key)
                result = ValidationResult(**result_dict)
                
            version = save_artifact(state.session_id, "startup_advisor", result.dict())
            add_decision_log(state.session_id, "startup_advisor", f"Validated idea '{idea_to_validate}': Verdict={result.verdict}, Risk={result.risk_score}")
        
        # Check if we need to trigger the gate
        is_high_risk = result.risk_score > 0.6 or len(result.red_flags) > 0
        
        if is_high_risk:
            stages["startup_advisor"] = {"status": "awaiting_gate", "version": version}
            
            user_response = interrupt({
                "risk_score": result.risk_score,
                "red_flags": result.red_flags,
                "verdict": result.verdict,
                "reasoning": result.reasoning
            })
            
            decision = user_response.get("decision")
            revised_idea_val = user_response.get("revised_idea", "")
            
            if decision == "revise":
                add_decision_log(state.session_id, "startup_advisor", f"Founder requested revision with new idea: '{revised_idea_val}'")
                return {
                    "idea": revised_idea_val,
                    "gate_decision": "revise",
                    "revised_idea": revised_idea_val,
                    "startup_advisor": result,
                    "stages": {"startup_advisor": {"status": "running", "version": version}},
                    "status": "running"
                }
            else:
                add_decision_log(state.session_id, "startup_advisor", "Founder chose to continue despite warnings.")
                return {
                    "gate_decision": "continue",
                    "startup_advisor": result,
                    "stages": {"startup_advisor": {"status": "complete", "version": version}},
                    "status": "running"
                }
        else:
            return {
                "startup_advisor": result,
                "gate_decision": None,
                "gate_resolved": True,
                "stages": {"startup_advisor": {"status": "complete", "version": version}},
                "status": "running"
            }
            
    except GraphInterrupt:
        raise
    except Exception as e:
        logger.exception(f"Error in startup_advisor_node: {e}")
        if "startup_advisor" not in failed_stages:
            failed_stages.append("startup_advisor")
        return {
            "stages": {"startup_advisor": {"status": "failed", "version": 0}},
            "failed_stages": failed_stages,
            "status": "failed"
        }

async def market_research_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["market_research"] = {"status": "running", "version": 0}
    
    idea_val = state.idea
    search_results_str = ""
    sources = []
    
    try:
        if settings.TAVILY_API_KEY:
            from tools.tavily import search_tavily
            search_res = await search_tavily(f"competitors and market trends for {idea_val}")
            results = search_res.get("results", [])
            for r in results:
                title = r.get("title", "")
                url = r.get("url", "")
                content = r.get("content", "")
                search_results_str += f"Source: {title} ({url})\nContent: {content}\n\n"
                sources.append(url)
        else:
            search_results_str = "No search results available (Mocked)."
            sources = ["https://tavily.com/mocked"]
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}")
        search_results_str = "No search results available due to API failure."
        sources = ["https://tavily.com/fallback"]
        
    system_instruction = (
        "You are the Market Research Agent. Based on the web search results provided, "
        "estimate the TAM (Total Addressable Market), list top competitors, outline key industry trends, "
        "and list your sources. Every competitor must have a name, description, and source url. "
        "You must output a valid JSON object matching the MarketResearchReport schema."
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nSearch Results:\n{search_results_str}"
    
    try:
        api_key = settings.RESEARCHER_API_KEY or settings.GROQ_API_KEY
        if not api_key:
            report = MarketResearchReport(
                tam_estimate="$500M",
                competitors=[{"name": "Competitor X", "description": "Market incumbent (Mocked)", "url": "https://competitor.com"}],
                trends=["Rising adoption of automation (Mocked)"],
                sources=sources
            )
            report_dict = report.dict()
        else:
            report_dict = await query_groq(system_instruction, prompt, MarketResearchReport, api_key=api_key)
            if not report_dict.get("sources"):
                report_dict["sources"] = sources
            report = MarketResearchReport(**report_dict)
            
        version = save_artifact(state.session_id, "market_research", report_dict)
        add_decision_log(state.session_id, "market_research", "Successfully completed market research report using web search.")
        return {"market_research": report, "stages": {"market_research": {"status": "complete", "version": version}}}
    except Exception as e:
        logger.exception(f"Error in market_research_node: {e}")
        if "market_research" not in failed_stages:
            failed_stages.append("market_research")
        return {"stages": {"market_research": {"status": "failed", "version": 0}}, "failed_stages": failed_stages}

async def product_manager_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["product_manager"] = {"status": "running", "version": 0}
    
    idea_val = state.idea
    market_report = state.market_research
    market_report_str = json.dumps(market_report.dict()) if market_report else "No market report available."
    
    system_instruction = (
        "You are the Product Manager. Your task is to write a PRD based on the startup idea and the market research report. "
        "Include a clear problem statement, user stories, a list of features with priority, and roadmap phases. "
        "You must output a valid JSON object matching the PRD schema."
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nMarket Research Report:\n{market_report_str}"
    
    try:
        api_key = settings.PM_API_KEY or settings.GEMINI_API_KEY
        if not api_key:
            prd = PRD(
                problem_statement=f"Simplify setup for idea: {idea_val} (Mocked)",
                user_stories=["As a founder, I want to review automated market validation report."],
                features=[{"name": "Skeletal Pipeline", "description": "Validates graph state", "priority": "High"}],
                roadmap_phases=[{"name": "Phase 1", "items": ["Skeletal Pipeline"]}]
            )
            prd_dict = prd.dict()
        else:
            prd_dict = await query_gemini(system_instruction, prompt, PRD, api_key=api_key)
            prd = PRD(**prd_dict)
            
        version = save_artifact(state.session_id, "product_manager", prd_dict)
        add_decision_log(state.session_id, "product_manager", "Compiled and generated Product Requirement Document (PRD).")
        return {"product_manager": prd, "stages": {"product_manager": {"status": "complete", "version": version}}}
    except Exception as e:
        logger.exception(f"Error in product_manager_node: {e}")
        if "product_manager" not in failed_stages:
            failed_stages.append("product_manager")
        return {"stages": {"product_manager": {"status": "failed", "version": 0}}, "failed_stages": failed_stages}

async def architect_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["architect"] = {"status": "running", "version": 0}
    
    prd = state.product_manager
    prd_str = json.dumps(prd.dict()) if prd else "No PRD available."
    
    system_instruction = (
        "You are the Software Architect. Create an architecture specification based on the PRD. "
        "Generate the database schema in SQL, the schema in Mermaid syntax, the list of API endpoints (method, path, description), "
        "and system design notes. You must output a valid JSON object matching the ArchitectureSpec schema."
    )
    prompt = f"Product Requirement Document (PRD):\n{prd_str}"
    
    try:
        api_key = settings.ARCHITECT_API_KEY or settings.NVIDIA_NIM_API_KEY
        if not api_key:
            spec = ArchitectureSpec(
                db_schema_sql="CREATE TABLE sessions (id TEXT, idea TEXT);",
                db_schema_mermaid="erDiagram SESSIONS { string id string idea }",
                api_endpoints=[{"method": "POST", "path": "/sessions", "description": "Create session"}],
                system_design_notes="Utilizing SQLite database and FastAPI backend (Mocked)."
            )
            spec_dict = spec.dict()
        else:
            spec_dict = await query_nim(system_instruction, prompt, ArchitectureSpec, api_key=api_key)
            spec = ArchitectureSpec(**spec_dict)
            
        version = save_artifact(state.session_id, "architect", spec_dict)
        add_decision_log(state.session_id, "architect", "Generated database schema SQL and system design specification.")
        return {"architect": spec, "stages": {"architect": {"status": "complete", "version": version}}}
    except Exception as e:
        logger.exception(f"Error in architect_node: {e}")
        if "architect" not in failed_stages:
            failed_stages.append("architect")
        return {"stages": {"architect": {"status": "failed", "version": 0}}, "failed_stages": failed_stages}

async def engineering_manager_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["engineering_manager"] = {"status": "running", "version": 0}
    
    spec = state.architect
    spec_str = json.dumps(spec.dict()) if spec else "No architecture spec available."
    
    system_instruction = (
        "You are the Engineering Manager. Build a sprint plan and list of GitHub issues based on the architecture specification. "
        "Each issue should have a title, body, and labels. Group issues into named sprints. "
        "You must output a valid JSON object matching the IssuesAndSprintPlan schema."
    )
    prompt = f"Architecture Specification:\n{spec_str}"
    
    try:
        api_key = settings.EM_API_KEY or settings.GROQ_API_KEY
        if not api_key:
            plan = IssuesAndSprintPlan(
                issues=[{"title": "Setup SQLite Schema", "body": "Create schemas defined in architecture spec.", "labels": ["db", "setup"]}],
                sprints=[{"name": "Sprint 1", "issue_titles": ["Setup SQLite Schema"]}]
            )
            plan_dict = plan.dict()
        else:
            plan_dict = await query_groq(system_instruction, prompt, IssuesAndSprintPlan, api_key=api_key)
            plan = IssuesAndSprintPlan(**plan_dict)
            
        version = save_artifact(state.session_id, "engineering_manager", plan_dict)
        add_decision_log(state.session_id, "engineering_manager", "Compiled issues backlog and sprint timeline.")
        
        # Trigger GitHub integration if repo is set
        if state.github_repo:
            try:
                from tools.github import create_github_issues_bulk
                await create_github_issues_bulk(state.github_repo, plan.issues)
                add_decision_log(state.session_id, "engineering_manager", f"Successfully synced issues to GitHub repository: {state.github_repo}")
            except Exception as github_err:
                logger.warning(f"Failed to sync issues to GitHub: {github_err}")
                add_decision_log(state.session_id, "engineering_manager", f"Failed to sync issues to GitHub: {github_err}")
                
        return {"engineering_manager": plan, "stages": {"engineering_manager": {"status": "complete", "version": version}}}
    except Exception as e:
        logger.exception(f"Error in engineering_manager_node: {e}")
        if "engineering_manager" not in failed_stages:
            failed_stages.append("engineering_manager")
        return {"stages": {"engineering_manager": {"status": "failed", "version": 0}}, "failed_stages": failed_stages}

async def marketing_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["marketing"] = {"status": "running", "version": 0}
    
    idea_val = state.idea
    prd = state.product_manager
    prd_str = json.dumps(prd.dict()) if prd else "No PRD available."
    
    system_instruction = (
        "You are the Marketing Agent. Generate launch assets based on the startup idea and the PRD. "
        "Create landing page copy, a LinkedIn launch post, and an email campaign copy. "
        "You must output a valid JSON object matching the MarketingAssets schema."
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nProduct Requirement Document (PRD):\n{prd_str}"
    
    try:
        api_key = settings.MARKETING_API_KEY or settings.GROQ_API_KEY
        if not api_key:
            assets = MarketingAssets(
                landing_copy="AI Founder OS: Automate your product validation.",
                linkedin_post="Accelerating startup workflows with AI Founder OS!",
                email_campaign="Introducing automated pipeline for startup validation."
            )
            assets_dict = assets.dict()
        else:
            assets_dict = await query_groq(system_instruction, prompt, MarketingAssets, api_key=api_key)
            assets = MarketingAssets(**assets_dict)
            
        version = save_artifact(state.session_id, "marketing", assets_dict)
        add_decision_log(state.session_id, "marketing", "Generated promotional copy and launch assets.")
        return {"marketing": assets, "stages": {"marketing": {"status": "complete", "version": version}}}
    except Exception as e:
        logger.exception(f"Error in marketing_node: {e}")
        if "marketing" not in failed_stages:
            failed_stages.append("marketing")
        return {"stages": {"marketing": {"status": "failed", "version": 0}}, "failed_stages": failed_stages}

async def join_node(state: GraphState) -> Dict[str, Any]:
    # Marks session complete once both branches join
    return {"status": "complete"}


# --- Conditional Routing ---

def router_after_advisor(state: GraphState) -> str:
    if state.gate_decision == "revise":
        return "startup_advisor"
    return "market_research"


# --- Build StateGraph ---

def create_graph(checkpointer=None):
    workflow = StateGraph(GraphState)
    
    # Add nodes
    workflow.add_node("startup_advisor", startup_advisor_node)
    workflow.add_node("market_research", market_research_node)
    workflow.add_node("product_manager", product_manager_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("engineering_manager", engineering_manager_node)
    workflow.add_node("marketing", marketing_node)
    workflow.add_node("join", join_node)
    
    # Add edges
    workflow.add_edge(START, "startup_advisor")
    
    # Conditional Edge
    workflow.add_conditional_edges(
        "startup_advisor",
        router_after_advisor,
        {
            "startup_advisor": "startup_advisor",
            "market_research": "market_research"
        }
    )
    
    workflow.add_edge("market_research", "product_manager")
    
    # Parallel branching
    workflow.add_edge("product_manager", "architect")
    workflow.add_edge("product_manager", "marketing")
    
    # Architect branch continues to EM
    workflow.add_edge("architect", "engineering_manager")
    
    # Both branches join
    workflow.add_edge("engineering_manager", "join")
    workflow.add_edge("marketing", "join")
    
    workflow.add_edge("join", END)
    
    return workflow.compile(checkpointer=checkpointer)
