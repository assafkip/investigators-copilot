#!/bin/bash
# setup.sh -- one-time setup for the telegram-harvest skill: venv, deps, tgspyder,
# offline translation models. Safe to re-run. Model download is the only network step.
#
# tgspyder (Darksight Analytics, MIT) is NOT vendored here. Point TGSPYDER_SRC at a
# checkout (e.g. tools/tgspyder, or the copy inside
# assafkip/account-procurement-tools), or have `tgspyder` already on PATH.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HERE/.venv"
TGSPYDER_SRC="${TGSPYDER_SRC:-$HERE/../../tools/tgspyder}"

echo "[1/4] virtualenv: $VENV"
python3 -m venv "$VENV"

echo "[2/4] Python dependencies"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install -r "$HERE/requirements.txt"

echo "[3/4] tgspyder"
if [ -f "$TGSPYDER_SRC/pyproject.toml" ] || [ -f "$TGSPYDER_SRC/setup.py" ]; then
  "$VENV/bin/pip" install -e "$TGSPYDER_SRC"
elif command -v tgspyder >/dev/null 2>&1; then
  echo "      using tgspyder on PATH: $(command -v tgspyder)"
else
  echo "      WARNING: tgspyder not found (set TGSPYDER_SRC=<checkout>). --from-csv mode still works." >&2
fi

echo "[4/4] offline translation models"
"$VENV/bin/python" "$HERE/scripts/install_models.py"

echo "Done. Authenticate tgspyder once (interactive): $VENV/bin/tgspyder @somechannel --chats"
echo "Then: $VENV/bin/python $HERE/scripts/harvest.py --channels channels.txt --case"
