#!/usr/bin/env python3
"""Install offline Argos translation models (source -> English). Needs network once.

Ported 2026-10-10 from assafkip/account-procurement-tools
(account-procurement-pipeline/install_models.py).
"""

import argostranslate.package as pkg

WANT = ["ru", "zh", "vi", "es", "pt", "tr", "uk", "de", "fr", "id", "ar", "fa", "he"]


def main():
    pkg.update_package_index()
    available = pkg.get_available_packages()
    installed, missing = [], []
    for code in WANT:
        match = next((p for p in available if p.from_code == code and p.to_code == "en"), None)
        if match is None:
            missing.append(code)
            continue
        pkg.install_from_path(match.download())
        installed.append(code)
    print(f"  installed: {', '.join(installed) or 'none'}")
    if missing:
        print(f"  NOT in Argos index: {', '.join(missing)} (posts in these languages stay untranslated;")
        print("   detection and native-language keyword matching still work)")


if __name__ == "__main__":
    main()
