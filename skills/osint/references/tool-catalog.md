# OSINT Tool Catalog (curated)

A short, opinionated index of external tools by category, for when the scripts in
`scripts/` do not cover a question. It is a pointer list, not an endorsement and not
a tool we have wired. Before using any web tool on case material:

- Uploading a target's image, email or phone to a third-party site discloses it.
  Decide per case; the founder approves anything client-sensitive.
- Output of every tool here is **T3** until crosslinked (`.claude/rules/q-investigation.md`).
- Cite nothing that is not an EV-NNNN item (`capture-evidence.sh`).
- `(local)` = runs on our machine; `(web)` = third-party site; `(key)` = needs an account/API key.

Sources (fetched 2026-10-10, used as data): Bellingcat Online Investigation Toolkit
(bellingcat.gitbook.io/toolkit, categories + tool pages), lockfale/OSINT-Framework
(`public/arf.json`, MIT), jivoi/awesome-osint (README, CC BY-SA 4.0; this file is an
independent selection, not a copy). Re-check a tool's status before relying on it;
these lists rot.

## Contents

1. Already wired in this repo
2. People, usernames, email, phone
3. Companies, finance, public records
4. Domains, IPs, infrastructure
5. Images, video, verification
6. Geolocation, maps, satellites
7. Social platforms and messaging
8. Archiving and monitoring
9. Crypto / blockchain
10. Transport (air, sea)
11. Threat intel and fraud
12. Methods and tradecraft references
13. Skill libraries worth reading (reference only)

## 1. Already wired in this repo

| Need | Use first |
|---|---|
| Page to evidence | `scripts/capture-evidence.sh` (`--social` for media, `--archivebox`) |
| Page text / site map / deep crawl | `scripts/crawl.sh fetch|map|deep` |
| Change monitoring | `/q-watch` (`scripts/watch.py`) |
| Reverse image (Google Vision) | `scripts/reverse-image.sh`; faces: `/q-face` (founder approval) |
| Shadow-length geolocation band | `scripts/shadowfinder.sh`; full photo geolocation: `skills/geo-sleuth/` |
| Recent public activity of a handle | `scripts/recent-activity.sh` (Bluesky, GitHub, Mastodon) |
| Reddit history incl. deleted | `scripts/reddit-arctic.py` |
| Corporate/public records CLIs | `/q-corp` (`scripts/install-pp.sh`) |
| Telegram channel harvest to XLSX | `skills/telegram-harvest/` |
| STIX / MISP / CSV export | `scripts/export-intel.py` |
| Timeline / map deliverables | `scripts/render-timeline.py`, `scripts/render-map.py` |
| Verification method | `skills/verification/SKILL.md` |

## 2. People, usernames, email, phone

| Tool | What | Link |
|---|---|---|
| WhatsMyName (local/web) | username across ~600 sites, low false-positive list | https://whatsmyname.app |
| Maigret (local) | username across 3000+ sites, parses profiles | https://github.com/soxoj/maigret |
| Sherlock (local) | username enumeration | https://github.com/sherlock-project/sherlock |
| Blackbird (local) | username + email account search | https://github.com/p1ngul1n0/blackbird |
| user-scanner (local) | username/email presence, has an MCP server | https://github.com/kaifcodec/user-scanner |
| Holehe (local) | which sites an email is registered on | https://github.com/megadose/holehe |
| Have I Been Pwned (web, key for API) | breach exposure for an email | https://haveibeenpwned.com |
| Epieos (web) | email / phone to Google + other account traces | https://epieos.com |
| PhoneInfoga (local) | phone number footprinting | https://github.com/sundowndev/phoneinfoga |
| Numbering plans (web) | carrier / range lookup | https://www.numberingplans.com |

People-search aggregators (US) are T3 by definition: name-match results, never a crosslink.

## 3. Companies, finance, public records

