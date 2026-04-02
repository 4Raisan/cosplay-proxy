"""Cosplay proxy — server-side web tools.

Implements the ``web_search`` and ``web_fetch`` tools that Claude Code
declares as ``web_search_20250305`` / ``web_fetch_20250404``. The model calls
them like normal functions and the proxy executes them in a tool loop.
"""

from __future__ import annotations

import asyncio
import html as html_module
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from config.web_voice import WebVoiceManager

SERVER_TOOL_NAMES = {"web_search", "web_fetch"}
DEFAULT_FETCH_MAX = 8000
SEARCH_TIMEOUT = 15.0
FETCH_TIMEOUT = 30.0

# Function definitions injected upstream so the model can call these tools.
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information. Returns a list of relevant "
            "results with titles, URLs, and short snippets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 5).",
                },
            },
            "required": ["query"],
        },
    },
}

WEB_FETCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": (
            "Fetch the contents of a URL and return its visible text. Use for "
            "reading articles or pages identified by web_search."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch."},
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 8000).",
                },
            },
            "required": ["url"],
        },
    },
}


def enabled() -> bool:
    """Whether server web tools are enabled by configuration."""
    return WebVoiceManager().get().enable_web_search


def upstream_tool_defs() -> list[dict[str, Any]]:
    """Return the tool definitions injected into the upstream request."""
    if not enabled():
        return []
    return [WEB_SEARCH_TOOL, WEB_FETCH_TOOL]


async def execute_server_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a server tool and return the text result for the model."""
    if name == "web_search":
        query = str(arguments.get("query", ""))
        if not query:
            return "Error: web_search requires a 'query' argument."
        max_results = int(arguments.get("max_results", 5) or 5)
        return await _web_search(query, max_results)
    if name == "web_fetch":
        url = str(arguments.get("url", ""))
        if not url:
            return "Error: web_fetch requires a 'url' argument."
        max_length = int(arguments.get("max_length", DEFAULT_FETCH_MAX) or DEFAULT_FETCH_MAX)
        return await _web_fetch(url, max_length)
    return f"Unknown server tool: {name}"


# ---------------------------------------------------------------------------
# Web search (DuckDuckGo HTML)
# ---------------------------------------------------------------------------

_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
)
_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>'
)


async def _web_search(query: str, max_results: int) -> str:
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                return f"Web search failed with HTTP {resp.status_code}."
            page = resp.text
    except httpx.HTTPError as exc:
        return f"Web search failed: {type(exc).__name__}."

    titles = _RESULT_RE.findall(page)
    links = [href for href, _ in titles]
    title_texts = [_strip_tags(t) for _, t in titles]
    snippets = [_strip_tags(s) for s in _SNIPPET_RE.findall(page)]

    results: list[str] = []
    for i in range(min(max_results, len(titles))):
        real_url = _decode_result_url(links[i]) if i < len(links) else ""
        snippet = snippets[i] if i < len(snippets) else ""
        results.append(
            f"{i + 1}. {title_texts[i]}\n   URL: {real_url}\n   {snippet}"
        )

    if not results:
        return f"No results found for: {query}"
    return "\n\n".join(results)


def _decode_result_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    uddg = query.get("uddg")
    if uddg:
        return uddg[0]
    return href


def _strip_tags(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw)
    return html_module.unescape(text).strip()


# ---------------------------------------------------------------------------
# Web fetch
# ---------------------------------------------------------------------------


async def _web_fetch(url: str, max_length: int) -> str:
    if not url.startswith(("http://", "https://")):
        return "Error: web_fetch only supports http/https URLs."

    settings = WebVoiceManager().get()
    if not settings.allow_private_network and not await _is_public(url):
        return "Error: blocked private or local address (web_fetch to private networks is disabled)."

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                return f"Web fetch failed with HTTP {resp.status_code}."
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type:
                text = _html_to_text(resp.text)
            else:
                text = resp.text
    except httpx.HTTPError as exc:
        return f"Web fetch failed: {type(exc).__name__}."

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_length:
        text = text[:max_length] + "\n...[truncated]"
    return text or "No readable content found."


def _html_to_text(page: str) -> str:
    page = re.sub(r"<script[\s\S]*?</script>", " ", page, flags=re.IGNORECASE)
    page = re.sub(r"<style[\s\S]*?</style>", " ", page, flags=re.IGNORECASE)
    page = re.sub(r"<br\s*/?>", "\n", page, flags=re.IGNORECASE)
    page = re.sub(r"</(p|div|li|h[1-6]|tr|blockquote)>", "\n", page, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", page)
    text = html_module.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


async def _is_public(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = await asyncio.get_event_loop().getaddrinfo(
            host, None, family=socket.AF_INET
        )
    except socket.gaierror:
        return False
    for info in infos[:8]:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    return True
