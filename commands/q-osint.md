Run targeted OSINT collection on a specific platform.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Read `skills/osint/SKILL.md` for actor IDs and tool usage, then execute the /q-osint steps from `.q-system/commands.md`.

Supported platforms: linkedin, instagram, facebook, reddit, x, tiktok, youtube, domain, email, telegram, username, sweep

Additional tools beyond the OSINT skill scripts:
- Telegram: `tgspyder <target> --members --chats` or `tgspyder --user <username>`
- Reddit: `python3 skills/osint/scripts/reddit-arctic.py user <username> --case <case>` (Arctic Shift, then PullPush, then Reddit RSS; reddit.com JSON returns 403 from servers, do not use it)
- Username search: `maigret <username> --json investigations/<case>/investigation/evidence/maigret-<username>.json`
- Google/Email: `ghunt email <address> --json investigations/<case>/investigation/evidence/ghunt-<address>.json`
- Identity sweep (username / email / phone): `python3 skills/osint/scripts/identity-sweep.py <value> --case <case>` -- every ready identity adapter (incl. maigret, sherlock, holehe, ghunt when installed), merged, all T3. Shortcut: `bash skills/osint/scripts/identity-lookup.sh sweep <value> <case>`
- Any enrichment adapter: `python3 skills/osint/scripts/osint-tool.py --list`, then `osint-tool.py <slug> <query> --case <case>` (domain: `rdap`, `doh`, `crtsh`, `certspotter`; company: `gleif`, `opencorporates`, `courtlistener`, `ofac`; crypto: `wallet`, `ens`, `tron`). Each result prints its tier: T1 records vs T3 tool output.
- Social posts: `bash skills/osint/scripts/capture-evidence.sh <url> <slug> --case <case> --social` also saves the post media into the EV item.
- Missing tools: `bash skills/osint/scripts/setup-tools.sh --list`

Saved runs write `results.json` + `urls.tsv`; feed `urls.tsv` to `capture-evidence.sh --batch` before citing. Reputation, username and scraped-profile hits are T3 and never count as crosslinks (`.claude/rules/q-investigation.md`).

All results must be saved to `investigations/<case>/investigation/evidence/` and relevant target profiles updated.
Tag source reliability using the A-F scale from `.q-system/preflight.md`.

Argument: $ARGUMENTS (required: platform and target, e.g. "linkedin https://linkedin.com/in/someone")