| Tool | What | Link |
|---|---|---|
| OpenCorporates (web, key for API) | global company registry index | https://opencorporates.com |
| GLEIF LEI search (web/API, free) | legal-entity identifiers, parent/child trees | https://search.gleif.org |
| SEC EDGAR full-text search (web/API, free) | US filings, Form D, insiders | https://efts.sec.gov/LATEST/search-index?q= / https://www.sec.gov/edgar/search/ |
| UK Companies House (web, free key for API) | officers, PSCs, filings | https://find-and-update.company-information.service.gov.uk |
| OpenSanctions (web/API) | sanctions, PEPs, entities of interest | https://www.opensanctions.org |
| ICIJ Offshore Leaks (web) | Panama/Pandora/Paradise papers entities | https://offshoreleaks.icij.org |
| OCCRP Aleph (web, account) | leaked + public records search | https://aleph.occrp.org |
| CourtListener / RECAP (web/API) | US federal court opinions + dockets | https://www.courtlistener.com |
| FEC (web/API) | US campaign finance | https://www.fec.gov/data/ |
| Senate/House LDA (web/API) | US lobbying disclosures | https://lda.gov |
| EU VIES (web) | EU VAT number validation | https://ec.europa.eu/taxation_customs/vies/ |
| TED (web/API) | EU public procurement notices | https://ted.europa.eu |
| Overseas registries list (gov.uk) | where each country's registry lives | https://www.gov.uk/government/publications/overseas-registries/overseas-registries |

Registry records are T1 for the fact that the record exists and what it says.

## 4. Domains, IPs, infrastructure

| Tool | What | Link |
|---|---|---|
| RDAP / whois (local) | registration data | `whois`, https://rdap.org |
| crt.sh (web) | certificate transparency, subdomains | https://crt.sh |
| DNSDumpster (web) | DNS recon map | https://dnsdumpster.com |
| Mnemonic passive DNS (web) | historic resolutions | https://passivedns.mnemonic.no |
| Shodan InternetDB (web, keyless) | open ports/tags for an IP | https://internetdb.shodan.io |
| Censys / Shodan / Netlas (web, key) | host + certificate search | https://search.censys.io, https://www.shodan.io, https://app.netlas.io |
| BGP.tools / bgp.he.net (web) | ASN, prefixes, peering | https://bgp.tools, https://bgp.he.net |
| URLScan.io (web, key for API) | page scan, linked resources, screenshots | https://urlscan.io |
| VirusTotal (web, key) | reputation, relations, passive DNS | https://www.virustotal.com |
| dnstwist (local) | typosquat / lookalike domains | https://github.com/elceef/dnstwist |
| BuiltWith / Wappalyzer (web/local) | tech stack, shared trackers | https://builtwith.com, https://github.com/projectdiscovery/wappalyzergo |
| katana / subfinder (local) | crawl / passive subdomains | https://github.com/projectdiscovery |
| DNSViz (web) | DNSSEC chain | https://dnsviz.net |

## 5. Images, video, verification

| Tool | What | Link |
|---|---|---|
| Google Lens / Vision (web, key for API) | reverse image, web entities | https://lens.google.com |
| Yandex / Bing / TinEye (web) | reverse image (Yandex strong on faces/places) | https://yandex.com/images, https://tineye.com |
| InVID-WeVerify plugin (browser) | video keyframes, forensic filters | https://www.invid-project.eu/tools-and-services/invid-verification-plugin/ |
| Forensically / FotoForensics (web) | ELA, clone detection, metadata | https://29a.ch/photo-forensics/, https://fotoforensics.com |
| ExifTool (local) | metadata read | https://exiftool.org |
| c2patool (local) | C2PA Content Credentials | https://github.com/contentauth/c2patool |
| yt-dlp / gallery-dl (local) | media download (used by `--social`) | https://github.com/yt-dlp/yt-dlp, https://github.com/mikf/gallery-dl |
| Whisper (local) | transcription / translation | https://github.com/openai/whisper |

## 6. Geolocation, maps, satellites

