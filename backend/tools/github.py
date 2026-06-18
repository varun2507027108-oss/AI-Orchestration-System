# GitHub Tool Integration
import httpx
import logging
from typing import Dict, Any, List, Optional
from config import settings

logger = logging.getLogger(__name__)

async def create_github_issue(repo: str, title: str, body: str, labels: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """
    Create a GitHub issue in the specified repository.
    repo format: "owner/repo"
    """
    if not settings.GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN is not configured. Skipping issue creation.")
        return None
        
    if not repo or "/" not in repo:
        logger.warning(f"Invalid repository format: '{repo}'. Expected 'owner/repo'. Skipping issue creation.")
        return None

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Founder-OS"
    }
    payload = {
        "title": title,
        "body": body,
        "labels": labels or []
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 201:
                logger.info(f"Successfully created GitHub issue: '{title}' in {repo}")
                return response.json()
            else:
                logger.error(f"Failed to create GitHub issue. Status code: {response.status_code}, Response: {response.text}")
                return None
    except Exception as e:
        logger.exception(f"Exception occurred while creating GitHub issue: {e}")
        return None

async def create_github_issues_bulk(repo: str, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Create multiple issues in bulk.
    """
    created = []
    for issue in issues:
        res = await create_github_issue(
            repo=repo,
            title=issue.get("title", "Untitled Issue"),
            body=issue.get("body", ""),
            labels=issue.get("labels", [])
        )
        if res:
            created.append(res)
    return created
