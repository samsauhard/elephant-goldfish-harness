# Harness Lab comparison website

Buildless HTML, CSS, and JavaScript explaining direct API review, EGM, and EGM with grounded evidence checks. It includes dataset selection, synchronized metrics, three evidence views, and an illustrative inventory walkthrough.

From the repository root:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory site
```

Open <http://127.0.0.1:8765/>. Stop the server with Ctrl+C. There is no build step, model API call, secret, or Sites account requirement. Fonts are loaded from Google Fonts when available, with local font fallbacks.

`data.js` contains recorded measurements from `benchmarks/results/2026-11-02-hard.json`, `2026-11-02-grounded.json`, and the grounded audit. “Direct API*” uses the closest saved proxy: one generic reviewer with basic validation and repair. The raw direct command is now runnable, but has no recorded benchmark yet. The inventory pair has no generic baseline, and missing values are displayed explicitly rather than as zero.

The original EGM measurement also includes a basic harness. The third approach adds the grounded evidence contract. These are not three cleanly isolated levels of all harness functionality. See [the three-approach guide](../docs/three-approaches.md).

The page preserves the November 2 experiment's historical 70-test count. Current source tests and the runnable entry points are described in the repository README and guide. The hosted Sites deployment is private; these standalone assets can be served independently.
