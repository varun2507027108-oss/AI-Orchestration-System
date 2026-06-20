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

def safe_serialize(obj) -> str:
    """Safely serialize a Pydantic model, dictionary, or string to JSON string."""
    if obj is None:
        return "None"
    if hasattr(obj, 'model_dump'):
        return json.dumps(obj.model_dump())
    elif isinstance(obj, dict):
        return json.dumps(obj)
    elif isinstance(obj, str):
        # Try to parse string as JSON, if fails, return raw string
        try:
            return json.dumps(json.loads(obj))
        except:
            return json.dumps({"raw": obj})
    return str(obj)

# --- LLM Query Helpers ---

async def call_with_retry(func, *args, max_attempts=3, **kwargs):
    from groq import APIStatusError
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except APIStatusError as e:
            # Only retry on rate limits (429) or server errors (5xx)
            if e.status_code in [429, 500, 502, 503]:
                logger.warning(f"Attempt {attempt + 1} failed with retryable error {e.status_code}")
                if attempt == max_attempts - 1:
                    raise e
                await asyncio.sleep(2 ** attempt)
            else:
                # Fail fast on 401, 403, 404, etc.
                logger.error(f"Non-retryable API error {e.status_code}: {e}")
                raise e
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed with error: {e}")
            if attempt == max_attempts - 1:
                raise e
            await asyncio.sleep(2 ** attempt)

async def query_groq(system_instruction: str, user_prompt: str, schema: Any, api_key: Optional[str] = None, model: Optional[str] = None, timeout: float = 30.0, max_attempts: int = 3) -> Dict[str, Any]:
    key_to_use = api_key or settings.GROQ_API_KEY
    if not key_to_use:
        raise ValueError("GROQ_API_KEY is not configured.")
    
    model_to_use = model or "llama-3.3-70b-versatile"
    client = AsyncGroq(api_key=key_to_use, timeout=timeout)
    
    async def _call():
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            model=model_to_use,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        schema(**parsed)  # validate structure
        return parsed
        
    return await call_with_retry(_call, max_attempts=max_attempts)

