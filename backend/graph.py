# AI Founder Orchestration System - LangGraph Workflow
# System prompts upgraded for Groq Llama 3.3 70B — production-grade, Maestro-beating output quality
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


# ---------------------------------------------------------------------------
# LangGraph Helper Functions
# ---------------------------------------------------------------------------

def init_saver(db_path: str = "checkpoints.db") -> AsyncSqliteSaver:
    """Return an async SQLite checkpointer for the given db path."""
    return AsyncSqliteSaver.from_conn_string(db_path)


def update_stage(
    stages: Optional[Dict[str, Any]],
    stage_name: str,
    status: str,
    version: int = 0,
) -> Dict[str, Any]:
    """Return a new stages dict with the named stage updated."""
    current = dict(stages or {})
    current[stage_name] = {"status": status, "version": version}
    return current


def safe_serialize(obj) -> str:
    """Safely serialise a Pydantic model, dict, or string to a JSON string."""
    if obj is None:
        return "None"
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump())
    if isinstance(obj, dict):
        return json.dumps(obj)
    if isinstance(obj, str):
        try:
            return json.dumps(json.loads(obj))
        except (json.JSONDecodeError, ValueError):
            return json.dumps({"raw": obj})
    return str(obj)


# ---------------------------------------------------------------------------
# LLM Query Helpers
# ---------------------------------------------------------------------------

async def call_with_retry(func, *args, max_attempts: int = 3, **kwargs):
    """Retry an async callable on retryable Groq API errors with exponential back-off."""
    from groq import APIStatusError

    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except APIStatusError as exc:
            if exc.status_code in {429, 500, 502, 503}:
                logger.warning(
                    "Attempt %d/%d failed with retryable error %d",
                    attempt + 1, max_attempts, exc.status_code,
                )
                if attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("Non-retryable API error %d: %s", exc.status_code, exc)
                raise
        except Exception as exc:
            logger.warning("Attempt %d/%d failed: %s", attempt + 1, max_attempts, exc)
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(2 ** attempt)


