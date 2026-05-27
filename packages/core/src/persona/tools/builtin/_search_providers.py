"""Web-search provider implementations behind a small Protocol (D-03-9).

Brave is the v0.1 default (free tier; spec §6.1). Tavily and SerpAPI are
explicit stubs raising ``NotImplementedError`` — adding them later is one
file change per provider.

Endpoints, headers, and response shapes documented in research.md §6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import httpx

__all__ = [
    "BraveSearchProvider",
    "SearchResult",
    "SerpAPISearchProvider",
    "TavilySearchProvider",
    "_SearchProvider",
]


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One result row — common shape across providers."""

    title: str
    url: str
    snippet: str


@runtime_checkable
class _SearchProvider(Protocol):
    """Internal Protocol for swappable search backends (D-03-9)."""

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Execute the search and return up to ``max_results`` rows."""
        ...


# Section: Brave Search default provider


_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    """Brave Search API client.

    Free tier: 1 req/s, 2000 req/month (research §6.1). Requires
    ``X-Subscription-Token`` header. Response shape: ``web.results[]`` with
    ``title``, ``url``, ``description``.
    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        params = {
            "q": query,
            "count": str(min(max_results, 20)),  # Brave cap.
        }
        headers = {
            "X-Subscription-Token": self._api_key,
            "Accept": "application/json",
        }
        response = await self._http.get(_BRAVE_ENDPOINT, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        results: list[SearchResult] = []
        for row in (data.get("web", {}).get("results", []) or [])[:max_results]:
            results.append(
                SearchResult(
                    title=row.get("title", ""),
                    url=row.get("url", ""),
                    snippet=row.get("description", ""),
                )
            )
        return results


# Section: Tavily stub provider


class TavilySearchProvider:
    """Tavily Search stub. Tracked as future work (D-03-9)."""

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        msg = "Tavily provider not yet wired; tracked as future work (D-03-9)"
        raise NotImplementedError(msg)


# Section: SerpAPI stub provider


class SerpAPISearchProvider:
    """SerpAPI Search stub. Tracked as future work (D-03-9)."""

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        msg = "SerpAPI provider not yet wired; tracked as future work (D-03-9)"
        raise NotImplementedError(msg)
