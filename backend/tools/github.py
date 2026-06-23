# GitHub Tool Integration
import httpx
import logging
from typing import Dict, Any, List, Optional
from config import settings

logger = logging.getLogger(__name__)

async def create_github_issue(repo: str, title: str, body: str, labels: Optional[List[str]] = None, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    actual_token = token or settings.GITHUB_TOKEN
    if not actual_token:
        logger.warning("No GitHub token provided. Skipping issue creation.")
        return None
        
    if not repo or "/" not in repo:
        logger.warning(f"Invalid repository format: '{repo}'. Expected 'owner/repo'. Skipping issue creation.")
        return None

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {actual_token}", # Bearer is required for fine-grained PATs or OAuth tokens
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AI-Founder-OS"
    }
    payload = {
        "title": title,
        "body": body,
        "labels": labels or []
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 201:
                logger.info(f"Successfully created GitHub issue: '{title}' in {repo}")
                return response.json()
            else:
                # This will print the EXACT error from GitHub to your backend terminal
                logger.error(f"Failed to create GitHub issue. Status: {response.status_code}, Response: {response.text}")
                return None
    except Exception as e:
        logger.exception(f"Exception occurred while creating GitHub issue: {e}")
        return None

async def create_github_issues_bulk(repo: str, issues: List[Any], token: Optional[str] = None) -> List[Dict[str, Any]]:
    created = []
    for issue in issues:
        if hasattr(issue, 'model_dump'):
            issue = issue.model_dump()
            
        res = await create_github_issue(
            repo=repo,
            title=issue.get("title", "Untitled Issue"),
            body=issue.get("body", ""),
            labels=issue.get("labels", []),
            token=token
        )
        if res:
            created.append(res)
    return created