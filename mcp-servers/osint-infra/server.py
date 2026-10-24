"""
osint-infra-mcp -- DNS, WHOIS, and Wayback Machine MCP server for OSINT investigations.

Tools:
  - whois_lookup: WHOIS registration data for a domain
  - dns_lookup: DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA, or ANY)
  - reverse_dns: PTR record for an IP address
  - wayback_snapshots: List archived snapshots of a URL from the Wayback Machine
  - wayback_fetch: Fetch the content of a specific Wayback Machine snapshot
  - enrich_providers / enrich: every adapter in skills/osint/scripts/lib/enrich
  - reddit_user_history / reddit_subreddit_recent: keyless Reddit reads (Arctic Shift, PullPush, RSS)
"""

import asyncio
import json
import subprocess
from datetime import datetime
from urllib.parse import quote

import httpx
from fastmcp import FastMCP

mcp = FastMCP(
    "osint-infra",
    instructions=(
        "OSINT infrastructure lookup tools for investigations. "
        "Use whois_lookup and dns_lookup for domain/IP intelligence. "
        "Use wayback_snapshots and wayback_fetch to check archived versions of pages."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_cmd(cmd: list[str], timeout: int = 15) -> str:
    """Run a shell command and return stdout. Raises on timeout or failure."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return f"ERROR: Command timed out after {timeout}s"

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        return f"ERROR (exit {proc.returncode}): {err}"

    return stdout.decode("utf-8", errors="replace").strip()


# ---------------------------------------------------------------------------
# DNS / WHOIS Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def whois_lookup(domain: str) -> str:
    """
    Look up WHOIS registration data for a domain.

    Returns registrar, creation/expiry dates, name servers, registrant info (if public).
    Useful for: domain ownership, registration history, infrastructure mapping.

    Args:
        domain: The domain to look up (e.g. "example.com"). Do not include protocol.
    """
    # Strip protocol if accidentally included
    domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    return await _run_cmd(["whois", domain], timeout=15)


@mcp.tool()
async def dns_lookup(domain: str, record_type: str = "A") -> str:
    """
    Query DNS records for a domain.

    Args:
        domain: The domain to query (e.g. "example.com").
        record_type: DNS record type -- one of: A, AAAA, MX, NS, TXT, CNAME, SOA, ANY. Default: A.
    """
    allowed = {"A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "ANY"}
    record_type = record_type.upper()
    if record_type not in allowed:
        return f"ERROR: record_type must be one of {allowed}"

    domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    return await _run_cmd(["dig", "+noall", "+answer", "+authority", domain, record_type], timeout=10)


@mcp.tool()
async def reverse_dns(ip_address: str) -> str:
    """
    Perform reverse DNS lookup on an IP address.

    Args:
        ip_address: The IP address to look up (e.g. "8.8.8.8").
    """
    return await _run_cmd(["dig", "+short", "-x", ip_address], timeout=10)


# ---------------------------------------------------------------------------
# Wayback Machine Tools
# ---------------------------------------------------------------------------

CDX_API = "https://web.archive.org/cdx/search/cdx"
WAYBACK_BASE = "https://web.archive.org/web"


@mcp.tool()
async def wayback_snapshots(
    url: str,
    from_date: str = "",
    to_date: str = "",
    limit: int = 20,
) -> str:
    """
    List archived snapshots of a URL from the Wayback Machine.

    Returns timestamps, HTTP status, and direct archive URLs.
    Useful for: checking historical versions of profiles, pages, or sites that may have changed or been deleted.

    Args:
        url: The URL to check (e.g. "example.com" or "https://example.com/page").
        from_date: Start date filter as YYYYMMDD (optional).
        to_date: End date filter as YYYYMMDD (optional).
        limit: Max number of snapshots to return (default 20, max 100).
    """
    limit = min(max(1, limit), 100)

    params = {
        "url": url,
        "output": "json",
        "limit": str(limit),
        "fl": "timestamp,original,statuscode,mimetype,digest",
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.get(CDX_API, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return f"ERROR: Wayback API returned {e.response.status_code}"
        except httpx.RequestError as e:
            return f"ERROR: Request failed -- {e}"

    data = resp.json()
    if not data or len(data) < 2:
        return f"No snapshots found for {url}"

    headers = data[0]
    rows = data[1:]

    results = []
    for row in rows:
        entry = dict(zip(headers, row))
        ts = entry.get("timestamp", "")
        # Format timestamp for readability
        try:
            dt = datetime.strptime(ts, "%Y%m%d%H%M%S")
            readable = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            readable = ts

        results.append({
            "date": readable,
            "timestamp": ts,
            "status": entry.get("statuscode", ""),
            "type": entry.get("mimetype", ""),
            "archive_url": f"{WAYBACK_BASE}/{ts}/{entry.get('original', url)}",
        })

    return json.dumps(results, indent=2)


@mcp.tool()
async def wayback_fetch(url: str, timestamp: str = "") -> str:
    """
    Fetch the text content of a Wayback Machine snapshot.

    Returns the raw text of the archived page (HTML stripped to readable text for efficiency).
    Use wayback_snapshots first to find available timestamps.

    Args:
        url: The original URL that was archived.
        timestamp: The Wayback timestamp (YYYYMMDDHHmmSS). If empty, fetches the latest snapshot.
    """
    if timestamp:
        archive_url = f"{WAYBACK_BASE}/{timestamp}id_/{url}"
    else:
        archive_url = f"{WAYBACK_BASE}/{url}"

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(archive_url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return f"ERROR: Archive returned {e.response.status_code}"
        except httpx.RequestError as e:
            return f"ERROR: Request failed -- {e}"

    content = resp.text

    # Basic HTML to text conversion (keep it simple, no extra deps)
    import re
    # Remove script and style blocks
    content = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    content = re.sub(r"<[^>]+>", " ", content)
    # Collapse whitespace
    content = re.sub(r"\s+", " ", content).strip()
    # Decode common entities
    content = content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")

    # Truncate if too long
    if len(content) > 10000:
        content = content[:10000] + "\n\n[TRUNCATED -- content exceeds 10,000 chars]"

    return content


# ---------------------------------------------------------------------------
# Reddit (keyless): Arctic Shift -> PullPush -> Reddit RSS
# Shared library lives in skills/osint/scripts/lib so the CLI
# (reddit-arctic.py) and this server cannot drift apart.
# ---------------------------------------------------------------------------

import sys as _sys
from pathlib import Path as _Path

_LIB = _Path(__file__).resolve().parents[2] / "skills" / "osint" / "scripts" / "lib"
if str(_LIB) not in _sys.path:
    _sys.path.insert(0, str(_LIB))


@mcp.tool()
async def reddit_user_history(username: str, max_items: int = 100) -> str:
    """Posts and comments by one Reddit user (T3). Arctic Shift, then PullPush, then RSS.

    A failure returns an ERROR string naming every route, never an empty list.
    """
    import reddit_arctic as ra
    try:
        out = await asyncio.to_thread(ra.user_history, username, max_items=max_items)
    except ra.RedditFetchFailed as exc:
        return f"ERROR: {exc}"
    out["tier"] = "T3"
    return json.dumps(out, ensure_ascii=False)[:60000]


@mcp.tool()
async def reddit_subreddit_recent(subreddit: str, max_items: int = 60) -> str:
    """Recent posts in a subreddit (T3). Arctic Shift, then PullPush, then RSS."""
    import reddit_arctic as ra
    try:
        rows = await asyncio.to_thread(ra.recent_with_rss, subreddit, max_items=max_items)
    except ra.RedditFetchFailed as exc:
        return f"ERROR: {exc}"
    return json.dumps({"subreddit": subreddit, "posts": rows, "tier": "T3"}, ensure_ascii=False)[:60000]


# ---------------------------------------------------------------------------
# Shared enrichment adapters (skills/osint/scripts/lib/enrich).
# Every adapter is reachable through these two tools, so adding a provider
# never requires editing this server.
# ---------------------------------------------------------------------------


@mcp.tool()
async def enrich_providers() -> str:
    """List every enrichment provider: slug, category, evidence tier, modes, and
    what is missing (API key env var or local binary) to run it."""
    from enrich import registry
    rows = await asyncio.to_thread(registry.describe_all)
    return json.dumps({"providers": rows, "import_errors": registry.IMPORT_ERRORS})


@mcp.tool()
async def enrich(provider: str, query: str, mode: str = "") -> str:
    """Run one enrichment provider (see enrich_providers for slugs and modes).

    Each result carries its evidence tier: T1 = non-fakeable record (WHOIS/RDAP,
    DNS, CT, registry, court, on-chain), T3 = automated tool output (hypothesis
    queue only). Errors come back as an ERROR string, never an empty list.
    """
    from enrich import registry
    from enrich.base import EnrichmentError
    try:
        adapter = registry.get_adapter(provider)
    except KeyError:
        return f"ERROR: unknown provider {provider!r}; call enrich_providers"
    try:
        results = await asyncio.to_thread(adapter.run, query, mode or None)
    except EnrichmentError as exc:
        return f"ERROR ({provider}): {exc}"
    rows = [dict(r.to_dict(), source=provider) for r in results]
    return json.dumps({"provider": provider, "query": query, "results": rows}, ensure_ascii=False)[:60000]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
