#!/usr/bin/env python3
"""add-osint-keys.py: put pasted OSINT API keys into ~/.zshrc and test each one.

Usage (copy your keys first, one per line, label then key):
    abusech   <key>
    urlscan   <key>
    builtwith <key>
    tavily    <key>
    exa       <key>
    jina      <key>

    python3 add-osint-keys.py --clipboard      # reads what you copied
    python3 add-osint-keys.py              # asks for each key, one by one

Labels are loose: "abuse.ch", "ABUSECH_AUTH_KEY=", "urlscan:" all work.
A key already in ~/.zshrc is replaced in place; a new one goes into the
managed block between the COPILOT-OSINT-KEYS markers. ~/.zshrc is backed up
first. Key values are never printed. Each key gets one live test call.
Flags: --no-verify skips the live tests. --zshrc PATH targets another file (tests).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# label -> env var name. Names match what the Investigators Copilot tools read.
ALIASES = {
    "ABUSECH_AUTH_KEY": ["abusech", "abuse.ch", "abuse", "threatfox", "urlhaus", "malwarebazaar"],
    "URLSCAN_API_KEY": ["urlscan", "urlscan.io"],
    "BUILTWITH_API_KEY": ["builtwith"],
    "TAVILY_API_KEY": ["tavily"],
    "EXA_API_KEY": ["exa"],
    "JINA_API_KEY": ["jina"],
    "VIRUSTOTAL_API_KEY": ["virustotal", "vt"],
}
BEGIN = "# >>> COPILOT-OSINT-KEYS (managed by add-osint-keys.py) >>>"
END = "# <<< COPILOT-OSINT-KEYS <<<"
# diagnose.sh looks for APIFY_API_TOKEN; the founder's shell sets APIFY_TOKEN.
EXTRA = ['[ -n "${APIFY_TOKEN:-}" ] && export APIFY_API_TOKEN="${APIFY_API_TOKEN:-$APIFY_TOKEN}"']


def resolve(label):
    norm = re.sub(r"[^a-z0-9.]", "", label.lower())
    for var, names in ALIASES.items():
        if norm == var.lower().replace("_", "") or norm in names:
            return var
    return None


def parse(text):
    keys, unknown = {}, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        m = re.match(r"""^([A-Za-z0-9_.\- ]+?)\s*[:=\s]\s*["']?([^"'\s]+)["']?\s*$""", line)
        if not m:
            unknown.append(line.split()[0][:20])
            continue
        var = resolve(m.group(1))
        if var is None:
            unknown.append(m.group(1)[:20])
            continue
        keys[var] = m.group(2)
    return keys, unknown


def write_zshrc(path, keys):
    text = open(path).read() if os.path.exists(path) else ""
    if os.path.exists(path):
        backup = f"{path}.bak-osint-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(path, backup)
        print(f"backup: {backup}")
    lines = text.splitlines()
    placed = set()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*export\s+([A-Z0-9_]+)=", line)
        if m and m.group(1) in keys and m.group(1) not in placed:
            lines[i] = f'export {m.group(1)}="{keys[m.group(1)]}"'
            placed.add(m.group(1))
            print(f"{m.group(1)}: replaced existing line")
    if BEGIN in lines:
        b, e = lines.index(BEGIN), lines.index(END)
        block = lines[b + 1:e]
        lines = lines[:b] + lines[e + 1:]
    else:
        block = []
    for var in keys:
        if var not in placed:
            block = [l for l in block if not l.startswith(f"export {var}=")]
            block.append(f'export {var}="{keys[var]}"')
            print(f"{var}: added")
    for x in EXTRA:
        if x not in block:
            block.append(x)
    while lines and lines[-1] == "":
        lines.pop()
    lines += ["", BEGIN] + block + [END]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    req.add_header("User-Agent", "investigators-copilot-osint-keycheck/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def verify(var, key):
    if var == "ABUSECH_AUTH_KEY":
        code, body = http("https://threatfox-api.abuse.ch/api/v1/",
                          json.dumps({"query": "get_iocs", "days": 1}).encode(), {"Auth-Key": key})
    elif var == "URLSCAN_API_KEY":
        code, body = http("https://urlscan.io/user/quotas/", headers={"API-Key": key})
    elif var == "BUILTWITH_API_KEY":
        code, body = http(f"https://api.builtwith.com/free1/api.json?KEY={key}&LOOKUP=example.com")
        if code == 200 and '"Errors"' in body and "[]" not in body.split('"Errors"')[1][:10]:
            code = 401
    elif var == "TAVILY_API_KEY":
        code, body = http("https://api.tavily.com/search",
                          json.dumps({"query": "test", "max_results": 1}).encode(),
                          {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    elif var == "EXA_API_KEY":
        code, body = http("https://api.exa.ai/search", json.dumps({"query": "test", "numResults": 1}).encode(),
                          {"x-api-key": key, "Content-Type": "application/json"})
    elif var == "JINA_API_KEY":
        code, body = http("https://r.jina.ai/https://example.com", headers={"Authorization": f"Bearer {key}"})
    elif var == "VIRUSTOTAL_API_KEY":
        code, body = http("https://www.virustotal.com/api/v3/domains/example.com", headers={"x-apikey": key})
    else:
        return "not tested"
    if code == 200:
        return "OK"
    if code == 429:
        return "OK (key accepted, rate limited right now)"
    return f"FAILED (HTTP {code})"


# The free keys, in the order asked, with where to get each one.
PROMPTS = [
    ("ABUSECH_AUTH_KEY", "abuse.ch (ThreatFox, URLhaus, MalwareBazaar)",
     "https://auth.abuse.ch/  sign in with Google or GitHub, copy the Auth-Key"),
    ("URLSCAN_API_KEY", "urlscan.io",
     "https://urlscan.io/user/signup  then https://urlscan.io/user/profile/  click New API key"),
    ("BUILTWITH_API_KEY", "BuiltWith (free API)",
     "https://api.builtwith.com/free-api  sign up, copy the key from your API page"),
    ("TAVILY_API_KEY", "Tavily search", "https://app.tavily.com  key is on the dashboard"),
    ("EXA_API_KEY", "Exa search", "https://dashboard.exa.ai  API Keys page"),
    ("JINA_API_KEY", "Jina reader", "https://jina.ai  scroll to the API section, copy the key shown"),
]


def prompt_each():
    import getpass
    keys = {}
    print("One key at a time. Paste it and press Enter. Press Enter on an empty line to skip.")
    print("What you paste stays hidden.\n")
    for i, (var, name, where) in enumerate(PROMPTS, 1):
        print(f"[{i}/{len(PROMPTS)}] {name}")
        print(f"      get it: {where}")
        val = getpass.getpass("      paste key: ").strip().strip("'\"")
        if val:
            keys[var] = val
            print("      got it\n")
        else:
            print("      skipped\n")
    return keys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clipboard", action="store_true")
    ap.add_argument("--paste", action="store_true", help="paste a block of labelled keys instead of being asked one by one")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--zshrc", default=os.path.expanduser("~/.zshrc"))
    a = ap.parse_args()
    if a.clipboard:
        keys, unknown = parse(subprocess.run(["pbpaste"], capture_output=True, text=True).stdout)
    elif a.paste or not sys.stdin.isatty():
        if sys.stdin.isatty():
            print("Paste your keys (label then key, one per line), then press Ctrl-D:")
        keys, unknown = parse(sys.stdin.read())
    else:
        keys, unknown = prompt_each(), []
    for u in unknown:
        print(f"skipped, label not recognised: {u}")
    if not keys:
        if not a.clipboard and not a.paste and not sys.stdin.isatty():
            print("No keyboard here, so I cannot ask for keys one by one.")
            print("Double-click 'Add OSINT Keys' on your Desktop instead.")
            sys.exit(1)
        print("No keys found. Expected lines like:  urlscan  <key>")
        sys.exit(1)
    # Test BEFORE writing, so a mistyped key never overwrites a working one.
    failed = 0
    if not a.no_verify:
        for var in list(keys):
            result = verify(var, keys[var])
            print(f"{var}: {result}")
            if result.startswith("FAILED"):
                failed += 1
                del keys[var]
                print(f"{var}: NOT written. Check you copied the whole key.")
    if keys:
        write_zshrc(a.zshrc, keys)
    print("Done. Open a new terminal (or run: source ~/.zshrc) and restart Claude Code to load them.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
