from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Annotated

# --- Reducers for parallel state merging ---

def reduce_dict(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged

def reduce_list(left: Optional[List[Any]], right: Optional[List[Any]]) -> List[Any]:
    merged = list(left or [])
    for item in (right or []):
        if item not in merged:
            merged.append(item)
    return merged

# --- Agent Output Models ---
# ... (same as before) ...
class ValidationResult(BaseModel):
    verdict: str
    risk_score: float  # 0.0-1.0
    reasoning: str
    red_flags: List[str]

class MarketResearchReport(BaseModel):
    tam_estimate: str
    competitors: List[Dict[str, Any]]  # {name, description, url}
    trends: List[str]
    sources: List[str]

class PRD(BaseModel):
    problem_statement: str
    user_stories: List[str]
    features: List[Dict[str, Any]]  # {name, description, priority}
    roadmap_phases: List[Dict[str, Any]]  # {name, items}

class ArchitectureSpec(BaseModel):
    db_schema_sql: str
    db_schema_mermaid: str
    api_endpoints: List[Dict[str, Any]]  # {method, path, description}
    system_design_notes: str

class IssuesAndSprintPlan(BaseModel):
    issues: List[Dict[str, Any]]  # {title, body, labels}
    sprints: List[Dict[str, Any]]  # {name, issue_titles}

class MarketingAssets(BaseModel):
    landing_copy: str
    linkedin_post: str
    email_campaign: str

# --- Graph State ---

class GraphState(BaseModel):
    session_id: str
    startup_name: str
    idea: str
    github_repo: str
    status: str = "running"  # "running" | "awaiting_gate" | "complete" | "failed"
    
    # Track status and version of each stage
    stages: Annotated[Dict[str, Any], reduce_dict] = Field(default_factory=dict)

    # Artifact outputs mapping to stage_name
    startup_advisor: Optional[ValidationResult] = None
    market_research: Optional[MarketResearchReport] = None
    product_manager: Optional[PRD] = None
    architect: Optional[ArchitectureSpec] = None
    engineering_manager: Optional[IssuesAndSprintPlan] = None
    marketing: Optional[MarketingAssets] = None

    # Track failures
    failed_stages: Annotated[List[str], reduce_list] = Field(default_factory=list)

    # Gate management (interrupts payload)
    gate_decision: Optional[str] = None  # "continue" | "revise"
    revised_idea: Optional[str] = None
