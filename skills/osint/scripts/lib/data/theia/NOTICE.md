# Vendored data: theia (KTLYST Labs)

The JSON files in this directory are copied verbatim from the theia project
(`app/lib/` at commit `93013f957ff36c4e6e6caf8018be162d1d3ba39c`, 2026-09-30).
The Python logic in `../../ioc_extract.py` is a port of theia's
`iocExtract.mjs`, `grounding.mjs`, `context.mjs`, `section.mjs`,
`attackIds.mjs` and `entities.mjs`.

| File | SHA-256 | Upstream source |
|------|---------|-----------------|
| `tlds.json` | `58697ea57a3ceb90b2e0a7aa1dc8bee940521e31e3abf62ad7a55c5d40da40a1` | IANA root-zone TLD list |
| `gazetteer.json` | `7908076013fd5f1ce04a7f7f0f23b0d18e1d9719049f360f7360496e6f53731b` | MITRE ATT&CK STIX (enterprise) + Malpedia families, built by theia `scripts/build-gazetteer.mjs` |
| `entity-stoplist.json` | `3c6f8d08f114fc56d9840d69260c902e1059b58ea854773b9d5ad72fe32568e5` | theia curated false-positive stoplist |

Upstream data licenses still apply to the gazetteer content: MITRE ATT&CK
(see https://attack.mitre.org/resources/legal-and-branding/terms-of-use/) and
Malpedia (CC BY-SA 4.0). To refresh, re-run theia's
`node scripts/build-gazetteer.mjs` and copy the outputs here, updating the
hashes above.

## theia license (MIT)

```
MIT License

Copyright (c) 2026 KTLYST Labs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