| Tool | What | Link |
|---|---|---|
| geo-sleuth (local skill) | end-to-end photo geolocation | `skills/geo-sleuth/` |
| ShadowFinder (local) | shadow-length location band | https://github.com/bellingcat/ShadowFinder |
| SunCalc (web) | sun azimuth/altitude for a place + time | https://www.suncalc.org |
| Bellingcat OSM search (web) | find places by feature combination | https://osm-search.bellingcat.com |
| Overpass Turbo (web) | OSM queries | https://overpass-turbo.eu |
| Google Earth Pro (local) | historical imagery | https://www.google.com/earth/versions/ |
| Sentinel Hub EO Browser (web) | free Sentinel/Landsat imagery | https://apps.sentinel-hub.com/eo-browser/ |
| GeoHints (web) | country clues (plates, bollards, poles) | https://geohints.com |
| PeakVisor (web) | mountain skyline identification | https://peakvisor.com |

## 7. Social platforms and messaging

| Tool | What | Link |
|---|---|---|
| Bluesky public API (keyless) | profiles, feeds (used by `recent-activity.sh`) | https://docs.bsky.app |
| Telegram public preview | read public channels without login | `https://t.me/s/<channel>` |
| tgspyder (local, account) | Telegram channel/member scrape | used by `skills/telegram-harvest/` |
| Telepathy (local) | Telegram archiving + member lists | https://github.com/proseltd/Telepathy-Community |
| Arctic Shift (web/API) | Reddit archive incl. deleted | https://arctic-shift.photon-reddit.com |
| Meta Ad Library (web) | ads by page / advertiser | https://www.facebook.com/ads/library/ |
| TikTok / Instagram / X collectors | via Apify actors | `scripts/run-actor.sh`, see `references/platforms.md` |

## 8. Archiving and monitoring

| Tool | What | Link |
|---|---|---|
| bellingcat auto-archiver (local) | media + WACZ + timestamps per URL | https://github.com/bellingcat/auto-archiver |
| ArchiveBox (local, docker) | self-hosted web archive (`--archivebox`) | https://github.com/ArchiveBox/ArchiveBox |
| changedetection.io (local, docker) | page change monitoring (`/q-watch`) | https://github.com/dgtlmoon/changedetection.io |
| crawl4ai (local, docker) | LLM-ready markdown crawl (`crawl.sh`) | https://github.com/unclecode/crawl4ai |
| Scrapling (local) | anti-bot-tolerant fetch fallback | https://github.com/D4Vinci/Scrapling |
| Wayback Machine / archive.today (web) | public archives (LOOKUP only; this instance does not submit) | https://web.archive.org, https://archive.ph |

## 9. Crypto / blockchain

| Tool | What | Link |
|---|---|---|
| Blockchair (web) | multi-chain explorer | https://blockchair.com |
| Etherscan family (web, key for API) | EVM chains | https://etherscan.io |
| Breadcrumbs / MetaSleuth (web) | visual flow tracing | https://www.breadcrumbs.app, https://metasleuth.io |
| Arkham (web, account) | entity labels | https://intel.arkm.com |
| WalletExplorer (web) | BTC wallet clustering | https://www.walletexplorer.com |
| Chainabuse (web) | scam address reports | https://www.chainabuse.com |

On-chain transaction records are T1 for the transfer; address-to-person labels are not.

## 10. Transport (air, sea)

| Tool | What | Link |
|---|---|---|
| FAA registry (web / `/q-corp`) | US aircraft owners | https://registry.faa.gov/aircraftinquiry |
| ADS-B Exchange / Flightradar24 (web) | flight tracks | https://globe.adsbexchange.com, https://www.flightradar24.com |
| MarineTraffic / Global Fishing Watch (web) | vessel positions | https://www.marinetraffic.com, https://globalfishingwatch.org/map |

## 11. Threat intel and fraud

| Tool | What | Link |
|---|---|---|
| abuse.ch (URLhaus, ThreatFox, MalwareBazaar) | IOC lookups | https://abuse.ch |
| AlienVault OTX (web, key) | pulses, IOCs | https://otx.alienvault.com |
| MISP (local) | IOC sharing (import `export-intel.py misp`) | https://www.misp-project.org |
| OpenCTI (local) | STIX knowledge base (import `export-intel.py stix`) | https://github.com/OpenCTI-Platform/opencti |
| SpiderFoot (local) | automated multi-source recon | https://github.com/smicallef/spiderfoot |
| Google Safe Browsing report (web) | report malicious sites | https://safebrowsing.google.com |
| MITRE F3 (Fight Fraud Framework) | fraud TTP catalog (Positioning, Monetization) | https://ctid.mitre.org/fraud/ |

