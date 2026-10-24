#!/bin/bash
# mcp-call.sh -- call one tool on a local stdio MCP server from the shell.
# For subagents and sessions where the server did not load as MCP tools
# (2026-10-06: osint-infra / threat-intel failed to connect from infohawk/ cwd).
#
# Usage: mcp-call.sh <osint-infra|threat-intel> <tool> '<json args>'
#   mcp-call.sh threat-intel crt_lookup '{"domain":"playsstoresint.com"}'
#   mcp-call.sh osint-infra whois_lookup '{"domain":"getstatslab.work"}'
# Tools: osint-infra: whois_lookup dns_lookup reverse_dns wayback_snapshots wayback_fetch
#        threat-intel: vt_lookup urlhaus_lookup threatfox_lookup crt_lookup
set -euo pipefail
SERVER="${1:?ERROR: server name}"; TOOL="${2:?ERROR: tool name}"; ARGS="${3:-{\}}"
R="$(cd "$(dirname "$0")/../../../tools" && pwd)"
case "$SERVER" in
  osint-infra) PY="$R/osint-infra-mcp/.venv/bin/python"; SRV="$R/osint-infra-mcp/server.py" ;;
  threat-intel) PY="$R/threat-intel-mcp/.venv/bin/python"; SRV="$R/threat-intel-mcp/server.py" ;;
  *) echo "ERROR: unknown server $SERVER" >&2; exit 1 ;;
esac
REQ=$(python3 -c 'import json,sys; print(json.dumps({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":sys.argv[1],"arguments":json.loads(sys.argv[2])}}))' "$TOOL" "$ARGS")
{ printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"mcp-call","version":"1"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized"}' "$REQ"; sleep "${MCP_CALL_WAIT:-20}"; } \
| "$PY" "$SRV" 2>/dev/null \
| python3 -c 'import sys,json
for l in sys.stdin:
  try: d=json.loads(l)
  except Exception: continue
  if d.get("id")==3:
    r=d.get("result",d)
    for c in r.get("content",[]): print(c.get("text",""))
    sys.exit(1 if r.get("isError") else 0)
sys.exit(2)'
