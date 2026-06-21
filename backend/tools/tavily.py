import sys
import os
from typing import Dict, Any
from tavily import AsyncTavilyClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

async def search_tavily(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search Tavily API using the official Async SDK.
    """
    if not settings.TAVILY_API_KEY:
        raise ValueError("TAVILY_API_KEY is not set.")
    
    # Use the official async client
    client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
    
    # The SDK handles all the HTTP formatting, headers, and error handling
    response = await client.search(
        query=query,
        search_depth="basic",
        max_results=max_results,
    )
    
    return response
