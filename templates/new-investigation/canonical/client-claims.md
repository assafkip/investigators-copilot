# Client-Claimed Identifiers

**Prerequisite:** Populate this file before running check-collision.sh or writing any findings.
The collision check reads `client-claims.json` directly. The findings gate blocks CONFIRMED or
HIGH CONFIDENCE attributions when any cited identifier remains UNVERIFIED in this file.

**Workflow:**
1. Add all client-provided identifiers below (status: UNVERIFIED on entry)
2. For each identifier, run: `bash skills/osint/scripts/check-collision.sh <value> <type> <case-folder>`
3. The script updates status to VERIFIED in client-claims.json on a clean pass
4. Update this markdown table to match after each run
5. Before writing findings, confirm no UNVERIFIED identifier is being used as an attribution crosslink

**Username policy (T3 cap):**
> username-only attribution is capped at T3. A username becomes T2 only when a second,
> independent identifier (phone, email, or SSN) crosslinks it to a T1 source for the subject.
> Do not cite a username-only match as CONFIRMED or HIGH CONFIDENCE -- the findings hook will block it.

---

| Identifier | Type | Status | Verified-By | Notes |
|------------|------|--------|-------------|-------|
| {{IDENTIFIER_VALUE}} | {{email\|phone\|username\|ssn\|handle}} | UNVERIFIED | | Client-provided |

---

*This file is auto-scaffolded per case. Update both this table and client-claims.json when verification status changes.*
