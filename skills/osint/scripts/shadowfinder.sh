#!/bin/bash
# shadowfinder.sh -- wrapper for bellingcat/ShadowFinder (shadow-length geolocation)
#
# Estimates the band of the Earth's surface where an object of a given height
# casts a shadow of a given length at a given date + time. The output is a
# PNG band map plus a JSON note of the inputs. A band is a SEARCH AREA, not a
# location: treat it as a constraint for geo-sleuth / manual geolocation.
#
# ShadowFinder is MIT licensed and is called via its CLI or Python API in a
# subprocess; nothing is vendored. Install: pip install shadowfinder
#
# Usage:
#   shadowfinder.sh find <object_height> <shadow_length> <YYYY-MM-DD> <HH:MM:SS> [--utc|--local] [--case <case>]
#   shadowfinder.sh sun  <sun_altitude_deg> <YYYY-MM-DD> <HH:MM:SS> [--utc|--local] [--case <case>]
#
# Heights/lengths are in any consistent unit. --utc is the default.
# Output: <run-dir>/shadowfinder.png + inputs.json. With --case the run dir is
# investigations/<case>/investigation/evidence/raw-collections/<ts>-shadowfinder/
# (route the PNG into an EV item with ingest-client-document.sh if you cite it).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../../.." && pwd)"

usage() {
  sed -n '12,15p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 1
}

MODE="${1:-}"
[ -z "$MODE" ] && usage
shift

case "$MODE" in
  find)
    [ $# -ge 4 ] || usage
    HEIGHT="$1"; LENGTH="$2"; DATE="$3"; TIME="$4"; shift 4
    ANGLE=""
    ;;
  sun)
    [ $# -ge 3 ] || usage
    ANGLE="$1"; DATE="$2"; TIME="$3"; shift 3
    HEIGHT=""; LENGTH=""
    ;;
  -h | --help) usage ;;
  *) echo "ERROR: unknown mode: $MODE" >&2; usage ;;
esac

TIME_FORMAT="utc"
CASE=""
WANT_CASE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --utc) TIME_FORMAT="utc"; shift ;;
    --local) TIME_FORMAT="local"; shift ;;
    --case) CASE="${2:-}"; WANT_CASE=1; shift 2 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage ;;
  esac
done

PY="${PYTHON:-python3}"
if ! "$PY" -c "import shadowfinder" >/dev/null 2>&1; then
  echo "NotConfigured: ShadowFinder is not installed." >&2
  echo "  Install: pip install shadowfinder   (bellingcat/ShadowFinder, MIT)" >&2
  echo "  No-install alternative: https://colab.research.google.com/github/Bellingcat/ShadowFinder/blob/main/ShadowFinderColab.ipynb" >&2
  exit 3
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
if [ "$WANT_CASE" = "1" ]; then
  # shellcheck source=lib/active_case.sh
  source "$SCRIPT_DIR/lib/active_case.sh"
  resolve_case_dir "$CASE" || exit 1
  OUT_DIR="$CASE_DIR/investigation/evidence/raw-collections/${TS}-shadowfinder"
else
  OUT_DIR="${TMPDIR:-/tmp}/shadowfinder-${TS}"
fi
mkdir -p "$OUT_DIR"

# The Python API caches the timezone grid in the working directory, which is
# the main cost of the CLI ("generated every run"). Run from a stable cache dir.
CACHE_DIR="${SHADOWFINDER_CACHE:-$HOME/.cache/shadowfinder}"
mkdir -p "$CACHE_DIR"

(
  cd "$CACHE_DIR"
  SF_MODE="$MODE" SF_HEIGHT="$HEIGHT" SF_LENGTH="$LENGTH" SF_ANGLE="$ANGLE" \
  SF_DATE="$DATE" SF_TIME="$TIME" SF_TF="$TIME_FORMAT" SF_OUT="$OUT_DIR" \
  "$PY" - <<'PYEOF'
import json
import os
from datetime import datetime

from shadowfinder import ShadowFinder

env = os.environ
date_time = datetime.strptime(f"{env['SF_DATE']} {env['SF_TIME']}", "%Y-%m-%d %H:%M:%S")
finder = ShadowFinder()
try:
    finder.load_timezone_grid()
except FileNotFoundError:
    finder.generate_timezone_grid()
    finder.save_timezone_grid()

kwargs = {"date_time": date_time, "time_format": env["SF_TF"]}
if env["SF_MODE"] == "find":
    kwargs["object_height"] = float(env["SF_HEIGHT"])
    kwargs["shadow_length"] = float(env["SF_LENGTH"])
else:
    kwargs["sun_altitude_angle"] = float(env["SF_ANGLE"])
finder.set_details(**kwargs)
finder.find_shadows()
fig = finder.plot_shadows()
png = os.path.join(env["SF_OUT"], "shadowfinder.png")
fig.savefig(png, dpi=150, bbox_inches="tight")

inputs = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in kwargs.items()}
inputs.update({"tool": "bellingcat/ShadowFinder", "tier": "T3",
               "note": "Possible-location band, not a location. Constraint only."})
with open(os.path.join(env["SF_OUT"], "inputs.json"), "w") as fh:
    json.dump(inputs, fh, indent=2)
print(png)
PYEOF
)

echo "[shadowfinder] output: $OUT_DIR" >&2
