#!/usr/bin/env bash
# long_pass.sh: launch a long background pass ONLY after its preflight passes.
#
# USAGE
#   long_pass.sh --name <pass-name> --workdir <dir> --preflight "<command>" -- <pass cmd> [args...]
#
#   1. cd <workdir>, run the preflight with `bash -c "<command>"`.
#   2. Preflight exit != 0: print its output to stderr, write NOTHING, exit 2.
#      The pass never starts. No run.json, no status file, no log, no child.
#   3. Preflight exit 0: start the pass with nohup in the background (stdin from
#      /dev/null, stdout+stderr to <name>.<run_id>.log), then write:
#        <workdir>/<name>.status.<run_id>.json  one file per run, never rewritten by
#                                               this launcher, never shared by two runs
#        <workdir>/<name>.status.latest         one line: the newest run_id
#        <workdir>/<name>.run.json              the newest launch record
#      All three carry: run_id, pid, started, preflight_exit, preflight_output_tail,
#      command, workdir, log, status_file.
#   4. The pass gets LONG_PASS_RUN_ID and LONG_PASS_STATUS_FILE in its environment,
#      so a resume run writes progress into ITS OWN status file, not the last run's.
#   Exit codes: 0 launched, 2 preflight refused, 64 usage error, 70 launch failed.
#
# PREFLIGHT HELPERS (same folder)
#   preflight_control.py -- <control cmd>   exit 0 only on exit 0 AND JSON "ok": true
#   plausibility_band.py --measured R --baseline B --tolerance T   exit 2 outside the band
#   Chain stages with && inside the one --preflight string.
#
# EXAMPLE (case-044 C1 description-link full pass, run from anywhere)
#   OSINT=skills/osint/scripts
#   SNOW=investigations/case-001-example/investigation/raw-collections/snowball-2026-10-13
#   bash "$OSINT/long_pass.sh" --name c1c-full --workdir "$SNOW" \
#     --preflight "python3 $PWD/$OSINT/preflight_control.py -- python3 c1c_description_links.py --control-pilot" \
#     -- python3 c1c_description_links.py
#
# WHY THIS SHAPE
#   rca-c1-agent-process-case-001-example: the known-answer control was read AFTER
#   a 90-minute nohup pass, so a broken extractor spent the whole run and its null
#   looked like a finding. The launch has to depend on the control, not be followed
#   by it. Same RCA: a resume run shared one status file with the first run and
#   overwrote its id, so nobody could tell which process the file described. Hence
#   one status file per run id plus a separate .latest pointer.
#   Usage errors exit 64, not 2, so a typo can never read as "the control said no".
#
# LIMITS (not built here, see the RCA action list)
#   No receipt keyed to the pass script's sha, no PreToolUse hook blocking a bare
#   nohup outside this launcher, no controls-first queue ordering, no pass_status.py.
set -euo pipefail

usage() {
  echo "usage: long_pass.sh --name <pass-name> --workdir <dir> --preflight \"<command>\" -- <pass cmd> [args...]" >&2
  exit 64
}

NAME="" WORKDIR="" PREFLIGHT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) [ $# -ge 2 ] || usage; NAME="$2"; shift 2 ;;
    --workdir) [ $# -ge 2 ] || usage; WORKDIR="$2"; shift 2 ;;
    --preflight) [ $# -ge 2 ] || usage; PREFLIGHT="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "long_pass.sh: unknown argument: $1" >&2; usage ;;
  esac
done
[ -n "$NAME" ] && [ -n "$WORKDIR" ] && [ -n "$PREFLIGHT" ] && [ $# -ge 1 ] || usage
case "$NAME" in
  *[!A-Za-z0-9._-]*|.*) echo "long_pass.sh: --name must be [A-Za-z0-9._-] and not start with a dot" >&2; exit 64 ;;
esac
[ -d "$WORKDIR" ] || { echo "long_pass.sh: workdir not found: $WORKDIR" >&2; exit 64; }
WORKDIR="$(cd "$WORKDIR" && pwd)"
cd "$WORKDIR"

# Preflight. Its output is held in memory, not a file: a refused run writes nothing.
set +e
PREFLIGHT_OUT="$(bash -c "$PREFLIGHT" 2>&1 </dev/null)"
PREFLIGHT_EXIT=$?
set -e
if [ "$PREFLIGHT_EXIT" -ne 0 ]; then
  {
    echo "LONG_PASS REFUSED: preflight exited $PREFLIGHT_EXIT, pass '$NAME' NOT started."
    echo "--- preflight output ---"
    printf '%s\n' "$PREFLIGHT_OUT"
  } >&2
  exit 2
fi

RAND="$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$RAND"
STATUS_FILE="$WORKDIR/$NAME.status.$RUN_ID.json"
LOG="$WORKDIR/$NAME.$RUN_ID.log"
if [ -e "$STATUS_FILE" ] || [ -e "$LOG" ]; then
  echo "long_pass.sh: run id collision on $RUN_ID, refusing to overwrite" >&2
  exit 70
fi
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

LONG_PASS_RUN_ID="$RUN_ID" LONG_PASS_STATUS_FILE="$STATUS_FILE" \
  nohup "$@" >"$LOG" 2>&1 </dev/null &
PID=$!

# One python writer for all three files, so the JSON is escaped correctly and each
# file lands by rename (a reader never sees half a record).
LP_RUN_ID="$RUN_ID" LP_PID="$PID" LP_STARTED="$STARTED" LP_PRE_EXIT="$PREFLIGHT_EXIT" \
LP_PRE_OUT="$PREFLIGHT_OUT" LP_WORKDIR="$WORKDIR" LP_LOG="$LOG" LP_STATUS="$STATUS_FILE" \
LP_NAME="$NAME" python3 - "$@" <<'PY' || { echo "long_pass.sh: failed to write run records; pass pid $PID is running" >&2; exit 70; }
import json, os, sys
e = os.environ
tail = "\n".join(e["LP_PRE_OUT"].splitlines()[-20:])
rec = {"run_id": e["LP_RUN_ID"], "pid": int(e["LP_PID"]), "started": e["LP_STARTED"],
       "state": "launched", "preflight_exit": int(e["LP_PRE_EXIT"]),
       "preflight_output_tail": tail, "command": sys.argv[1:],
       "workdir": e["LP_WORKDIR"], "log": e["LP_LOG"], "status_file": e["LP_STATUS"]}
def put(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)
body = json.dumps(rec, indent=2) + "\n"
put(e["LP_STATUS"], body)
put(os.path.join(e["LP_WORKDIR"], e["LP_NAME"] + ".run.json"), body)
put(os.path.join(e["LP_WORKDIR"], e["LP_NAME"] + ".status.latest"), e["LP_RUN_ID"] + "\n")
PY

echo "LONG_PASS LAUNCHED name=$NAME run_id=$RUN_ID pid=$PID"
echo "  status: $STATUS_FILE"
echo "  log:    $LOG"
