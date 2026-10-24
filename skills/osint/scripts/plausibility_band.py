#!/usr/bin/env python3
"""plausibility_band.py: refuse a measured rate that sits far from its prior.

USAGE
    python3 plausibility_band.py --measured R --baseline B --tolerance T [--relative]

    Absolute mode (default): passes when |R - B| <= T.
    --relative: passes when |R - B| <= T * |B|  (T is a fraction, e.g. 0.25).
    Prints one JSON line {measured, baseline, tolerance, mode, low, high, ok}.
    Exit 0 inside the band, 2 outside it, 64 on bad input (not a number, T < 0).

    Meant as an optional second preflight stage chained with &&, e.g.
      --preflight "python3 preflight_control.py -- <control> && \
                   python3 plausibility_band.py --measured 0.55 --baseline 0.58 --tolerance 0.10"

WHY THIS EXISTS
    rca-c1-agent-process-case-001-example: a partial whose zero-link share sat far
    from the prior was read as a finding instead of as a broken instrument. A rate far
    from what a prior run measured is a reason to stop and look, not to keep running.
"""
import argparse
import json
import math
import sys

EXIT_PASS, EXIT_FAIL, EXIT_USAGE = 0, 2, 64


def band(measured, baseline, tolerance, relative=False):
    width = tolerance * abs(baseline) if relative else tolerance
    low, high = baseline - width, baseline + width
    return low, high, low <= measured <= high


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--measured", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--tolerance", required=True)
    p.add_argument("--relative", action="store_true")
    try:
        a = p.parse_args(argv)
    except SystemExit:
        return EXIT_USAGE
    try:
        m, b, t = float(a.measured), float(a.baseline), float(a.tolerance)
    except ValueError:
        sys.stderr.write("plausibility_band.py: every value must be a number\n")
        return EXIT_USAGE
    if any(math.isnan(x) or math.isinf(x) for x in (m, b, t)) or t < 0:
        sys.stderr.write("plausibility_band.py: values must be finite and tolerance >= 0\n")
        return EXIT_USAGE
    low, high, ok = band(m, b, t, a.relative)
    print(json.dumps({"measured": m, "baseline": b, "tolerance": t,
                      "mode": "relative" if a.relative else "absolute",
                      "low": low, "high": high, "ok": ok}, sort_keys=True))
    if not ok:
        sys.stderr.write(f"PLAUSIBILITY FAIL: {m} outside [{low}, {high}]\n")
        return EXIT_FAIL
    return EXIT_PASS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
