#!/usr/bin/env python3
"""preflight_control.py: wrap a known-answer control so it can gate a long pass.

USAGE
    python3 preflight_control.py [--timeout SECONDS] -- <control command> [args...]

    Runs the control command once. Passes (exit 0) only when ALL of these hold:
      1. the command exits 0
      2. its stdout is JSON (the whole stdout, or failing that its last non-empty line)
      3. that JSON is an object with "ok" set to the boolean true (not "true", not 1)
    On pass it prints the control's JSON to stdout and exits 0.
    On any failure it prints the reason plus the raw output to stderr and exits 2.
    A usage error exits 64, so a broken invocation never reads as "control said no".

    It spends nothing and makes no network call of its own. Whatever the control
    command does is the control command's business; keep controls offline or cached.

EXAMPLE (case-044, run from the snowball workdir)
    python3 "$OSINT/preflight_control.py" -- python3 c1c_description_links.py --control-pilot

WHY THIS EXISTS
    rca-c1-agent-process-case-001-example: the must-hit control was READ after a
    90-minute background pass instead of GATING its launch, so a broken extractor ran
    the whole population and its null looked like a finding. A control that runs after
    the pass is a post-mortem. This helper is the gate half; long_pass.sh is the
    launcher half and refuses to start anything when this exits non-zero.
    "ok" must be a real boolean because a control that prints {"ok": "false"} is a
    truthy string, and a gate that reads truthiness would wave it through.
"""
import json
import subprocess
import sys

EXIT_PASS = 0
EXIT_FAIL = 2
EXIT_USAGE = 64


def _fail(reason, out="", err=""):
    sys.stderr.write(f"PREFLIGHT_CONTROL FAIL: {reason}\n")
    if out:
        sys.stderr.write("--- control stdout ---\n" + out.rstrip("\n") + "\n")
    if err:
        sys.stderr.write("--- control stderr ---\n" + err.rstrip("\n") + "\n")
    return EXIT_FAIL


def parse_control_json(stdout):
    """Return the control's JSON object, or raise ValueError naming why not."""
    text = stdout.strip()
    if not text:
        raise ValueError("control printed nothing on stdout")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # A control may log progress lines first; its verdict is then the last line.
        last = [ln for ln in text.splitlines() if ln.strip()][-1]
        try:
            obj = json.loads(last)
        except json.JSONDecodeError as exc:
            raise ValueError(f"control stdout is not JSON ({exc})") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"control JSON is a {type(obj).__name__}, not an object")
    if "ok" not in obj:
        raise ValueError('control JSON has no "ok" key')
    if obj["ok"] is not True:
        raise ValueError(f'control JSON has "ok": {json.dumps(obj["ok"])}, need true')
    return obj


def main(argv):
    timeout = None
    args = list(argv)
    if args[:1] == ["--timeout"]:
        if len(args) < 2:
            sys.stderr.write("usage: preflight_control.py [--timeout S] -- <cmd> [args]\n")
            return EXIT_USAGE
        try:
            timeout = float(args[1])
        except ValueError:
            sys.stderr.write("preflight_control.py: --timeout needs a number\n")
            return EXIT_USAGE
        args = args[2:]
    if args[:1] != ["--"] or len(args) < 2:
        sys.stderr.write("usage: preflight_control.py [--timeout S] -- <cmd> [args]\n")
        return EXIT_USAGE
    cmd = args[1:]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return _fail(f"control command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return _fail(f"control command timed out after {timeout}s")
    if proc.returncode != 0:
        return _fail(f"control command exited {proc.returncode}", proc.stdout, proc.stderr)
    try:
        obj = parse_control_json(proc.stdout)
    except ValueError as exc:
        return _fail(str(exc), proc.stdout, proc.stderr)
    print(json.dumps(obj, sort_keys=True))
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
