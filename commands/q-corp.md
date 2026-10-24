Public-records sweep for a company or person: SEC/EDGAR, Form D, UK Companies House, FEC, lobbying (LDA), FAA aircraft registry, EU tenders.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every output lands in `investigations/<case>/investigation/evidence/raw-collections/<ts>-pp-<cli>/` (`output.txt`, `stderr.txt`, `command.txt`). If `.active-case` is missing or empty, ask the founder which case to use.

**Tooling:** the mvanhorn printing-press library CLIs (Go binaries, run as subprocesses). Check and install:
```bash
bash skills/osint/scripts/install-pp.sh list
bash skills/osint/scripts/install-pp.sh install            # all seven, needs Go
bash skills/osint/scripts/install-pp.sh install edgar fec   # or a subset
```
Keys: `COMPANY_PP_CONTACT_EMAIL` (SEC fair-access User-Agent; edgar-pp-cli refuses to run without it), `COMPANIES_HOUSE_API_KEY` (UK lookups), `FEC_API_KEY_QUERY_AUTH` (DEMO_KEY works, rate-limited), `LDA_API_KEY` (optional). If a CLI is missing, say which and offer the install line; do not substitute a web scrape silently.

**Steps:**
1. Parse `$ARGUMENTS`: the subject (company name, domain, ticker, person, N-number) and optional source list. Default: all sources that fit the subject type.
2. Run each source through the saving wrapper (always `run ... --`, never the bare binary, so the output is kept):
   ```bash
   P=skills/osint/scripts/install-pp.sh
   # SEC / EDGAR
   bash $P run edgar -- primary-sources <TICKER> --json
   bash $P run sec-edgar -- companies lookup "<name or ticker>" --json
   bash $P run sec-edgar -- filings list --cik <CIK> --limit 20 --json
   # Form D (private raises, US) and UK Companies House
   bash $P run company-goat -- funding --domain <domain> --json
   bash $P run company-goat -- funding --who "<Person Name>" --json
   bash $P run company-goat -- legal --region uk <company> --json
   # Campaign finance / lobbying
   bash $P run fec -- --help        # pick the committee / contributor command from the help, then rerun
   bash $P run lda-gov -- entities resolve "<name>" --agent --limit 10
   bash $P run lda-gov -- search "<name>" --type filings --limit 10
   # Aircraft
   bash $P run faa-registry -- aircraft lookup <N-number>
   bash $P run faa-registry -- owners "<owner name>"
   # EU procurement
   bash $P run eu-tenders -- winner "<company>" --agent
   bash $P run eu-tenders -- buyer --name "<buyer>" --show-winners --agent
   ```
   Subcommands change between releases: when a command errors, run `bash $P run <cli> -- <command> --help` and adapt, do not guess flags twice.
3. Tier the results (`.claude/rules/q-investigation.md`): a registry record is **T1 for what the record says** (filer, officer, amount, date, registration). A name match between a registry record and a target is **0 crosslinks** until a second identifier (address, CIK, LEI, company number, email domain, signature) ties them.
4. Capture the record pages you will cite as EV items:
   `bash skills/osint/scripts/capture-evidence.sh "<sec.gov / find-and-update.company-information.service.gov.uk / fec.gov / lda.gov / registry.faa.gov / ted.europa.eu URL>" <slug> --platform <registry>`
5. Record load-bearing numbers (amounts, counts, dates) in the evidence ledger before they go into a deliverable (`.claude/rules/investigation-claims-ledger.md`).
6. Report: per source, what was found (with the raw-collections path), what is T1, the EV IDs captured, name-only matches flagged as unverified, and sources skipped for missing keys/binaries.

**Rules:**
- Fail-stop: a CLI error you cannot resolve with its own `--help` is a stop; tell the founder which CLI, which command, and the stderr.
- Never put API keys in commands that get saved to `command.txt`; use the env vars above.

Argument: $ARGUMENTS (subject, plus optional sources: `sec`, `formd`, `uk`, `fec`, `lda`, `faa`, `eu`)
