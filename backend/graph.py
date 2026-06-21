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
                if "trigger_gate" in idea_to_validate:
                    result = ValidationResult(
                        verdict="Needs Major Revision",
                        risk_score=0.9,
                        reasoning="A volatile dangerous project (Mocked trigger_gate).",
                        red_flags=["Potential hazard", "High volatility"]
                    )
                else:
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
        "You are a Senior Market Research Analyst. Synthesize the provided search results into an actionable, data-driven market report. "
        "Estimate the TAM (Total Addressable Market) realistically. If search results provide specific numbers, CAGR, or sources, USE THEM EXACTLY (e.g., '$10.06B by 2029, CAGR 7.96% [source]'). "
        "List exactly 3-4 key competitors, explicitly stating their core weakness. "
        "Identify 3 macro industry trends driving this market right now. "
        "Identify 2-3 market gaps that this startup could exploit. "
        "Provide a SWOT Analysis for this startup (2-3 points each for Strengths, Weaknesses, Opportunities, Threats). "
        "You must output a valid JSON object with these exact keys: "
        '"tam_estimate" (string), "competitors" (array of objects with name, description, url), '
        '"trends" (array of strings), "sources" (array of strings), '
        '"swot" (object with arrays of strings: strengths, weaknesses, opportunities, threats), '
        '"gaps" (array of strings).'
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nSearch Results:\n{search_results_str}"
    
    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            report_dict = {
                "tam_estimate": "$500M",
                "competitors": [{"name": "Competitor X", "description": "Market incumbent (Mocked)", "url": "https://competitor.com"}],
                "trends": ["Rising adoption of automation (Mocked)"],
                "sources": sources,
                "swot": {
                    "strengths": ["Agile engineering"],
                    "weaknesses": ["Low initial funding"],
                    "opportunities": ["AI market expansion"],
                    "threats": ["Big tech competitors"]
                },
                "gaps": ["Personalized client management"]
            }
        else:
            report_dict = await query_groq(system_instruction, prompt, MarketResearchReport, api_key=api_key, model="llama-3.3-70b-versatile")
            if not report_dict.get("sources"):
                report_dict["sources"] = sources
            if not report_dict.get("swot"):
                report_dict["swot"] = {
                    "strengths": [],
                    "weaknesses": [],
                    "opportunities": [],
                    "threats": []
                }
            if not isinstance(report_dict.get("gaps"), list):
                report_dict["gaps"] = []
                
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
        "CRITICAL: You MUST provide EXACTLY 3 goals in the 'goals' array, and EXACTLY 3 success metrics in the 'success_metrics' array. No more, no less. This is a strict constraint. "
        "Define a sharp problem_statement (2 sentences). "
        "Write 3-4 core user_stories in the format: 'As a [user], I want to [action] so that [value]'. "
        "List 4-5 features using the MoSCoW prioritization method (Must-have, Should-have) for priority. "
        "Define a 2-phase roadmap_phases (MVP vs V2). "
        "You must output a valid JSON object with these exact keys: "
        '"goals" (array of exactly 3 strings), "success_metrics" (array of exactly 3 strings), '
        '"problem_statement" (string), "user_stories" (array of strings), '
        '"features" (array of objects with name, description, priority), '
        '"roadmap_phases" (array of objects with name, items).'
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nMarket Research Report:\n{market_report_str}"
    
    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            prd = PRD(
                goals=["Validate product concept", "Identify core features", "Launch MVP within 90 days"],
                success_metrics=["MVP launched on schedule", "3-5 user feedback sessions completed", "100+ beta registrations"],
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
        spec_data = {}
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
            "You are a Senior Engineering Manager. Create a comprehensive sprint plan. "
            "Create exactly 4 sprints. Create exactly 4-5 GitHub issues per sprint (total ~16-20 issues). "
            "Each issue must have a title, body, labels (backend, frontend, infra, design), and story_points (1, 2, 3, 5, or 8). "
            "Provide a 'definition_of_done' array with 3 strict criteria. "
            "Provide a 'tech_debt_risks' array with 2-3 specific risks. "
            "Provide a 'team_size_recommended' string (e.g., '3 engineers'). "
            "You must output a valid JSON object with these exact keys: "
            '"issues" (array of objects with title, body, labels, story_points), '
            '"sprints" (array of objects with name, issue_titles), '
            '"definition_of_done" (array of strings), '
            '"tech_debt_risks" (array of strings), '
            '"team_size_recommended" (string).'
        )
        prompt = f"Architecture Specification:\n{spec_str}"
        
        api_key = settings.GROQ_API_KEY
        if not api_key:
            plan_dict = {
                "issues": [{"title": "Setup SQLite Schema", "body": "Create schemas.", "labels": ["db", "setup"], "story_points": 3}],
                "sprints": [{"name": "Sprint 1", "issue_titles": ["Setup SQLite Schema"]}],
                "definition_of_done": ["Code compiles", "Tests pass", "Approved by team"],
                "tech_debt_risks": ["Potential DB lockups"],
                "team_size_recommended": "2-3 engineers"
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
            if not isinstance(raw_dict.get("definition_of_done"), list): raw_dict["definition_of_done"] = []
            if not isinstance(raw_dict.get("tech_debt_risks"), list): raw_dict["tech_debt_risks"] = []
            if not raw_dict.get("team_size_recommended"): raw_dict["team_size_recommended"] = "2-3 engineers"
                
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
        "You are a world-class Creative Director and Growth Lead. Generate a comprehensive Go-To-Market strategy. "
        "Write landing_copy: A bold headline, subheadline, 3 value props, and a CTA. Do NOT use HTML tags. "
        "Write linkedin_post: A professional announcement post. "
        "Write email_campaign: A short, urgency-driven email. "
        "Develop a 5-step Email Drip Campaign sequence (Goal, Send Day [Day 0, Day 3, Day 7, Day 14, Day 30], Subject, Body). "
        "Define a Freemium Pricing Model with 2 tiers (Basic and Premium) including price and features. "
        "Provide a 'ninety_day_plan' array with 3 phases (Month 1, Month 2, Month 3) detailing launch and growth tactics. "
        "Provide 'launch_channels' array with 2-3 objects (e.g., Product Hunt, Instagram) including 'channel', 'tactic', and 'expected_reach'. "
        "You must output a valid JSON object with these exact keys: "
        '"landing_copy" (string), "linkedin_post" (string), "email_campaign" (string), '
        '"pricing_tiers" (array of objects with model, price, features), '
        '"email_sequence" (array of objects with goal, send_day, subject, body), '
        '"ninety_day_plan" (array of strings), '
        '"launch_channels" (array of objects with channel, tactic, expected_reach). '
        "Do not nest these inside other objects; top-level keys only."
    )
    prompt = f"Startup Idea: '{idea_val}'\n\nProduct Requirement Document (PRD):\n{prd_str}"
    
    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            assets_dict = {
                "landing_copy": "AI Founder OS: Automate your product validation.",
                "linkedin_post": "Accelerating startup workflows with AI Founder OS!",
                "email_campaign": "Introducing automated pipeline for startup validation.",
                "pricing_tiers": [{"model": "Basic", "price": "Free", "features": ["1 user", "Basic docs"]}],
                "email_sequence": [{"goal": "Onboarding", "send_day": "Day 0", "subject": "Welcome!", "body": "Welcome aboard."}],
                "ninety_day_plan": ["Month 1: Design logo", "Month 2: Launch beta", "Month 3: Scale marketing"],
                "launch_channels": [{"channel": "Product Hunt", "tactic": "Post daily updates", "expected_reach": "1000 users"}]
            }
        else:
            assets_dict = await query_groq_creative(system_instruction, prompt, MarketingAssets, api_key=api_key, model="llama-3.3-70b-versatile")
            if not isinstance(assets_dict.get("pricing_tiers"), list): assets_dict["pricing_tiers"] = []
            if not isinstance(assets_dict.get("email_sequence"), list): assets_dict["email_sequence"] = []
            if not isinstance(assets_dict.get("ninety_day_plan"), list): assets_dict["ninety_day_plan"] = []
            if not isinstance(assets_dict.get("launch_channels"), list): assets_dict["launch_channels"] = []
            
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
    stages_dict = state.stages or {}
    all_stages = ["startup_advisor", "market_research", "product_manager", "architect", "engineering_manager", "marketing"]
    
    # Check if all stages are done (either complete or failed)
    all_done = all(stages_dict.get(s, {}).get("status") in ["complete", "failed"] for s in all_stages)
    
    if all_done:
        if state.failed_stages or any(stages_dict.get(s, {}).get("status") == "failed" for s in all_stages):
            return {"status": "failed"}
        return {"status": "complete"}
        
    return {"status": "running"}

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