"""Shared OSINT enrichment adapters for Investigators Copilot.

One adapter per provider, one file per adapter. Used by:
  - scripts/osint-tool.py           (bash belt / CLI)
  - tools/osint-infra-mcp/server.py (MCP tools `enrich` and `enrich_providers`)

Adding a provider = adding one module here that defines an `Adapter` subclass
with a unique `slug`. registry.py discovers it; nothing else needs editing.
Ported 2026-10-10 from assafkip/kipi `investigations/enrich/` (SQLite key store
removed: keys come from environment variables only) plus hydra keyless lookups.
"""