async def query_groq(
    system_instruction: str,
    user_prompt: str,
    schema: Any,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 30.0,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Call the Groq chat-completions endpoint and validate the response against schema."""
    key_to_use = api_key or settings.GROQ_API_KEY
    if not key_to_use:
        raise ValueError("GROQ_API_KEY is not configured.")

    model_to_use = model or "llama-3.3-70b-versatile"
    client = AsyncGroq(api_key=key_to_use, timeout=timeout)

    async def _call():
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            model=model_to_use,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        schema(**parsed)  # validate structure against Pydantic model
        return parsed

    return await call_with_retry(_call, max_attempts=max_attempts)


async def query_groq_creative(
    system_instruction: str,
    user_prompt: str,
    schema: Any,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Higher temperature variant for creative tasks (marketing copy, etc.)."""
    key_to_use = api_key or settings.GROQ_API_KEY
    if not key_to_use:
        raise ValueError("GROQ_API_KEY is not configured.")

    model_to_use = model or "llama-3.3-70b-versatile"
    client = AsyncGroq(api_key=key_to_use, timeout=30.0)

    async def _call():
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            model=model_to_use,
            response_format={"type": "json_object"},
            temperature=0.85,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        schema(**parsed)
        return parsed

    return await call_with_retry(_call)


# ---------------------------------------------------------------------------
# Node: Startup Advisor
# ---------------------------------------------------------------------------

# ── UPGRADED SYSTEM PROMPT ─────────────────────────────────────────────────
_ADVISOR_SYSTEM = """\
You are a General Partner at a Sequoia / a16z-caliber venture capital firm. \
You have personally evaluated 5,000+ startup pitches and led investments across \
FinTech, DevTools, AI/ML, and Consumer SaaS. Your reputation rests on ruthless \
clarity — founders pay $50k/hour for advisory calls because you cut to the truth \
faster than anyone in the room.

YOUR JOB: Deliver a BRUTAL, HONEST, and ACTIONABLE evaluation. \
Not a cheerleader report. Not vague optimism. The founder needs the hardest truth \
NOW, before they waste 2 years and $500k.

MANDATORY EVALUATION FRAMEWORK — apply ALL 5 lenses before scoring:

1. FOUNDER-MARKET FIT
   Does this founder have an unfair advantage in this space? \
   (domain expertise, lived experience, network, proprietary data access)

2. MARKET TIMING — "WHY NOW?"
   What specific macro shift (AI commoditisation, regulatory change, \
   consumer behaviour flip) makes this the RIGHT window — not 2019, not 2030, \
   but RIGHT NOW in the current year?

3. UNIT ECONOMICS VIABILITY
   Can this business reach positive gross margins at scale? \
   Is the CAC recoverable within 12 months of LTV? \
   Is the pricing model defensible against a well-funded competitor?

4. COMPETITIVE MOAT
   What is the DURABLE defensible advantage in Year 3? \
   (network effects, proprietary data flywheel, switching cost, regulatory moat, brand)

5. SINGLE POINT OF DEATH
   If this startup fails, what is the MOST LIKELY cause? \
   Be specific: "Lose to incumbents on distribution" is weak. \
   "Stripe will ship this as a free add-on to 5M existing merchants in 90 days" is sharp.

RISK SCORE CALIBRATION:
   0.0 – 0.25 → "Approved" — Fundable NOW. Strong fundamentals, clear Series A path.
   0.25 – 0.55 → "Promising with Caveats" — Viable thesis, but 1-2 critical gaps to fix first.
   0.55 – 0.85 → "Needs Major Revision" — Core assumption is wrong. Pivot required.
   0.85 – 1.00 → "Reject" — Fatal flaw exists. Capital at serious risk.

REVISION HANDLING:
   If this is a REVISED idea, evaluate whether the founder has SPECIFICALLY addressed \
   the red_flags from the prior evaluation. If a red flag is genuinely fixed, \
   reduce the risk_score meaningfully (by at least 0.2). \
   Do NOT punish a fixed problem. Do NOT be lenient on an unfixed one.

OUTPUT RULES:
   - Return ONLY a valid JSON object. No markdown. No preamble. No explanation outside the JSON.
   - Required keys:
     "verdict"    → string — EXACTLY one of: Approved / Promising with Caveats / Needs Major Revision / Reject
     "risk_score" → float  — between 0.0 and 1.0, two decimal places
     "reasoning"  → string — 2-3 sentences. Must name the SINGLE biggest existential threat. \
Use the name of a real competitor or real market dynamic, not generics.
     "red_flags"  → array  — exactly 2-3 strings. Each must be SPECIFIC and ACTIONABLE. \
BAD: "Market is competitive." \
GOOD: "CAC will exceed 12-month LTV in Year 1 because organic acquisition is impossible \
in this keyword-saturated SaaS category without a $500k/month paid budget."
"""
# ──────────────────────────────────────────────────────────────────────────


async def startup_advisor_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["startup_advisor"] = {"status": "running", "version": 0}

    # --- Resume: founder already approved continuation ---
    if state.gate_decision == "continue":
        await asyncio.to_thread(
            add_decision_log,
            state.session_id,
            "startup_advisor",
            "Idea approved to continue by founder.",
        )
        latest_v = await asyncio.to_thread(
            get_latest_artifact_version, state.session_id, "startup_advisor"
        )
        return {
            "gate_decision": None,
            "status": "running",
            "stages": {"startup_advisor": {"status": "complete", "version": latest_v}},
        }

    idea_to_validate = state.revised_idea if state.gate_decision == "revise" else state.idea
    user_prompt = (
        f"Evaluate this startup idea: '{idea_to_validate}' "
        f"for a project named '{state.startup_name}'."
    )

    logs = await asyncio.to_thread(get_decision_log, state.session_id)
    is_resume = any(
        f"Validated idea '{idea_to_validate}':" in log["reasoning"] for log in logs
    )

    result: Optional[ValidationResult] = None
    version = 0

    if is_resume:
        art_data = await asyncio.to_thread(
            get_latest_artifact, state.session_id, "startup_advisor"
        )
        if art_data:
            result = ValidationResult(**art_data)
            version = await asyncio.to_thread(
                get_latest_artifact_version, state.session_id, "startup_advisor"
            )
        else:
            is_resume = False

    try:
        if not is_resume:
            api_key = settings.GROQ_API_KEY
            if not api_key:
                # Deterministic mock — used in local dev without a key
                if "trigger_gate" in idea_to_validate:
                    result = ValidationResult(
                        verdict="Needs Major Revision",
                        risk_score=0.9,
                        reasoning="A volatile dangerous project (Mocked trigger_gate).",
                        red_flags=["Potential hazard", "High volatility"],
                    )
                else:
                    result = ValidationResult(
                        verdict="Promising with Caveats",
                        risk_score=0.3,
                        reasoning="Straightforward business model and clear target market (Mocked).",
                        red_flags=[],
                    )
            else:
                result_dict = await query_groq(
                    _ADVISOR_SYSTEM,
                    user_prompt,
                    ValidationResult,
                    api_key=api_key,
                    model="llama-3.3-70b-versatile",
                )
                result = ValidationResult(**result_dict)

            version = await asyncio.to_thread(
                save_artifact, state.session_id, "startup_advisor", result.model_dump()
            )
            await asyncio.to_thread(
                add_decision_log,
                state.session_id,
                "startup_advisor",
                f"Validated idea '{idea_to_validate}': Verdict={result.verdict}, Risk={result.risk_score}",
            )

        is_high_risk = result.risk_score > 0.85

        if is_high_risk:
            stages["startup_advisor"] = {"status": "awaiting_gate", "version": version}
            user_response = interrupt(
                {
                    "risk_score": result.risk_score,
                    "red_flags": result.red_flags,
                    "verdict": result.verdict,
                    "reasoning": result.reasoning,
                }
            )
            decision = user_response.get("decision")
            revised_idea_val = user_response.get("revised_idea", "")

            if decision == "revise":
                await asyncio.to_thread(
                    add_decision_log,
                    state.session_id,
                    "startup_advisor",
                    f"Founder requested revision with new idea: '{revised_idea_val}'",
                )
                return {
                    "idea": revised_idea_val,
                    "gate_decision": "revise",
                    "revised_idea": revised_idea_val,
                    "startup_advisor": result,
                    "stages": {"startup_advisor": {"status": "running", "version": version}},
                    "status": "running",
                }

            await asyncio.to_thread(
                add_decision_log,
                state.session_id,
                "startup_advisor",
                "Founder chose to continue despite high-risk warnings.",
            )
            return {
                "gate_decision": "continue",
                "startup_advisor": result,
                "stages": {"startup_advisor": {"status": "complete", "version": version}},
                "status": "running",
            }

        return {
            "startup_advisor": result,
            "gate_decision": None,
            "stages": {"startup_advisor": {"status": "complete", "version": version}},
            "status": "running",
        }

    except GraphInterrupt:
        raise
    except Exception as exc:
        logger.exception("Error in startup_advisor_node: %s", exc)
        if "startup_advisor" not in failed_stages:
            failed_stages.append("startup_advisor")
        return {
            "stages": {"startup_advisor": {"status": "failed", "version": 0}},
            "failed_stages": failed_stages,
            "status": "failed",
        }


# ---------------------------------------------------------------------------
# Node: Market Research
# ---------------------------------------------------------------------------

# ── UPGRADED SYSTEM PROMPT ─────────────────────────────────────────────────
_MARKET_RESEARCH_SYSTEM = """\
You are a Senior Research Analyst with 15 years at McKinsey & Company, \
specialising in technology markets, competitive intelligence, and market-entry strategy. \
Your research has been cited by Fortune 500 boards and used to underwrite $2B+ in venture capital. \
Your reports are known for three things: precise numbers, brutal competitor takedowns, and \
monetisable insight — not vague observations.

RESEARCH METHODOLOGY — apply ALL frameworks before writing:

1. MARKET SIZING (TAM / SAM / SOM)
   TAM  = Total Addressable Market (the entire universe of buyers worldwide)
   SAM  = Serviceable Addressable Market (the realistic reachable segment by geography, ICP)
   SOM  = Serviceable Obtainable Market (what this startup can realistically capture in Year 1-3)
   Express all three in the tam_estimate field: "TAM: $X | SAM: $Y | SOM: $Z by Year 2"
   Use EXACT figures and CAGR percentages from the search results. \
   If no numbers are in the search results, state your methodology explicitly \
   (bottom-up from pricing × addressable users, or top-down from industry reports).

2. WHY NOW — TIMING ANALYSIS
   Identify the SPECIFIC technological, regulatory, or behavioural shift making this \
   market timely in the current year. Encode this in trends[0]. \
   Generic trends ("AI is growing") are UNACCEPTABLE. \
   Good: "LLM inference cost dropped 100× since 2022, making AI-first vertical SaaS \
   finally profitable at SMB price points."

3. COMPETITOR TEARDOWN
   For each competitor, you MUST identify their SINGLE most exploitable weakness in \
   one direct sentence. Use this format in the description field: \
   "[Company]: [core strength], BUT [specific exploitable weakness that this startup can attack]."
   Example: "Intercom: Gold-standard customer messaging, BUT pricing starts at $74/month, \
   making them inaccessible to the 40M solo founders and micro-SaaS operators globally."

4. MARKET GAPS — SPECIFIC AND MONETISABLE
   Each gap must be a specific, fundable opportunity — NOT a vague statement. \
   BAD: "Small businesses are underserved." \
   GOOD: "No affordable (<$30/month) AI-powered inventory forecasting tool exists \
   for Shopify merchants with fewer than 500 SKUs — a segment of 2.1M stores."

5. SWOT — HONEST AND ASYMMETRIC
   Strengths: What genuine structural advantages does this startup have right now?
   Weaknesses: What will kill early traction if not fixed in the first 90 days?
   Opportunities: What specific trend or gap, if captured in the next 6 months, \
   creates an unfair advantage?
   Threats: Name real competitors or macro forces — not generic "big tech could copy us."

OUTPUT RULES:
   - Return ONLY a valid JSON object. No markdown. No preamble. No text outside the JSON.
   - If search results provide specific stats (CAGR, $ figures, company names), \
     USE THEM EXACTLY — do not paraphrase numbers.
   - Required keys:
     "tam_estimate"  → string  — TAM / SAM / SOM breakdown with year and source methodology
     "competitors"   → array   — 3-4 objects: {name, description (include weakness), url}
     "trends"        → array   — exactly 3 strings, each explaining WHY the trend matters \
for THIS specific startup (not just industry in general)
     "sources"       → array   — strings (URLs from search results)
     "swot"          → object  — {strengths: [2-3], weaknesses: [2-3], \
opportunities: [2-3], threats: [2-3]} — all strings
     "gaps"          → array   — 2-3 strings, each a specific, monetisable market gap
"""
# ──────────────────────────────────────────────────────────────────────────


async def market_research_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["market_research"] = {"status": "running", "version": 0}

    idea_val = state.idea
    search_results_str = ""
    sources: List[str] = []

    try:
        if settings.TAVILY_API_KEY:
            from tools.tavily import search_tavily

            search_res = await search_tavily(
                f"competitors and market trends for {idea_val}"
            )
            results = search_res.get("results", [])
            for r in results:
                title = r.get("title", "")
                url = r.get("url", "")
                content = r.get("content", "")
                search_results_str += f"Source: {title} ({url})\nContent: {content}\n\n"
                sources.append(url)
        else:
            search_results_str = "No live search results available (mock mode)."
            sources = ["https://tavily.com/mocked"]
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        search_results_str = "No search results available due to API failure."
        sources = ["https://tavily.com/fallback"]

    user_prompt = (
        f"Startup Idea: '{idea_val}'\n\n"
        f"Search Results:\n{search_results_str}"
    )

    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            report_dict = {
                "tam_estimate": "TAM: $2.1B | SAM: $650M (English-speaking SMB segment) | SOM: $8M by Year 2 (Mocked)",
                "competitors": [
                    {
                        "name": "Competitor X",
                        "description": "Competitor X: Strong brand recognition, BUT pricing starts at $99/month making them inaccessible to bootstrapped founders (Mocked)",
                        "url": "https://competitor.com",
                    }
                ],
                "trends": [
                    "LLM inference costs dropped 10× in 2024, making AI-first vertical tools profitable at sub-$30/month price points for the first time (Mocked)"
                ],
                "sources": sources,
                "swot": {
                    "strengths": ["First-mover advantage in underserved niche"],
                    "weaknesses": ["Zero brand recognition at launch"],
                    "opportunities": ["Open-source LLM wave reducing COGS by 60%"],
                    "threats": ["Notion or Linear could ship this as a free add-on"],
                },
                "gaps": [
                    "No affordable AI-powered solution exists for this specific segment below $30/month (Mocked)"
                ],
            }
        else:
            report_dict = await query_groq(
                _MARKET_RESEARCH_SYSTEM,
                user_prompt,
                MarketResearchReport,
                api_key=api_key,
                model="llama-3.3-70b-versatile",
            )
            # Guard against missing optional fields from the LLM
            if not report_dict.get("sources"):
                report_dict["sources"] = sources
            if not report_dict.get("swot"):
                report_dict["swot"] = {
                    "strengths": [],
                    "weaknesses": [],
                    "opportunities": [],
                    "threats": [],
                }
            if not isinstance(report_dict.get("gaps"), list):
                report_dict["gaps"] = []

        report = MarketResearchReport(**report_dict)

        version = await asyncio.to_thread(
            save_artifact, state.session_id, "market_research", report_dict
        )
        await asyncio.to_thread(
            add_decision_log,
            state.session_id,
            "market_research",
            "Successfully completed market research report using web search.",
        )
        return {
            "market_research": report,
            "stages": {"market_research": {"status": "complete", "version": version}},
        }

    except Exception as exc:
        logger.exception("Error in market_research_node: %s", exc)
        if "market_research" not in failed_stages:
            failed_stages.append("market_research")
        return {
            "stages": {"market_research": {"status": "failed", "version": 0}},
            "failed_stages": failed_stages,
        }


# ---------------------------------------------------------------------------
# Node: Product Manager
# ---------------------------------------------------------------------------

# ── UPGRADED SYSTEM PROMPT ─────────────────────────────────────────────────
_PM_SYSTEM = """\
You are a Principal Product Manager with 12 years at Google, Stripe, and Linear. \
You have shipped 8 B2B SaaS products, 3 of which crossed $10M ARR within 18 months. \
You write PRDs that engineers ship without a single clarifying meeting, \
and that investors use to underwrite valuations.

Your documents are known for ONE thing: ruthless prioritisation. \
Every word earns its place. Every feature is tied to a user's hair-on-fire problem. \
Nothing is on the roadmap because it sounds cool — only because it is THE thing \
standing between the user and their goal.

PRD CONSTRUCTION FRAMEWORK — apply ALL layers:

1. PROBLEM STATEMENT (2 sentences, customer language)
   Sentence 1: WHO has the problem, WHAT they are forced to do today, and WHY it is painful.
   Sentence 2: What the CONSEQUENCE of not solving it is (time lost, money lost, opportunity missed).
   Do NOT write from the startup's perspective. Write from the user's lived experience.

2. GOALS — EXACTLY 3 (no more, no less)
   Each goal must be a DIRECTIONAL outcome, not a task.
   BAD: "Build the market research feature."
   GOOD: "Enable solo founders to validate their market in under 60 minutes without hiring a consultant."

3. SUCCESS METRICS — EXACTLY 3 (no more, no less)
   Each metric must be MEASURABLE with a NUMBER and a TIMEFRAME.
   BAD: "High user retention."
   GOOD: "Achieve ≥40% Week-4 retention among cohorts onboarded in Month 1."
   Metric 1 = North Star Metric (the single number that proves PMF)
   Metric 2 = Activation metric (did users reach the "aha moment"?)
   Metric 3 = Business metric (revenue, conversion, or growth)

4. USER STORIES — 3-4 stories in strict JTBD format
   Format: "As a [specific persona with a job title], when [specific context or trigger], \
I want to [specific action] so I can [measurable outcome or goal]."
   Each story must name a SPECIFIC persona — not just "user."
   Example: "As a bootstrapped SaaS founder managing my roadmap solo, \
when I receive new user feedback after a launch, I want to automatically cluster \
it by theme so I can triage the top 3 issues without spending 2 hours in Notion."

5. FEATURES — MoSCoW PRIORITISATION (4-5 features)
   Must-have: If this feature is missing on Day 1, the product CANNOT be used. \
These are the MVP survival features.
   Should-have: Significant competitive differentiator; absence hurts conversion but \
not core utility.
   Nice-to-have: Delight features for V2 — don't build until PMF is proven.
   Each feature object: {name, description, priority}
   Description must answer: What does the user DO with this feature, and what is the \
OUTCOME they get?

6. ROADMAP PHASES — 2 phases only
   Phase 1 (0-3 months): MVP — prove the core hypothesis. Ship ONLY Must-have features.
   Phase 2 (3-6 months): Monetisation & Retention — add Should-have, begin paid tiers.
   Each phase object: {name, items}

OUTPUT RULES:
   - Return ONLY a valid JSON object. No markdown. No preamble. No text outside the JSON.
   - "goals" MUST have EXACTLY 3 strings
   - "success_metrics" MUST have EXACTLY 3 measurable strings (number + timeframe in each)
   - Required keys:
     "goals"             → array of EXACTLY 3 strings
     "success_metrics"   → array of EXACTLY 3 strings (each must include a number and timeframe)
     "problem_statement" → string (2 sentences, customer language, no startup jargon)
     "user_stories"      → array of 3-4 JTBD-format strings with specific persona
     "features"          → array of 4-5 objects: {name, description, priority}
     "roadmap_phases"    → array of exactly 2 objects: {name, items}
"""
# ──────────────────────────────────────────────────────────────────────────


async def product_manager_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["product_manager"] = {"status": "running", "version": 0}

    idea_val = state.idea
    market_report = state.market_research
    market_report_str = (
        safe_serialize(market_report) if market_report else "No market report available."
    )
    user_prompt = (
        f"Startup Idea: '{idea_val}'\n\n"
        f"Market Research Report:\n{market_report_str}"
    )

    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            prd = PRD(
                goals=[
                    "Enable founders to validate their startup idea in under 60 minutes without hiring consultants",
                    "Deliver an investor-ready founder package (PRD, GTM, architecture) from a single idea prompt",
                    "Reduce the average time from idea to MVP kickoff from 4 weeks to 4 days",
                ],
                success_metrics=[
                    "North Star: ≥70% of sessions result in a complete 6-agent output within 10 minutes by Month 2",
                    "Activation: ≥60% of new users reach the Marketing Output step within their first session",
                    "Business: ≥15% free-to-paid conversion within 30 days of launch (Mocked)",
                ],
                problem_statement=(
                    f"Solo founders and early-stage teams building '{idea_val}' spend 3-6 weeks "
                    f"manually producing market research, PRDs, and technical specs before writing a single line of code. "
                    f"This bottleneck kills momentum, delays fundraising conversations, and burns runway before the product is even validated (Mocked)."
                ),
                user_stories=[
                    "As a solo SaaS founder with a new idea but no team, when I finish a customer discovery call, I want to generate a validated market research report in minutes so I can pitch investors that same week."
                ],
                features=[
                    {
                        "name": "AI Founder Pipeline",
                        "description": "6-agent orchestration that produces a complete founder package from a single idea input",
                        "priority": "Must-have",
                    }
                ],
                roadmap_phases=[
                    {
                        "name": "Phase 1: MVP (Month 1-3)",
                        "items": ["Core pipeline", "Human-in-the-loop gate", "PDF export"],
                    },
                    {
                        "name": "Phase 2: Monetisation (Month 3-6)",
                        "items": ["Paid tiers", "GitHub integration", "Team workspaces"],
                    },
                ],
            )
            prd_dict = prd.model_dump()
        else:
            prd_dict = await query_groq(
                _PM_SYSTEM,
                user_prompt,
                PRD,
                api_key=api_key,
                model="llama-3.3-70b-versatile",
            )
            prd = PRD(**prd_dict)

        version = await asyncio.to_thread(
            save_artifact, state.session_id, "product_manager", prd_dict
        )
        await asyncio.to_thread(
            add_decision_log,
            state.session_id,
            "product_manager",
            "Compiled and generated Product Requirement Document (PRD).",
        )
        return {
            "product_manager": prd,
            "stages": {"product_manager": {"status": "complete", "version": version}},
        }

    except Exception as exc:
        logger.exception("Error in product_manager_node: %s", exc)
        if "product_manager" not in failed_stages:
            failed_stages.append("product_manager")
        return {
            "stages": {"product_manager": {"status": "failed", "version": 0}},
            "failed_stages": failed_stages,
        }


# ---------------------------------------------------------------------------
# Node: Architect
# ---------------------------------------------------------------------------

# ── UPGRADED SYSTEM PROMPT ─────────────────────────────────────────────────
_ARCHITECT_SYSTEM = """\
You are a Staff Software Architect with experience scaling systems at Stripe, \
Vercel, and PlanetScale. You have designed APIs serving 100M+ requests/day and \
data pipelines processing $50B+ in annual transaction volume. \
Your architecture decisions are driven by three immovable principles: \
SIMPLICITY (a junior engineer must understand it), \
OBSERVABILITY (every failure must be visible before a user reports it), and \
ZERO single points of failure in production.

ARCHITECTURE DESIGN PRINCIPLES — apply ALL before writing:

1. MVP-FIRST CONSTRAINT
   Design the LEANEST possible system that proves the core hypothesis. \
   Do NOT design for 1M users on Day 1. Design for 1,000 users and explicitly note \
   the scale ceiling and upgrade path in system_design_notes.

2. SECURITY-BY-DESIGN
   Every API endpoint that touches user data MUST be noted as auth_required. \
   system_design_notes MUST describe the authentication strategy \
   (JWT with refresh tokens / API key / session cookie) and where it is enforced \
   (middleware vs per-route).

3. OBSERVABILITY REQUIREMENT
   Every database table MUST include created_at and updated_at TIMESTAMP columns. \
   These are non-negotiable for debugging, billing, and audit trails.

4. SCALE CEILING DECLARATION
   system_design_notes MUST state: at what load (concurrent users or req/sec) \
   this architecture breaks, and what the upgrade path is \
   (e.g., "Handles ~500 concurrent users on a single Render instance. \
   Upgrade path: add Redis caching layer + read replica at 5k users.").

5. API DESIGN STANDARDS
   Follow RESTful resource-naming conventions. \
   Endpoint descriptions must include: what the endpoint does, \
   what it returns on success, and what status code errors return. \
   Example: "POST /api/sessions → Creates a new session, returns 201 + session object. \
   Returns 400 on validation error, 409 on duplicate."

DB SCHEMA — MERMAID SYNTAX RULES (STRICT — violations cause parse errors):
   - MUST begin EXACTLY with "erDiagram" — no preceding text, no blank lines before it
   - Use SPECIFIC data types: UUID, VARCHAR(255), TEXT, INT, BOOLEAN, TIMESTAMP, DECIMAL(10,2)
   - ALWAYS include PK, FK, UNIQUE constraints where applicable
   - ALWAYS show all table relationships with correct cardinality \
     (||--o{, ||--||, }o--||, etc.)
   - Include created_at TIMESTAMP and updated_at TIMESTAMP on EVERY table
   - CORRECT example:
     "erDiagram\\n  USERS {\\n    UUID id PK\\n    VARCHAR(255) email UNIQUE\\n    \
TIMESTAMP created_at\\n    TIMESTAMP updated_at\\n  }\\n  \
SESSIONS {\\n    UUID id PK\\n    UUID user_id FK\\n    TIMESTAMP created_at\\n  }\\n  \
USERS ||--o{ SESSIONS : has"

DB SCHEMA — SQL DDL RULES:
   - PostgreSQL syntax only
   - Include PRIMARY KEY, FOREIGN KEY, UNIQUE constraints
   - Add CREATE INDEX statements on foreign key columns and frequently queried columns
   - Use ON DELETE CASCADE or SET NULL where semantically correct
   - Timestamps must use DEFAULT NOW() or DEFAULT CURRENT_TIMESTAMP

OUTPUT RULES:
   - Return ONLY a valid JSON object. No markdown. No preamble. No text outside the JSON.
   - Required keys:
     "db_schema_sql"      → string — PostgreSQL DDL including indexes, constraints, \
and foreign keys
     "db_schema_mermaid"  → string — MUST start with exactly "erDiagram", \
followed by the schema using the correct Mermaid ER syntax
     "api_endpoints"      → array  — objects: {method, path, description, \
auth_required (boolean)}
     "system_design_notes"→ string — 3-4 sentences covering: \
(a) tech stack with rationale, (b) auth strategy, \
(c) scale ceiling + upgrade path
"""
# ──────────────────────────────────────────────────────────────────────────


async def architect_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["architect"] = {"status": "running", "version": 0}

    prd = state.product_manager
    prd_str = safe_serialize(prd) if prd else "No PRD available."
    user_prompt = f"Product Requirement Document (PRD):\n{prd_str}"

    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            spec = ArchitectureSpec(
                db_schema_sql=(
                    "CREATE TABLE users (\n"
                    "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "  email VARCHAR(255) UNIQUE NOT NULL,\n"
                    "  created_at TIMESTAMP DEFAULT NOW(),\n"
                    "  updated_at TIMESTAMP DEFAULT NOW()\n"
                    ");\n\n"
                    "CREATE TABLE sessions (\n"
                    "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
                    "  user_id UUID REFERENCES users(id) ON DELETE CASCADE,\n"
                    "  idea TEXT NOT NULL,\n"
                    "  status VARCHAR(50) DEFAULT 'running',\n"
                    "  created_at TIMESTAMP DEFAULT NOW(),\n"
                    "  updated_at TIMESTAMP DEFAULT NOW()\n"
                    ");\n\n"
                    "CREATE INDEX idx_sessions_user_id ON sessions(user_id);\n"
                    "CREATE INDEX idx_sessions_status ON sessions(status);"
                ),
                db_schema_mermaid=(
                    "erDiagram\n"
                    "  USERS {\n"
                    "    UUID id PK\n"
                    "    VARCHAR(255) email UNIQUE\n"
                    "    TIMESTAMP created_at\n"
                    "    TIMESTAMP updated_at\n"
                    "  }\n"
                    "  SESSIONS {\n"
                    "    UUID id PK\n"
                    "    UUID user_id FK\n"
                    "    TEXT idea\n"
                    "    VARCHAR(50) status\n"
                    "    TIMESTAMP created_at\n"
                    "    TIMESTAMP updated_at\n"
                    "  }\n"
                    "  USERS ||--o{ SESSIONS : has"
                ),
                api_endpoints=[
                    {
                        "method": "POST",
                        "path": "/api/sessions",
                        "description": "Create a new founder session. Returns 201 + session object. 400 on validation error.",
                        "auth_required": True,
                    },
                    {
                        "method": "GET",
                        "path": "/api/sessions/{id}",
                        "description": "Retrieve session state and all agent outputs. Returns 200 + full session. 404 if not found.",
                        "auth_required": True,
                    },
                ],
                system_design_notes=(
                    "FastAPI backend with async SQLite (via aiosqlite) for the MVP, \
providing zero-infrastructure persistence suitable for up to 500 concurrent sessions. \
Authentication is handled via JWT Bearer tokens issued at login and validated in FastAPI middleware. \
This architecture handles ~500 concurrent users on a single Render instance; \
the upgrade path at 5k users is a PostgreSQL read replica + Redis caching layer for \
session state hot reads. (Mocked)"
                ),
            )
            spec_dict = spec.model_dump()
        else:
            spec_dict = await query_groq(
                _ARCHITECT_SYSTEM,
                user_prompt,
                ArchitectureSpec,
                api_key=api_key,
                model="llama-3.3-70b-versatile",
            )
            spec = ArchitectureSpec(**spec_dict)

        version = await asyncio.to_thread(
            save_artifact, state.session_id, "architect", spec_dict
        )
        await asyncio.to_thread(
            add_decision_log,
            state.session_id,
            "architect",
            "Generated database schema SQL and system design specification.",
        )
        return {
            "architect": spec,
            "stages": {"architect": {"status": "complete", "version": version}},
        }

    except Exception as exc:
        logger.exception("Error in architect_node: %s", exc)
        if "architect" not in failed_stages:
            failed_stages.append("architect")
        return {
            "stages": {"architect": {"status": "failed", "version": 0}},
            "failed_stages": failed_stages,
        }


# ---------------------------------------------------------------------------
# Node: Engineering Manager
# ---------------------------------------------------------------------------

# ── UPGRADED SYSTEM PROMPT ─────────────────────────────────────────────────
_EM_SYSTEM = """\
You are a Director of Engineering, formerly an Engineering Manager at Linear and Notion. \
You run sprints that ACTUALLY ship. Your GitHub issues are so well-written that \
any engineer — including a strong junior — can pick one up cold on a Monday morning \
and deliver it by Friday with zero clarification meetings.

Your sprint plans are famous for two things: \
(1) ruthless dependency ordering — no engineer is ever blocked by another sprint's output, and \
(2) honest definition-of-done — no wishful "it works correctly" criteria, \
only pass/fail verifiable conditions.

SPRINT PLANNING FRAMEWORK — apply ALL rules:

1. DEPENDENCY-ORDERED SPRINTS (EXACTLY 4 sprints)
   Sprint 1 — Foundation: DB schema, auth, environment setup, CI/CD pipeline. \
Nothing in Sprint 2 is possible without Sprint 1 being complete.
   Sprint 2 — Core Feature Set: The Must-have features from the PRD. The product is \
usable (not polished) by Sprint 2 end.
   Sprint 3 — Integration & Quality: End-to-end tests, error handling, external API \
integrations, performance baseline.
   Sprint 4 — Launch Polish: UI polish, onboarding flow, monitoring, documentation, \
production deployment.

2. ISSUE QUALITY STANDARD
   Every issue body must contain THREE parts:
   Part 1 — CONTEXT: Why does this issue exist? What breaks if we skip it?
   Part 2 — ACCEPTANCE CRITERIA: A bulleted checklist of PASS/FAIL conditions. \
At least 2 criteria per issue.
   Part 3 — TECHNICAL NOTES (optional but valued): A specific implementation hint or \
library suggestion.
   Issue title must be actionable — start with a verb: "Implement", "Create", "Add", \
"Fix", "Write", "Deploy".

3. STORY POINT CALIBRATION (Fibonacci: 1, 2, 3, 5, 8)
   1 = Under 2 hours. Simple config change or text update.
   2 = Half-day. Single-file change, well-understood scope.
   3 = Full day. Moderate complexity, clear path.
   5 = 2-3 days. Complex implementation, some unknowns.
   8 = 4-5 days. High complexity. Consider splitting if possible.
   Do NOT use 8 for more than 2 issues per sprint.

4. DEFINITION OF DONE — EXACTLY 3 criteria
   Every criterion must be MECHANICALLY VERIFIABLE — a CI tool, a Postman collection, \
or a test suite must be able to PROVE it passes.
   BAD: "Feature is working correctly."
   GOOD: "All 12 Postman collection requests return expected status codes \
in under 400ms on the staging environment."

5. TECH DEBT RISKS — 2-3 specific risks
   Each risk must name a SPECIFIC file, function, component, or architectural decision \
that will cause pain at 10× scale.
   BAD: "Database may have performance issues."
   GOOD: "The synchronous artifact save in db.py (save_artifact function) will create \
a thread-pool bottleneck at >200 concurrent sessions; migrate to full async SQLAlchemy \
before hitting 1k DAU."

STRICT OUTPUT CONSTRAINTS:
   - EXACTLY 4 sprint objects in the "sprints" array
   - EXACTLY 4-5 issue objects per sprint (16-20 issues total)
   - Each issue: {title (verb-first), body (context + acceptance criteria), \
labels (from: backend, frontend, infra, database, testing, design), story_points (1/2/3/5/8)}
   - Each sprint: {name, issue_titles (array of issue title strings)}
   - "definition_of_done": EXACTLY 3 mechanically verifiable strings
   - "tech_debt_risks": 2-3 strings referencing specific components or files
   - "team_size_recommended": specific string, e.g., "3 engineers: 1 backend, \
1 frontend, 1 fullstack/DevOps"

OUTPUT RULES:
   - Return ONLY a valid JSON object. No markdown. No preamble. No text outside the JSON.
   - Required keys: issues, sprints, definition_of_done, tech_debt_risks, team_size_recommended
"""
# ──────────────────────────────────────────────────────────────────────────


async def engineering_manager_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["engineering_manager"] = {"status": "running", "version": 0}

    try:
        spec = state.architect
        spec_data: Dict[str, Any] = {}

        if spec is None:
            pass  # spec_data stays empty, fallback string used below
        elif hasattr(spec, "model_dump"):
            spec_data = spec.model_dump()
        elif isinstance(spec, str):
            try:
                spec_data = json.loads(spec)
            except (json.JSONDecodeError, ValueError):
                spec_data = {"system_design_notes": spec}
        elif isinstance(spec, dict):
            spec_data = spec

        # Pass only endpoints + notes to the EM — keeps the prompt tight and fast
        spec_str = json.dumps(
            {
                "api_endpoints": spec_data.get("api_endpoints", []),
                "system_design_notes": spec_data.get("system_design_notes", ""),
            }
        )

        user_prompt = f"Architecture Specification:\n{spec_str}"

        api_key = settings.GROQ_API_KEY
        if not api_key:
            plan_dict = {
                "issues": [
                    {
                        "title": "Create PostgreSQL schema and run initial migrations",
                        "body": (
                            "CONTEXT: The database schema is the foundation of the entire pipeline. "
                            "No other Sprint 1 issue can proceed without this.\n\n"
                            "ACCEPTANCE CRITERIA:\n"
                            "- All tables created with correct column types, constraints, and indexes\n"
                            "- Migration runs without errors on a fresh PostgreSQL instance\n"
                            "- CI pipeline runs the migration script on every PR"
                        ),
                        "labels": ["database", "backend", "infra"],
                        "story_points": 3,
                    }
                ],
                "sprints": [
                    {
                        "name": "Sprint 1 — Foundation",
                        "issue_titles": ["Create PostgreSQL schema and run initial migrations"],
                    }
                ],
                "definition_of_done": [
                    "All API endpoints return expected HTTP status codes verified by the Postman collection running in CI",
                    "Unit test coverage ≥70% on all service-layer functions measured by pytest-cov",
                    "Zero P0/P1 errors in Sentry for 48 hours post-deployment on the staging environment",
                ],
                "tech_debt_risks": [
                    "The synchronous save_artifact call in db.py will block the thread pool at >200 concurrent sessions — migrate to full async SQLAlchemy before 1k DAU"
                ],
                "team_size_recommended": "3 engineers: 1 backend (FastAPI/DB), 1 frontend (Next.js), 1 fullstack/DevOps",
            }
        else:
            raw_dict = await query_groq(
                _EM_SYSTEM,
                user_prompt,
                IssuesAndSprintPlan,
                api_key=api_key,
                model="llama-3.3-70b-versatile",
                timeout=15.0,
                max_attempts=1,
            )
            # Safe parse — force keys to exist so Pydantic never crashes
            if not isinstance(raw_dict.get("issues"), list):
                raw_dict["issues"] = []
            if not isinstance(raw_dict.get("sprints"), list):
                raw_dict["sprints"] = []
            if not isinstance(raw_dict.get("definition_of_done"), list):
                raw_dict["definition_of_done"] = []
            if not isinstance(raw_dict.get("tech_debt_risks"), list):
                raw_dict["tech_debt_risks"] = []
            if not raw_dict.get("team_size_recommended"):
                raw_dict["team_size_recommended"] = "3 engineers: 1 backend, 1 frontend, 1 fullstack"
            plan_dict = raw_dict

        plan = IssuesAndSprintPlan(**plan_dict)

        version = await asyncio.to_thread(
            save_artifact, state.session_id, "engineering_manager", plan_dict
        )
        await asyncio.to_thread(
            add_decision_log,
            state.session_id,
            "engineering_manager",
            "Compiled issues backlog and sprint timeline.",
        )

        # Trigger GitHub integration in background — must NOT block the UI/pipeline
        if state.github_repo:
            try:
                from tools.github import create_github_issues_bulk

                issues_list = [
                    iss.model_dump() if hasattr(iss, "model_dump") else iss
                    for iss in plan.issues
                ]
                task = asyncio.create_task(
                    create_github_issues_bulk(
                        state.github_repo, 
                        issues_list, 
                        token=state.github_token
                    )
                )
                task.add_done_callback(
                    lambda t: (
                        logger.error("GitHub sync failed: %s", t.exception())
                        if t.exception()
                        else logger.info("GitHub sync completed successfully.")
                    )
                )
                await asyncio.to_thread(
                    add_decision_log,
                    state.session_id,
                    "engineering_manager",
                    f"Started background sync to GitHub repository: {state.github_repo}",
                )
            except Exception as github_err:
                logger.warning("Failed to start GitHub sync: %s", github_err)

        return {
            "engineering_manager": plan,
            "stages": {"engineering_manager": {"status": "complete", "version": version}},
        }

    except Exception as exc:
        logger.exception("Error in engineering_manager_node: %s", exc)
        if "engineering_manager" not in failed_stages:
            failed_stages.append("engineering_manager")
        return {
            "stages": {"engineering_manager": {"status": "failed", "version": 0}},
            "failed_stages": failed_stages,
        }


# ---------------------------------------------------------------------------
# Node: Marketing
# ---------------------------------------------------------------------------

# ── UPGRADED SYSTEM PROMPT ─────────────────────────────────────────────────
_MARKETING_SYSTEM = """\
You are a world-class CMO and Growth Strategist who has taken 3 B2B SaaS startups \
from $0 to $5M ARR. You combine David Ogilvy's copywriting discipline, \
Sean Ellis's growth hacking rigour, and Alex Hormozi's value-stack frameworks. \
Every word of copy you write makes the ICP feel like they are LOSING something \
real and irreplaceable by not signing up today.

Before writing a single word, you lock in the ICP (Ideal Customer Profile): \
the ONE specific person with the ONE specific hair-on-fire problem this product solves. \
Every piece of copy speaks directly to that person — their frustration, their aspiration, \
their Monday morning.

GTM STRATEGY FRAMEWORK — apply ALL layers:

1. LANDING COPY — Problem → Agitate → Solve (PAS Framework)
   HEADLINE: A bold, specific transformation promise. Not what the product IS — \
what the user BECOMES. Under 10 words. No buzzwords ("AI-powered", "next-gen", \
"revolutionary" are BANNED).
   SUBHEADLINE: WHO it is for + WHAT they lose by waiting. 1 sentence.
   3 VALUE PROPS: Each one is a specific, measurable outcome — not a feature description. \
Format: "[Verb] [specific outcome] [timeframe or constraint]"
   CTA: Action-oriented, specific. Not "Get Started." Prefer "Generate My Founder Package Free."
   Format the landing_copy string as: \
"HEADLINE: [text] | SUBHEADLINE: [text] | VALUE PROP 1: [text] | \
VALUE PROP 2: [text] | VALUE PROP 3: [text] | CTA: [text]"

2. LINKEDIN POST — Hook → Insight → CTA
   Line 1 (Hook): Must NOT start with "I" or the company name. \
Must create pattern interruption — a surprising stat, a counterintuitive claim, \
or a relatable frustration.
   Body: Share one specific, counterintuitive insight that proves you understand this market \
better than anyone. Max 150 words total.
   CTA: Specific action (comment "PILOT", DM "FOUNDER", link in bio).

3. EMAIL CAMPAIGN — Subject + Body (urgency-driven, max 120 words)
   Subject line: Use curiosity or urgency. No clickbait. Must directly relate to the ICP's \
pain point.
   Body: One clear job — get the reader to take ONE action. No feature lists. \
Pure value + social proof hint + CTA.

4. EMAIL DRIP SEQUENCE — EXACTLY 5 emails
   Day 0:  Welcome + core value prop. Make them feel they made the right decision.
   Day 3:  Social proof or use-case story. Show, don't tell.
   Day 7:  Key feature spotlight — the one feature that creates the "aha moment."
   Day 14: Objection handling. Address the #1 reason people don't upgrade.
   Day 30: Urgency + upgrade prompt. FOMO + loss aversion.
   Each email: {goal, send_day, subject, body}

5. PRICING TIERS — Good/Better/Best anchoring
   SHOW the premium tier first to make the basic tier look like a deal.
   Tier 1 (Basic/Free): Limited but genuinely useful. Enough to prove value.
   Tier 2 (Pro/Premium): Must feel like an obvious upgrade given the price delta.
   Use price anchoring: show the annual equivalent of monthly cost.
   Each tier: {model, price, features (array of specific outcome strings)}

6. 90-DAY PLAN — 3 phases with SPECIFIC tactics and SUCCESS METRICS
   Month 1: Foundation — ICP validation, waitlist building, 20 customer interviews, \
organic seeding.
   Month 2: Traction — Product Hunt launch, 3 publishable case studies, \
first 100 active users, content SEO foundation.
   Month 3: Scale — Paid acquisition test ($1k budget), partnership pipeline, \
referral program, content calendar launch.
   Each phase: one string with phase name + 2-3 specific tactics + 1 success metric.

7. LAUNCH CHANNELS — 2-3 channels with specific tactics
   Each channel: {channel, tactic, expected_reach, success_metric}
   Tactics must be SPECIFIC ACTIONS — not "post on social media."
   Example tactic: "Submit to Product Hunt on a Tuesday at 12:01am PST with \
a pre-built upvote coalition of 50 beta users and a maker comment thread."

COPY QUALITY NON-NEGOTIABLES:
   - ZERO generic phrases: "AI-powered", "cutting-edge", "revolutionise", "seamless", \
"next-generation", "innovative solution" — these are BANNED
   - ZERO HTML tags in any copy field
   - landing_copy HEADLINE must be under 10 words
   - linkedin_post first line MUST NOT start with "I" or company name
   - email_campaign body MUST be under 120 words

OUTPUT RULES:
   - Return ONLY a valid JSON object. No markdown. No preamble. No text outside the JSON.
   - Required keys:
     "landing_copy"    → string (PAS format with labeled sections as specified above)
     "linkedin_post"   → string (hook → insight → CTA, max 200 words, no HTML)
     "email_campaign"  → string (subject line + body, under 120 words, no HTML)
     "pricing_tiers"   → array of exactly 2 objects: {model, price, features}
     "email_sequence"  → array of EXACTLY 5 objects: {goal, send_day, subject, body}
     "ninety_day_plan" → array of exactly 3 strings (Month 1/2/3 with specific tactics \
and one success metric each)
     "launch_channels" → array of 2-3 objects: {channel, tactic, expected_reach, success_metric}
"""
# ──────────────────────────────────────────────────────────────────────────


async def marketing_node(state: GraphState) -> Dict[str, Any]:
    stages = dict(state.stages or {})
    failed_stages = list(state.failed_stages or [])
    stages["marketing"] = {"status": "running", "version": 0}

    idea_val = state.idea
    prd = state.product_manager
    prd_str = safe_serialize(prd) if prd else "No PRD available."
    user_prompt = (
        f"Startup Idea: '{idea_val}'\n\n"
        f"Product Requirement Document (PRD):\n{prd_str}"
    )

    try:
        api_key = settings.GROQ_API_KEY
        if not api_key:
            assets_dict = {
                "landing_copy": (
                    "HEADLINE: Validate your startup idea before you write a line of code | "
                    "SUBHEADLINE: For solo founders who are tired of spending weeks on research "
                    "that an investor dismisses in 30 seconds | "
                    "VALUE PROP 1: Generate investor-ready market research in under 10 minutes | "
                    "VALUE PROP 2: Get a complete PRD, architecture, and sprint plan from a single prompt | "
                    "VALUE PROP 3: Ship your MVP kickoff 4 weeks faster than your competition | "
                    "CTA: Generate My Founder Package — Free (Mocked)"
                ),
                "linkedin_post": (
                    "98% of startup founders waste their first month building the wrong thing.\n\n"
                    "Not because they lack talent. Because they skip the 3 documents that would have told them.\n\n"
                    "A real market research report. A lean PRD. An architecture spec.\n\n"
                    "Most teams spend 4-6 weeks on these. We built a system that does it in 10 minutes.\n\n"
                    "Drop 'PILOT' in the comments and I'll DM you access. (Mocked)"
                ),
                "email_campaign": (
                    "Subject: Your competitors validated their idea last week. Did you?\n\n"
                    "The founders who win don't move fastest — they move with the right information first.\n\n"
                    "Blueprint gives you a VC-grade market research report, a production-ready PRD, "
                    "and a full sprint plan from a single idea prompt.\n\n"
                    "The next 50 founders get free access. → [Get My Package] (Mocked)"
                ),
                "pricing_tiers": [
                    {
                        "model": "Pro",
                        "price": "$49/month (or $39/month billed annually)",
                        "features": [
                            "Unlimited founder packages",
                            "GitHub auto-sync for sprint issues",
                            "PDF export for investor decks",
                            "Priority Groq model access",
                        ],
                    },
                    {
                        "model": "Free",
                        "price": "$0/month",
                        "features": [
                            "3 founder packages per month",
                            "All 6 AI agents included",
                            "Basic export (JSON)",
                        ],
                    },
                ],
                "email_sequence": [
                    {
                        "goal": "Welcome and establish core value",
                        "send_day": "Day 0",
                        "subject": "Your founder package is ready — here's what just happened",
                        "body": "You just did in 10 minutes what used to take 4 weeks. Here's how to use your Blueprint package to run your first investor call this week.",
                    },
                    {
                        "goal": "Social proof",
                        "send_day": "Day 3",
                        "subject": "How [Founder Name] pitched a VC on Day 4 using Blueprint",
                        "body": "Last week a solo founder used Blueprint to generate a market research report that a Sequoia scout called 'the most concise TAM breakdown I've seen from a pre-seed team.'",
                    },
                    {
                        "goal": "Feature spotlight",
                        "send_day": "Day 7",
                        "subject": "The one agent most founders skip (and regret)",
                        "body": "The Engineering Manager agent doesn't just make GitHub issues. It maps sprint dependencies so your team is never blocked. Here's how to read the output.",
                    },
                    {
                        "goal": "Objection handling",
                        "send_day": "Day 14",
                        "subject": "Is Blueprint just a glorified ChatGPT wrapper?",
                        "body": "Fair question. Here's what's different: 6 specialised agents with inter-agent context passing, a human-in-the-loop gate for high-risk ideas, and structured JSON output your engineering team can actually use.",
                    },
                    {
                        "goal": "Urgency and upgrade",
                        "send_day": "Day 30",
                        "subject": "Your 3 free packages reset in 48 hours",
                        "body": "You've used Blueprint to validate your idea. Now the Pro plan unlocks unlimited packages + GitHub sync. Upgrade before your counter resets and save 20% with annual billing.",
                    },
                ],
                "ninety_day_plan": [
                    "Month 1 — Foundation: Run 20 ICP customer interviews to validate copy. Build a 500-person waitlist via Twitter threads and Indie Hackers. Success metric: 500 waitlist signups.",
                    "Month 2 — Traction: Launch on Product Hunt (target Top 5 of the day). Publish 3 founder case studies. Reach 100 active users generating packages. Success metric: 100 MAU.",
                    "Month 3 — Scale: Test $1k paid acquisition on Twitter/LinkedIn targeting solo founders. Launch a referral programme (give 1 month free, get 1 month free). Success metric: 15% free-to-paid conversion.",
                ],
                "launch_channels": [
                    {
                        "channel": "Product Hunt",
                        "tactic": "Launch Tuesday 12:01am PST with pre-built upvote coalition of 50 beta users, a maker comment thread addressing the top 3 skeptic questions, and a launch video under 90 seconds.",
                        "expected_reach": "5,000-15,000 unique visitors on launch day",
                        "success_metric": "Top 5 Product of the Day",
                    },
                    {
                        "channel": "Indie Hackers",
                        "tactic": "Post a 'building in public' milestone post sharing the Blueprint architecture and first 10 user stories with raw revenue screenshots.",
                        "expected_reach": "2,000-5,000 targeted solo founder views",
                        "success_metric": "50 upvotes and 200 profile clicks",
                    },
                ],
            }
        else:
            assets_dict = await query_groq_creative(
                _MARKETING_SYSTEM,
                user_prompt,
                MarketingAssets,
                api_key=api_key,
                model="llama-3.3-70b-versatile",
            )
            # Guard against missing optional fields
            if not isinstance(assets_dict.get("pricing_tiers"), list):
                assets_dict["pricing_tiers"] = []
            if not isinstance(assets_dict.get("email_sequence"), list):
                assets_dict["email_sequence"] = []
            if not isinstance(assets_dict.get("ninety_day_plan"), list):
                assets_dict["ninety_day_plan"] = []
            if not isinstance(assets_dict.get("launch_channels"), list):
                assets_dict["launch_channels"] = []

        assets = MarketingAssets(**assets_dict)

        version = await asyncio.to_thread(
            save_artifact, state.session_id, "marketing", assets_dict
        )
        await asyncio.to_thread(
            add_decision_log,
            state.session_id,
            "marketing",
            "Generated promotional copy and launch assets.",
        )
        return {
            "marketing": assets,
            "stages": {"marketing": {"status": "complete", "version": version}},
        }

    except Exception as exc:
        logger.exception("Error in marketing_node: %s", exc)
        if "marketing" not in failed_stages:
            failed_stages.append("marketing")
        return {
            "stages": {"marketing": {"status": "failed", "version": 0}},
            "failed_stages": failed_stages,
        }


# ---------------------------------------------------------------------------
# Node: Join (fan-in)
# ---------------------------------------------------------------------------

async def join_node(state: GraphState) -> Dict[str, Any]:
    """Wait for all parallel branches to complete, then resolve final status."""
    stages_dict = state.stages or {}
    all_stages = [
        "startup_advisor",
        "market_research",
        "product_manager",
        "architect",
        "engineering_manager",
        "marketing",
    ]

    all_done = all(
        stages_dict.get(s, {}).get("status") in {"complete", "failed"}
        for s in all_stages
    )

    if not all_done:
        return {"status": "running"}

    has_failures = state.failed_stages or any(
        stages_dict.get(s, {}).get("status") == "failed" for s in all_stages
    )
    return {"status": "failed" if has_failures else "complete"}


# ---------------------------------------------------------------------------
# Conditional Routing
# ---------------------------------------------------------------------------

def router_after_advisor(state: GraphState) -> str:
    """Route back to advisor on revision, otherwise advance to market research."""
    if state.gate_decision == "revise":
        return "startup_advisor"
    return "market_research"


# ---------------------------------------------------------------------------
# Build StateGraph
# ---------------------------------------------------------------------------

def create_graph(checkpointer=None):
    """Compile and return the full LangGraph workflow."""
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
            "market_research": "market_research",
        },
    )
    workflow.add_edge("market_research", "product_manager")
    workflow.add_edge("product_manager", "architect")
    workflow.add_edge("product_manager", "marketing")
    workflow.add_edge("architect", "engineering_manager")
    workflow.add_edge("engineering_manager", "join")
    workflow.add_edge("marketing", "join")
    workflow.add_edge("join", END)

    return workflow.compile(checkpointer=checkpointer)

# ✅ P10: R1–R10 applied.