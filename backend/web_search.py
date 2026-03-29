"""
Wikipedia-based medical web search for MedGate.

Provides a web_search tool that cloud models can call to look up
diagnostic criteria, lab value interpretation, treatment guidelines, etc.
Uses the Wikipedia REST API (no auth needed, no rate limits for our volume).
"""

from __future__ import annotations

import logging
import httpx

logger = logging.getLogger(__name__)

# In-memory cache — persists for server lifetime, no TTL needed for demo
_cache: dict[str, dict] = {}

WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"


async def web_search(query: str) -> dict:
    """Search Wikipedia for medical reference information.

    Two-step: keyword search → fetch summaries of top results.

    Returns:
        {
            "query": str,
            "results": [{"title": str, "extract": str, "url": str}],
            "source": "wikipedia",
        }
    """
    if query in _cache:
        return _cache[query]

    try:
        result = await _do_search(query)
    except Exception as e:
        logger.warning("Web search failed for %r: %s", query, e)
        result = {"query": query, "results": [], "source": "wikipedia"}

    _cache[query] = result
    return result


async def _do_search(query: str) -> dict:
    """Execute the two-step Wikipedia search."""
    headers = {"User-Agent": "MedGate/1.0 (clinical-ai-demo; contact@medgate.dev)"}
    async with httpx.AsyncClient(timeout=5.0, headers=headers) as client:
        # Step 1: Search for matching articles
        search_resp = await client.get(
            WIKIPEDIA_SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 3,
                "srnamespace": 0,
            },
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()
        titles = [hit["title"] for hit in search_data.get("query", {}).get("search", [])]

        if not titles:
            return {"query": query, "results": [], "source": "wikipedia"}

        # Step 2: Fetch summaries for top 2 results
        results = []
        for title in titles[:2]:
            summary_resp = await client.get(
                f"{WIKIPEDIA_SUMMARY_URL}/{title.replace(' ', '_')}",
                headers={"Accept": "application/json"},
            )
            if summary_resp.status_code != 200:
                continue
            summary = summary_resp.json()
            extract = summary.get("extract", "")
            # Truncate to ~1500 chars to keep model context lean
            if len(extract) > 1500:
                extract = extract[:1500].rsplit(" ", 1)[0] + "..."
            results.append({
                "title": summary.get("title", title),
                "extract": extract,
                "url": summary.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"),
            })

        return {"query": query, "results": results, "source": "wikipedia"}
