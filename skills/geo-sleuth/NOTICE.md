# NOTICE -- geo-sleuth companion skill

`SKILL.md` in this folder is an adaptation (condensed and rewritten, with
Investigators Copilot evidence-routing added) of the geo-sleuth agent skill:

- Upstream: https://github.com/Oldcircle/geo-sleuth (`skills/geo-sleuth/SKILL.md`, `README.md`)
- Retrieved: 2026-10-10
- License: MIT

```
MIT License

Copyright (c) 2026 Oldcircle

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

Upstream scripts are NOT vendored here; they are installed separately and run
as-is. Upstream notes: tables in its `data/` derived from Wikipedia are
CC BY-SA 4.0; OpenStreetMap query results are ODbL ("(c) OpenStreetMap
contributors" when published).

Related tool referenced by this skill: bellingcat/ShadowFinder (MIT), called via
`scripts/shadowfinder.sh` as a subprocess, not vendored.