## 12. Methods and tradecraft references

**Bellingcat open-source-research-notebooks** (https://github.com/bellingcat/open-source-research-notebooks):
runnable Colab/Jupyter notebooks. Relevant ones: Telegram phone-number checker,
Wayback Google Analytics (historic analytics IDs that tie sites together), geoclustering
of incident CSVs, search-grid generator (KML for systematic area search), shadow
chronolocator, Whisper transcription, Holehe, Maigret, ExifTool, Deepface. Use them as
method references; run on copies, and register any output you cite as an EV item.

**Estimative language (ICD 203 style).** ODNI ICD 203 analytic standards
(https://www.dni.gov/files/documents/ICD/ICD-203.pdf); the 7onez/cti-expert skill (MIT)
pairs ICD-203 likelihood with Admiralty source grading. Our reimplementation, use in
briefs and findings:

| Term | Probability | Use when |
|---|---|---|
| almost no chance / remote | 1-5% | strong evidence against |
| very unlikely / highly improbable | 5-20% | |
| unlikely / improbable | 20-45% | |
| roughly even chance | 45-55% | evidence balanced |
| likely / probable | 55-80% | |
| very likely / highly probable | 80-95% | |
| almost certainly / nearly certain | 95-99% | multiple independent T1/T2 sources |

Rules: state likelihood and confidence separately (confidence = quality of the evidence
base: high / moderate / low); never stack estimative terms on a T3-only basis; name the
key assumption behind every "likely" or stronger. Map our A-F source reliability onto the
Admiralty letter and the 1-6 credibility number when a client expects NATO grading.

**Org attack surface and email spoofability (for `/q-sec-stack`).** From
elementalsouls/Claude-OSINT (code MIT, content CC BY 4.0; method summarised, cite when used):
- Entity to footprint, discover-only: exact legal entity and LEI (GLEIF org tree) ->
  registries (EDGAR, OpenCorporates, Wikidata) -> reverse-WHOIS on registrant org ->
  crt.sh `?O=<org>` certificate search -> org-first RIR lookup for netblocks registered to
  the org ("dark" netblocks not in DNS) -> ASN scope guard (hyperscaler ranges are not the
  target's).
- Email spoofability verdict: only DMARC governs header-From. SPF `-all` alone is not
  spoof-proof (it checks the envelope sender). Check `p=` (none/quarantine/reject), `pct`,
  subdomain policy `sp=`, alignment (`adkim`/`aspf`). SPF supply chain: more than 10 DNS
  lookups is a PermError (RFC 7208); includes pointing at expired/dead domains are a
  takeover risk. Commands: `dig +short TXT _dmarc.<d>`, `dig +short TXT <d>`, recurse includes.

## 13. Skill libraries worth reading (reference only, not installed)

mukul975/Anthropic-Cybersecurity-Skills (Apache-2.0, 818 skills; MITRE ATT&CK + F3
mappings). Read the SKILL.md of these when the case calls for it; adapt with attribution:

- `building-threat-actor-profile-from-osint`
- `conducting-external-reconnaissance-with-osint`
- `performing-brand-monitoring-for-impersonation`
- `analyzing-typosquatting-domains-with-dnstwist`
- `analyzing-certificate-transparency-for-phishing`
- `investigating-phishing-email-incident` / `analyzing-email-headers-for-phishing-investigation`
- `performing-osint-with-spiderfoot`
- `implementing-security-information-sharing-with-stix2` / `performing-threat-intelligence-sharing-with-misp`
- `generating-threat-intelligence-reports`

Path pattern: `https://github.com/mukul975/Anthropic-Cybersecurity-Skills/tree/main/skills/<name>`.
