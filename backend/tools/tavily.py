import sys
import os
import httpx
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

async def search_tavily(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search Tavily API directly using httpx.
    """
    if not settings.TAVILY_API_KEY:
        raise ValueError("TAVILY_API_KEY is not set.")
    
    payload = {
        "api_key": settings.TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(TAVILY_SEARCH_URL, json=payload)
        response.raise_for_status()
        return response.json()
