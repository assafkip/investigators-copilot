---
name: geo-sleuth
description: >
  Geolocate or chronolocate a photo with tool-verified reasoning, then route every
  output into the case's EV-NNNN evidence chain. Companion to the upstream
  Oldcircle/geo-sleuth agent skill (MIT): its scripts do metadata, OCR, reverse image
  search, sun/shadow math, OSM corridors, DEM skylines and street-view ranking.
  Use when: "where was this photo taken", "geolocate this image", "when was this
  taken", "chronolocate", "find the location of this picture".
  NOT for: identifying a person in a photo (use /q-face, founder approval required),
  or photos of private individuals whose location the case has no lawful reason to find.
---

# geo-sleuth (Investigators Copilot companion)

Adapted from https://github.com/Oldcircle/geo-sleuth (MIT, see `NOTICE.md`). This
file does NOT vendor the upstream scripts. It tells you how to install them, the
rules that make their output defensible, and how to land every artifact in the
case's evidence chain under `.claude/rules/evidence-capture-protocol.md`.

## 0. Gate before you start

- **Purpose check.** If the photo shows a private residence, a minor, or a person
  who is not a case target, stop and ask the founder what the location is for.
  Upstream's own rule: never use it to find people who have not agreed to be found.
- **Register the photo first.** A client-provided photo becomes an EV item before
  any analysis touches it:
  ```bash
  bash skills/osint/scripts/ingest-client-document.sh <photo> <slug> screenshot_only \
    --case <case> --provided-by "<who>"
  python3 skills/osint/scripts/extract-intake.py --case <case>
  ```
  A photo found online is captured by URL instead:
  `bash skills/osint/scripts/capture-evidence.sh <url> <slug> --case <case>`.
  Run geo-sleuth on a COPY (`cp` the EV original into a scratch dir). Never write
  into an EV folder's original, and never edit `source.json`.

## 1. Install (once per machine)

Needs Python 3.10+, `uv`, `curl`, Chrome or Playwright Chromium.

```bash
git clone https://github.com/Oldcircle/geo-sleuth ~/tools/geo-sleuth
export GEO_SLEUTH_DIR=~/tools/geo-sleuth/skills/geo-sleuth
uv run "$GEO_SLEUTH_DIR/scripts/doctor.py"            # local checks
uv run "$GEO_SLEUTH_DIR/scripts/doctor.py" --network  # service probes, no upload
# if the browser check fails:
uvx playwright install chromium
```

Upstream commands use `${CLAUDE_SKILL_DIR}`; in this repo substitute
`$GEO_SLEUTH_DIR`. Read upstream `SKILL.md` and `references/` for the full
operator catalog; the summary below is only what you need to stay inside our
evidence rules.

## 2. Working directory

One run directory per photo, outside the EV tree:

```bash
RUN=investigations/<case>/investigation/evidence/raw-collections/$(date -u +%Y%m%dT%H%M%SZ)-geo-<slug>
mkdir -p "$RUN" && cp <EV original> "$RUN/photo.jpg" && cd "$RUN"
```

`raw-collections/` is working material, not citable evidence.

## 3. Flow (upstream, condensed)

1. **Intake** -- `uv run $GEO_SLEUTH_DIR/scripts/intake.py photo.jpg --out-dir intake/`
   then `board.py init --photo photo.jpg`. Add `--no-rev` to keep the photo off
   Baidu/Yandex when the case is sensitive (founder call: reverse search uploads
   the image to a third party).
2. **Clues on the board** -- log each clue with an honest status
   (`read` / `observed` / `inferred` / `computed`) via `board.py clue`.
   Lookup-table clues through `clues.py`; region packs through `regions.py show <cc>`.
3. **List the whole category, then rank** -- `board.py children`, `board.py evidence`,
   `board.py rank`, `board.py next`. Never pick by population or fame.
4. **Narrow** -- anchors and bearings (`geo.py`), sun/shadows (`sun.py`; our
   `scripts/shadowfinder.sh` gives an independent shadow-band constraint),
   OSM corridors (`osm.py`), skylines (`terrain.py scan/ridge/fit`),
   satellite ranking (`sat_scan.py`), street-view ranking (`match.py`).
5. **Confirm and report** -- `board.py check`, `board.py report --merge result.json`,
   `evidence.py spec.json --out evidence.jpg`.

## 4. Upstream hard rules we keep verbatim in spirit

- No fabricated verification: "matched street view" or "plus/minus 10 m" must point
  to a command that ran and a file it produced. Otherwise write "unverified".
- An error radius of 100 m or less needs two independent constraints, or a
  ground-level match on 3+ invariant features.
- Exclusion and confirmation use the same standard: only read/computed clues with
  a computed file can exclude a candidate.
- Metadata and hints are hypotheses. When EXIF or a tip conflicts with the
  image, the image wins.
- If you cannot pin a point, report a range plus the missing information.

## 5. Mapping to our evidence tiers

| geo-sleuth output | Tier | May appear in a report? |
|---|---|---|
| EXIF GPS from the original file (unaltered EV item) | T1-adjacent metadata, still a hypothesis per rule above | Yes, labeled "metadata, not verified by imagery" |
| Two independent computed constraints + ground-level match, `board.py check` clean | T2 (when the matched street view / satellite tile is itself captured as an EV item) | Yes, with confidence tier and error radius |
| Single constraint, reverse-image hit, CLIP/DINOv2 rank | T3 | No, hypothesis queue only |

A location is not an identity. A geolocated photo never attributes an account to a
person on its own (`.claude/rules/q-investigation.md`).

## 6. Route outputs into EV (required before citing)

Everything you intend to cite becomes its own EV item. Never cite `raw-collections/`.

```bash
# The evidence image and the board report (derived analysis, not client material)
bash skills/osint/scripts/ingest-client-document.sh "$RUN/evidence.jpg" geo-<slug>-evidence document \
  --case <case> --provided-by "geo-sleuth analysis of EV-NNNN" --note "board.py report: result.json; confidence <tier>"
bash skills/osint/scripts/ingest-client-document.sh "$RUN/result.json" geo-<slug>-result document \
  --case <case> --provided-by "geo-sleuth analysis of EV-NNNN"

# Any street-view / satellite / page URL the conclusion rests on
bash skills/osint/scripts/capture-evidence.sh "<street-view-or-page-url>" geo-<slug>-match --case <case> \
  --note "geo-sleuth ground-level match for EV-NNNN"
```

Then write the finding citing the EV IDs, the commands run, the error radius and
the confidence tier. Plot geo-tagged items with
`python3 skills/osint/scripts/render-map.py --case <case>`.

## 7. Failure handling

Fail-stop applies. A CAPTCHA or 403 from Baidu/Yandex/Google during intake is a
blocked extraction: stop, tell the founder which service and URL, and wait. A failed
reverse search is not evidence that no matching image exists (upstream
troubleshooting table).