async def query_groq_creative(system_instruction: str, user_prompt: str, schema: Any, api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """Uses a higher temperature for creative tasks like marketing copy."""
    key_to_use = api_key or settings.GROQ_API_KEY
    if not key_to_use:
        raise ValueError("GROQ_API_KEY is not configured.")
    
    model_to_use = model or "llama-3.3-70b-versatile"
    client = AsyncGroq(api_key=key_to_use, timeout=30.0)
    
    async def _call():
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            model=model_to_use,
            response_format={"type": "json_object"},
            temperature=0.85
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
    
    if state.gate_decision == "continue":
        await asyncio.to_thread(add_decision_log, state.session_id, "startup_advisor", "Idea approved to continue by founder.")
        latest_v = await asyncio.to_thread(get_latest_artifact_version, state.session_id, "startup_advisor")
        return {
            "gate_decision": None,
            "status": "running",
            "stages": {"startup_advisor": {"status": "complete", "version": latest_v}}
        }

    idea_to_validate = state.revised_idea if state.gate_decision == "revise" else state.idea
    
    system_instruction = (
        "You are a top-tier Venture Capitalist and ruthless Startup Advisor. "
        "Evaluate the provided startup idea strictly on market viability, execution risk, and capital efficiency. "
        "If this is a revised idea, assume the founder has attempted to address previous feedback. Only assign a high risk_score if the core fatal flaw remains completely unaddressed. "
        "Provide a definitive verdict (e.g., 'Approved', 'Needs Major Revision', 'Reject'). "
        "Assign a risk_score between 0.0 (safe) and 1.0 (fatal). "
        "Your reasoning must be 2-3 concise sentences identifying the biggest existential threat to the startup. "
        "List 2-3 specific, actionable red_flags (e.g., 'High CAC in saturated market', 'Regulatory hurdles'). "
        "You must return a JSON object with these exact keys: "
        '"verdict" (string), "risk_score" (number), "reasoning" (string), "red_flags" (array of strings).'
    )
    prompt = f"Evaluate this startup idea: '{idea_to_validate}' for a project named '{state.startup_name}'."
    
    logs = await asyncio.to_thread(get_decision_log, state.session_id)
    is_resume = any(f"Validated idea '{idea_to_validate}':" in l["reasoning"] for l in logs)
    
    result = None
    version = 0
    
    if is_resume:
        art_data = await asyncio.to_thread(get_latest_artifact, state.session_id, "startup_advisor")
        if art_data:
            result = ValidationResult(**art_data)
            version = await asyncio.to_thread(get_latest_artifact_version, state.session_id, "startup_advisor")
        else:
            is_resume = False

    try:
        if not is_resume:
            api_key = settings.GROQ_API_KEY
            if not api_key:
                result = ValidationResult(
                    verdict="Excellent idea",
                    risk_score=0.2,
                    reasoning="Straightforward business model and target (Mocked).",
                    red_flags=[]
                )
            else:
                result_dict = await query_groq(system_instruction, prompt, ValidationResult, api_key=api_key, model="llama-3.3-70b-versatile")
                result = ValidationResult(**result_dict)
                
            version = await asyncio.to_thread(save_artifact, state.session_id, "startup_advisor", result.model_dump())
            await asyncio.to_thread(add_decision_log, state.session_id, "startup_advisor", f"Validated idea '{idea_to_validate}': Verdict={result.verdict}, Risk={result.risk_score}")
        
        is_high_risk = result.risk_score > 0.85
        
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
                await asyncio.to_thread(add_decision_log, state.session_id, "startup_advisor", f"Founder requested revision with new idea: '{revised_idea_val}'")
                return {
                    "idea": revised_idea_val,
                    "gate_decision": "revise",
                    "revised_idea": revised_idea_val,
                    "startup_advisor": result,
                    "stages": {"startup_advisor": {"status": "running", "version": version}},
                    "status": "running"
                }
            else:
                await asyncio.to_thread(add_decision_log, state.session_id, "startup_advisor", "Founder chose to continue despite warnings.")
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
        "You are a Senior Market Research Analyst. Synthesize the provided search results into an actionable market report. "
        "Estimate the TAM (Total Addressable Market) realistically using a bottom-up or top-down approach (1 sentence). "
        "List exactly 3-4 key competitors, explicitly stating their core weakness or your differentiation. "
        "Identify 3 macro industry trends driving this market right now. "
        "You must output a valid JSON object with these exact keys: "
        '"tam_estimate" (string), "competitors" (array of objects with name, description, url), '
        '"trends" (array of strings), "sources" (array of strings).'
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nSearch Results:\n{search_results_str}"
    
    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            report = MarketResearchReport(
                tam_estimate="$500M",
                competitors=[{"name": "Competitor X", "description": "Market incumbent (Mocked)", "url": "https://competitor.com"}],
                trends=["Rising adoption of automation (Mocked)"],
                sources=sources
            )
            report_dict = report.model_dump()
        else:
            report_dict = await query_groq(system_instruction, prompt, MarketResearchReport, api_key=api_key, model="llama-3.3-70b-versatile")
            if not report_dict.get("sources"):
                report_dict["sources"] = sources
            report = MarketResearchReport(**report_dict)
            
        version = await asyncio.to_thread(save_artifact, state.session_id, "market_research", report_dict)
        await asyncio.to_thread(add_decision_log, state.session_id, "market_research", "Successfully completed market research report using web search.")
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
    market_report_str = safe_serialize(market_report) if market_report else "No market report available."
    
    system_instruction = (
        "You are a Principal Product Manager. Write a lean, high-impact PRD. "
        "Define a sharp problem_statement (2 sentences). "
        "Write 3-4 core user_stories in the format: 'As a [user], I want to [action] so that [value]'. "
        "List 4-5 features using the MoSCoW prioritization method (Must-have, Should-have) for priority. "
        "Define a 2-phase roadmap_phases (MVP vs V2). "
        "You must output a valid JSON object with these exact keys: "
        '"problem_statement" (string), "user_stories" (array of strings), '
        '"features" (array of objects with name, description, priority), '
        '"roadmap_phases" (array of objects with name, items).'
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nMarket Research Report:\n{market_report_str}"
    
    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            prd = PRD(
                problem_statement=f"Simplify setup for idea: {idea_val} (Mocked)",
                user_stories=["As a founder, I want to review automated market validation report."],
                features=[{"name": "Skeletal Pipeline", "description": "Validates graph state", "priority": "High"}],
                roadmap_phases=[{"name": "Phase 1", "items": ["Skeletal Pipeline"]}]
            )
            prd_dict = prd.model_dump()
        else:
            prd_dict = await query_groq(system_instruction, prompt, PRD, api_key=api_key, model="llama-3.3-70b-versatile")
            prd = PRD(**prd_dict)
            
        version = await asyncio.to_thread(save_artifact, state.session_id, "product_manager", prd_dict)
        await asyncio.to_thread(add_decision_log, state.session_id, "product_manager", "Compiled and generated Product Requirement Document (PRD).")
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
    prd_str = safe_serialize(prd) if prd else "No PRD available."
    
    system_instruction = (
        "You are a Principal Software Architect. Design a scalable, lean architecture for an MVP. "
        "You must output a valid JSON object with exactly these 4 keys: "
        '"db_schema_sql", "db_schema_mermaid", "api_endpoints", "system_design_notes". '
        "For db_schema_sql, provide DDL statements only (PostgreSQL syntax). "
        "For db_schema_mermaid, provide a string that STARTS EXACTLY with 'erDiagram'. "
        "Do NOT put table definitions before 'erDiagram'. "
        "CRITICAL: Use specific SQL data types in the mermaid diagram (e.g., VARCHAR(255), TIMESTAMP, BOOLEAN, UUID, INT). "
        "Include constraints like PK, FK, and UNIQUE. "
        "Example of correct db_schema_mermaid syntax: "
        "\"erDiagram\\n  USERS {\\n    UUID id PK\\n    VARCHAR(255) email UNIQUE\\n  }\\n  SESSIONS {\\n    UUID id PK\\n    UUID user_id FK\\n    TIMESTAMP created_at\\n  }\\n  USERS ||--o{ SESSIONS : has\". "
        "For api_endpoints, provide an array of objects, each with 'method', 'path', and 'description'. "
        "For system_design_notes, write 2-3 sentences explaining the tech stack."
    )
    prompt = f"Product Requirement Document (PRD):\n{prd_str}"
    
    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            spec = ArchitectureSpec(
                db_schema_sql="CREATE TABLE sessions (id TEXT, idea TEXT);",
                db_schema_mermaid="erDiagram SESSIONS { string id string idea }",
                api_endpoints=[{"method": "POST", "path": "/sessions", "description": "Create session"}],
                system_design_notes="Utilizing SQLite database and FastAPI backend (Mocked)."
            )
            spec_dict = spec.model_dump()
        else:
            spec_dict = await query_groq(system_instruction, prompt, ArchitectureSpec, api_key=api_key, model="llama-3.3-70b-versatile")
            spec = ArchitectureSpec(**spec_dict)
            
        version = await asyncio.to_thread(save_artifact, state.session_id, "architect", spec_dict)
        await asyncio.to_thread(add_decision_log, state.session_id, "architect", "Generated database schema SQL and system design specification.")
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
    
    try:
        # CRITICAL FIX: Safely handle LangGraph state deserialization
        spec = state.architect
        if spec is None:
            spec_str = "No architecture spec available."
        elif hasattr(spec, 'model_dump'):
            spec_data = spec.model_dump()
        elif isinstance(spec, str):
            try:
                spec_data = json.loads(spec)
            except:
                spec_data = {"system_design_notes": spec}
        else:
            # Assume it's a dict
            spec_data = spec
            
        # Only pass the API endpoints and notes to the EM to make the LLM respond 10x faster!
        spec_str = json.dumps({
            "api_endpoints": spec_data.get("api_endpoints", []),
            "system_design_notes": spec_data.get("system_design_notes", "")
        })
        
        system_instruction = (
            "You are a Senior Engineering Manager. Create a concise sprint plan. "
            "Create exactly 3 GitHub issues. Keep the body under 20 words. "
            "You must output a valid JSON object with these exact keys: "
            '"issues" (array of objects with title, body, labels), '
            '"sprints" (array of objects with name, issue_titles).'
        )
        prompt = f"Architecture Specification:\n{spec_str}"
        
        api_key = settings.GROQ_API_KEY
        if not api_key:
            plan_dict = {
                "issues": [{"title": "Setup SQLite Schema", "body": "Create schemas.", "labels": ["db", "setup"]}],
                "sprints": [{"name": "Sprint 1", "issue_titles": ["Setup SQLite Schema"]}]
            }
        else:
            # CRITICAL FIX: Short timeout and 1 retry to fail fast and prevent UI lockups
            raw_dict = await query_groq(
                system_instruction, 
                prompt, 
                IssuesAndSprintPlan, 
                api_key=api_key, 
                model="llama-3.3-70b-versatile",
                timeout=15.0,
                max_attempts=1
            )
            
            # Safe parse. Force the keys to exist so Pydantic never crashes.
            if not isinstance(raw_dict.get("issues"), list): raw_dict["issues"] = []
            if not isinstance(raw_dict.get("sprints"), list): raw_dict["sprints"] = []
                
            plan_dict = raw_dict
            
        plan = IssuesAndSprintPlan(**plan_dict)
            
        version = await asyncio.to_thread(save_artifact, state.session_id, "engineering_manager", plan_dict)
        await asyncio.to_thread(add_decision_log, state.session_id, "engineering_manager", "Compiled issues backlog and sprint timeline.")
        
        # Trigger GitHub integration in the background so it doesn't block the UI/Pipeline
        if state.github_repo:
            try:
                from tools.github import create_github_issues_bulk
                issues_list = [iss.model_dump() if hasattr(iss, 'model_dump') else iss for iss in plan.issues]
                
                task = asyncio.create_task(create_github_issues_bulk(state.github_repo, issues_list))
                # FIX: Add error callback so failures aren't swallowed silently
                task.add_done_callback(lambda t: logger.error(f"GitHub sync failed: {t.exception()}") if t.exception() else logger.info("GitHub sync completed successfully."))
                
                await asyncio.to_thread(add_decision_log, state.session_id, "engineering_manager", f"Started background sync to GitHub repository: {state.github_repo}")
            except Exception as github_err:
                logger.warning(f"Failed to start GitHub sync: {github_err}")
                
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
    prd_str = safe_serialize(prd) if prd else "No PRD available."
    
    system_instruction = (
        "You are a world-class Creative Director and Direct-Response Copywriter. "
        "Your goal is to write emotionally resonant, high-converting launch assets that make people stop scrolling. "
        "Write landing_copy: Use the AIDA framework. Start with a bold, provocative headline (USE ALL CAPS FOR THE HEADLINE). Follow with a subheadline that agitates a pain point. Provide 3 benefit-driven bullet points (use dashes '- '). End with a strong call-to-action. "
        "CRITICAL: Do NOT use HTML tags (like <h1>, <ul>, <button>). Use plain text only with line breaks for formatting. "
        "Write linkedin_post: Tell a short, engaging story about why this startup exists. Be slightly vulnerable and professional. Use line breaks for readability. End with a question to drive engagement. "
        "Write email_campaign: Write a short, urgency-driven email to a waitlist. Start with a curiosity-inducing subject line (e.g., 'Subject: ...'). Keep the body under 100 words. "
        "You must output a valid JSON object with these exact keys: "
        '"landing_copy" (string), "linkedin_post" (string), "email_campaign" (string). '
        "Do not nest these inside other objects; they must be plain strings at the top level."
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nProduct Requirement Document (PRD):\n{prd_str}"
    
    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            assets = MarketingAssets(
                landing_copy="AI Founder OS: Automate your product validation.",
                linkedin_post="Accelerating startup workflows with AI Founder OS!",
                email_campaign="Introducing automated pipeline for startup validation."
            )
            assets_dict = assets.model_dump()
        else:
            assets_dict = await query_groq_creative(system_instruction, prompt, MarketingAssets, api_key=api_key, model="llama-3.3-70b-versatile")
            assets = MarketingAssets(**assets_dict)
            
        version = await asyncio.to_thread(save_artifact, state.session_id, "marketing", assets_dict)
        await asyncio.to_thread(add_decision_log, state.session_id, "marketing", "Generated promotional copy and launch assets.")
        return {"marketing": assets, "stages": {"marketing": {"status": "complete", "version": version}}}
    except Exception as e:
        logger.exception(f"Error in marketing_node: {e}")
        if "marketing" not in failed_stages:
            failed_stages.append("marketing")
        return {"stages": {"marketing": {"status": "failed", "version": 0}}, "failed_stages": failed_stages}

async def join_node(state: GraphState) -> Dict[str, Any]:
    if state.failed_stages:
        return {"status": "failed"}
    return {"status": "complete"}

# --- Conditional Routing ---

def router_after_advisor(state: GraphState) -> str:
    if state.gate_decision == "revise":
        return "startup_advisor"
    return "market_research"

# --- Build StateGraph ---

def create_graph(checkpointer=None):
    workflow = StateGraph(GraphState)
    
    workflow.add_node("startup_advisor", startup_advisor_node)
    workflow.add_node("market_research", market_research_node)
    workflow.add_node("product_manager", product_manager_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("engineering_manager", engineering_manager_node)
    workflow.add_node("marketing", marketing_node)
    workflow.add_node("join", join_node)
    
    workflow.add_edge(START, "startup_advisor")
    workflow.add_conditional_edges(
        "startup_advisor",
        router_after_advisor,
        {
            "startup_advisor": "startup_advisor",
            "market_research": "market_research"
        }
    )
    workflow.add_edge("market_research", "product_manager")
    workflow.add_edge("product_manager", "architect")
    workflow.add_edge("product_manager", "marketing")
    workflow.add_edge("architect", "engineering_manager")
    workflow.add_edge("engineering_manager", "join")
    workflow.add_edge("marketing", "join")
    workflow.add_edge("join", END)
    
    return workflow.compile(checkpointer=checkpointer)