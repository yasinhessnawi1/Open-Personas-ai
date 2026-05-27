"""``web_fetch`` built-in tool — fetch a URL and extract readable content.

Uses :mod:`httpx` (already a core dep) for the HTTP request and
:mod:`trafilatura` for HTML content extraction (D-03-12). Non-HTML
responses pass through with light cleanup via ``httpx.Response.text``.

Truncation: if extracted text exceeds ``max_chars``, truncate to
``max_chars`` and set ``ToolResult.truncated=True`` (D-03-3).

Scheme allow-list (``http``/``https`` only) is enforced; full SSRF guard
is deferred to spec 11 launch checklist (D-03-11).

`trafilatura.extract()` is called with explicit kwargs locked in by D-03-24
to keep the tool's behaviour stable across upstream version changes.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
import trafilatura

from persona.logging import get_logger
from persona.schema.tools import ToolResult
from persona.tools.protocol import AsyncTool, tool

__all__ = ["make_web_fetch_tool"]

_logger = get_logger("tools.web_fetch")

_DEFAULT_TIMEOUT_S = 30.0
_ALLOWED_SCHEMES = ("http", "https")


def _extract_readable(html: str) -> str:
    """Run trafilatura with the kwargs locked in by D-03-24.

    Returns the extracted text, or empty string if nothing extractable.
    """
    extracted = trafilatura.extract(
        html,
        output_format="txt",
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    return extracted or ""


def make_web_fetch_tool(
    *,
    http: httpx.AsyncClient | None = None,
) -> AsyncTool:
    """Build the ``web_fetch`` :class:`AsyncTool`.

    Args:
        http: Optional pre-built :class:`httpx.AsyncClient`. If ``None``, a
            client is constructed per call with a 30s timeout. Tests inject
            a mock client; callers (e.g., the runtime) may inject a shared
            client to amortise connection setup.

    Returns:
        An :class:`AsyncTool` named ``web_fetch``. Failures are returned as
        ``ToolResult(is_error=True, content=...)`` — never raised.
    """

    @tool(
        name="web_fetch",
        description="Fetch a URL and extract its readable text content.",
    )
    async def web_fetch(url: str, max_chars: int = 4000) -> ToolResult:
        # Scheme guard (D-03-11). Full SSRF defense lives in spec 11.
        try:
            parsed = urlparse(url)
        except ValueError as e:
            return ToolResult(
                tool_name="web_fetch",
                content=f"Invalid URL: {e}",
                is_error=True,
            )
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return ToolResult(
                tool_name="web_fetch",
                content=f"Only http/https URLs allowed; got scheme {parsed.scheme!r}",
                is_error=True,
            )
        if not parsed.netloc:
            return ToolResult(
                tool_name="web_fetch",
                content="URL missing host component",
                is_error=True,
            )

        owns_client = http is None
        client = (
            http
            if http is not None
            else httpx.AsyncClient(timeout=httpx.Timeout(_DEFAULT_TIMEOUT_S))
        )

        try:
            try:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                _logger.warning("web_fetch http error", url=url, status=status)
                return ToolResult(
                    tool_name="web_fetch",
                    content=f"HTTP {status}: {e.response.reason_phrase or 'error'}",
                    is_error=True,
                )
            except httpx.TimeoutException as e:
                _logger.warning("web_fetch timeout", url=url, error=type(e).__name__)
                return ToolResult(
                    tool_name="web_fetch",
                    content=f"Timeout fetching {url}: {type(e).__name__}",
                    is_error=True,
                )
            except httpx.HTTPError as e:
                _logger.warning("web_fetch network error", url=url, error=type(e).__name__)
                return ToolResult(
                    tool_name="web_fetch",
                    content=f"Network error fetching {url}: {type(e).__name__}: {e}",
                    is_error=True,
                )

            # Decide whether to run trafilatura or pass through.
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type:
                text = _extract_readable(response.text)
                if not text:
                    # Empty extraction — usually JavaScript-heavy page.
                    _logger.debug("web_fetch empty extraction", url=url)
                    return ToolResult(
                        tool_name="web_fetch",
                        content="",
                        truncated=False,
                        data={"url": url, "content_type": content_type, "extracted": False},
                    )
            else:
                text = response.text

        finally:
            if owns_client:
                await client.aclose()

        # Truncation per D-03-3 / D-03-16 pattern.
        if len(text) > max_chars:
            return ToolResult(
                tool_name="web_fetch",
                content=text[:max_chars],
                truncated=True,
                data={
                    "url": url,
                    "content_type": content_type,
                    "extracted": "html" in content_type,
                    "original_length": len(text),
                },
            )

        return ToolResult(
            tool_name="web_fetch",
            content=text,
            truncated=False,
            data={
                "url": url,
                "content_type": content_type,
                "extracted": "html" in content_type,
            },
        )

    return web_fetch
