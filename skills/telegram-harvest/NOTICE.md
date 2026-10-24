# NOTICE -- telegram-harvest

Ported 2026-10-10 from the founder's own repository
https://github.com/assafkip/account-procurement-tools
(`account-procurement-pipeline/`: `src/scrape.py`, `src/lang_translate.py`,
`src/extract.py`, `src/geo_clues.py`, `src/build_sheet.py`, `src/pipeline.py` ->
`scripts/harvest.py`, `install_models.py`, `config/keywords.json`,
`config/countries.json`). That repository carries no LICENSE file; it is reused here
as first-party code by the same owner. Changes: case-folder output routing,
offline CSV mode, `--no-translate`, configurable rule profiles, per-channel cap,
capture batch (`urls.tsv`) for the EV evidence protocol.

Third-party components (called, not vendored):
- tgspyder (Darksight Analytics, MIT) -- Telegram scraper, run as a subprocess.
- Argos Translate (MIT) and its CTranslate2 models -- offline translation.
- lingua-language-detector (Apache-2.0) -- language detection.
- openpyxl (MIT) -- workbook writer.
