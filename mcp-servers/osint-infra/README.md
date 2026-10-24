# osint-infra-mcp

MCP server for OSINT infrastructure lookups: DNS, WHOIS, and Wayback Machine.

## Tools

| Tool | What it does |
|------|-------------|
| `whois_lookup` | WHOIS registration data for a domain |
| `dns_lookup` | DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA, ANY) |
| `reverse_dns` | PTR record for an IP address |
| `wayback_snapshots` | List archived snapshots of a URL |
| `wayback_fetch` | Fetch content of a specific archived snapshot |
| `reddit_user_history` | Posts + comments by a Reddit user (Arctic Shift, PullPush, RSS) |
| `reddit_subreddit_recent` | Recent posts in a subreddit (same routes) |

## Setup and run

Vendored into Investigators Copilot (no longer a separate repo). `.mcp.json` launches it with uv:

```bash
uv run --directory tools/osint-infra-mcp server.py
```

The Reddit tools (`reddit_user_history`, `reddit_subreddit_recent`) import the shared
library at `skills/osint/scripts/lib/`, the same code the CLI scripts use.

## Requirements

- Python 3.10+
- `whois` and `dig` CLI tools (pre-installed on macOS/Linux)
- No API keys needed -- all lookups use public infrastructure
