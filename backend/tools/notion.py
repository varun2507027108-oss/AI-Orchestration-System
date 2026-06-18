# Notion Tool Integration
import httpx
import logging
from typing import Dict, Any, List, Optional
from config import settings

logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"

def get_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }

async def create_notion_page(startup_name: str, session_id: str) -> Optional[str]:
    """
    Create a page inside the database specified by NOTION_DATABASE_ID.
    Returns the page_id if successful.
    """
    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID:
        logger.warning("Notion token or database ID not set. Skipping Notion page creation.")
        return None

    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {
            "database_id": settings.NOTION_DATABASE_ID
        },
        "properties": {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": f"{startup_name} - AI Founder Launch ({session_id})"
                        }
                    }
                ]
            }
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=get_headers(), json=payload)
            if response.status_code == 200:
                page_data = response.json()
                page_id = page_data.get("id")
                logger.info(f"Created Notion page successfully: {page_id}")
                return page_id
            else:
                logger.error(f"Failed to create Notion page. Status: {response.status_code}, Response: {response.text}")
                return None
    except Exception as e:
        logger.exception(f"Error creating Notion page: {e}")
        return None

async def append_notion_blocks(page_id: str, blocks: List[Dict[str, Any]]) -> bool:
    """
    Append child blocks to a Notion page/block.
    """
    if not settings.NOTION_TOKEN:
        return False

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    
    # Notion API allows max 100 blocks per request
    chunk_size = 80
    for i in range(0, len(blocks), chunk_size):
        chunk = blocks[i:i + chunk_size]
        payload = {"children": chunk}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(url, headers=get_headers(), json=payload)
                if response.status_code != 200:
                    logger.error(f"Failed to append Notion blocks. Status: {response.status_code}, Response: {response.text}")
                    return False
        except Exception as e:
            logger.exception(f"Error appending Notion blocks: {e}")
            return False
            
    return True

def create_heading_block(text: str, level: int = 2) -> Dict[str, Any]:
    heading_key = f"heading_{level}"
    return {
        "object": "block",
        "type": heading_key,
        heading_key: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }

def create_paragraph_block(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }

def create_bullet_block(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }

def create_code_block(code: str, language: str = "plain text") -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": code
                    }
                }
            ],
            "language": language
        }
    }

def create_callout_block(text: str, emoji: str = "💡") -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ],
            "icon": {
                "type": "emoji",
                "emoji": emoji
            }
        }
    }

def translate_artifact_to_notion_blocks(stage_name: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Translates a stage artifact JSON payload into Notion API blocks.
    """
    blocks = []
    
    if stage_name == "startup_advisor":
        verdict = payload.get("verdict", "")
        risk_score = payload.get("risk_score", 0.0)
        reasoning = payload.get("reasoning", "")
        red_flags = payload.get("red_flags", [])
        
        blocks.append(create_heading_block("1. Startup Advisor Validation", 2))
        blocks.append(create_callout_block(f"Verdict: {verdict} (Risk Score: {risk_score})", "🛡️"))
        blocks.append(create_paragraph_block(f"Reasoning: {reasoning}"))
        if red_flags:
            blocks.append(create_heading_block("Red Flags Flagged", 3))
            for rf in red_flags:
                blocks.append(create_bullet_block(rf))
                
    elif stage_name == "market_research":
        tam = payload.get("tam_estimate", "")
        competitors = payload.get("competitors", [])
        trends = payload.get("trends", [])
        sources = payload.get("sources", [])
        
        blocks.append(create_heading_block("2. Market Research", 2))
        blocks.append(create_paragraph_block(f"TAM Estimate: {tam}"))
        
        if competitors:
            blocks.append(create_heading_block("Key Competitors", 3))
            for comp in competitors:
                blocks.append(create_bullet_block(f"{comp.get('name', '')}: {comp.get('description', '')} (Link: {comp.get('url', '')})"))
                
        if trends:
            blocks.append(create_heading_block("Market Trends", 3))
            for trend in trends:
                blocks.append(create_bullet_block(trend))
                
        if sources:
            blocks.append(create_heading_block("Sources Referenced", 3))
            for src in sources:
                blocks.append(create_bullet_block(src))
                
    elif stage_name == "product_manager":
        prob = payload.get("problem_statement", "")
        stories = payload.get("user_stories", [])
        features = payload.get("features", [])
        phases = payload.get("roadmap_phases", [])
        
        blocks.append(create_heading_block("3. Product Requirement Document (PRD)", 2))
        blocks.append(create_paragraph_block(f"Problem Statement: {prob}"))
        
        if stories:
            blocks.append(create_heading_block("User Stories", 3))
            for story in stories:
                blocks.append(create_bullet_block(story))
                
        if features:
            blocks.append(create_heading_block("Core Features", 3))
            for feat in features:
                blocks.append(create_bullet_block(f"[{feat.get('priority', 'Medium')}] {feat.get('name', '')}: {feat.get('description', '')}"))
                
        if phases:
            blocks.append(create_heading_block("Roadmap Phases", 3))
            for phase in phases:
                items_str = ", ".join(phase.get("items", []))
                blocks.append(create_bullet_block(f"{phase.get('name', '')}: {items_str}"))
                
    elif stage_name == "architect":
        sql = payload.get("db_schema_sql", "")
        mermaid = payload.get("db_schema_mermaid", "")
        endpoints = payload.get("api_endpoints", [])
        notes = payload.get("system_design_notes", "")
        
        blocks.append(create_heading_block("4. System Architecture Specification", 2))
        blocks.append(create_paragraph_block(f"Notes: {notes}"))
        
        if sql:
            blocks.append(create_heading_block("Database SQL Schema", 3))
            blocks.append(create_code_block(sql, "sql"))
            
        if mermaid:
            blocks.append(create_heading_block("Mermaid Diagram", 3))
            blocks.append(create_code_block(mermaid, "mermaid"))
            
        if endpoints:
            blocks.append(create_heading_block("API Endpoints Contract", 3))
            for ep in endpoints:
                blocks.append(create_bullet_block(f"{ep.get('method', 'GET')} {ep.get('path', '')} - {ep.get('description', '')}"))
                
    elif stage_name == "engineering_manager":
        issues = payload.get("issues", [])
        sprints = payload.get("sprints", [])
        
        blocks.append(create_heading_block("5. Issues and Sprint Plan", 2))
        
        if sprints:
            blocks.append(create_heading_block("Sprints Plan", 3))
            for sp in sprints:
                issues_str = ", ".join(sp.get("issue_titles", []))
                blocks.append(create_bullet_block(f"{sp.get('name', '')}: {issues_str}"))
                
        if issues:
            blocks.append(create_heading_block("GitHub Issues List", 3))
            for issue in issues:
                labels_str = ", ".join(issue.get("labels", []))
                blocks.append(create_bullet_block(f"Issue: '{issue.get('title', '')}' [Labels: {labels_str}] - {issue.get('body', '')}"))
                
    elif stage_name == "marketing":
        copy = payload.get("landing_copy", "")
        post = payload.get("linkedin_post", "")
        campaign = payload.get("email_campaign", "")
        
        blocks.append(create_heading_block("6. Marketing Copy & Assets", 2))
        
        if copy:
            blocks.append(create_heading_block("Landing Page Headline & Copy", 3))
            blocks.append(create_paragraph_block(copy))
            
        if post:
            blocks.append(create_heading_block("LinkedIn Launch Post", 3))
            blocks.append(create_paragraph_block(post))
            
        if campaign:
            blocks.append(create_heading_block("Email Campaign Copy", 3))
            blocks.append(create_paragraph_block(campaign))
            
    return blocks
