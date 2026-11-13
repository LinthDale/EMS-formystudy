# tAIstro logo hand-off (official files, copied 2026-09-23)

Source folder: \\192.168.0.97\行銷部\99.進行中專案\20260922_taistro_logo  (AI, PDF, 3 SVG, 3 JPG previews)
Local copies (ASCII names) in this folder: taistro-01.svg / -02.svg / -03.svg and matching .jpg previews.
Company: 星洋智能科技股份有限公司 · tAistro co., ltd.  (the wordmark is the company brand; the EMS is its product)

## Variants
| file | content | colours |
|---|---|---|
| taistro-01.svg | TWO copies of the wordmark: first `<g>` = white wordmark on a dark rect (rect x130.6 y113.33 w580.7 h200.42); second `<g>` = dark wordmark on white | white #fff on #352f2d; dark #352f2d |
| taistro-02.svg | white wordmark on a gradient box (#231815 → #3e3a39) + `<text>` company name (Noto Sans TC 500) | needs fonts; do not use |
| taistro-03.svg | dark wordmark with a drop-shadow filter + `<text>` "tAistro co., ltd." | filter + text; do not use |

## The wordmark geometry (use taistro-01.svg, SECOND `<g>` — lines 30–42 — the dark variant; all fills are `class="cls-2"`)
Letters, left → right: t · A (two polygons forming an upward arrow) · i (rect stem + circle dot) · s · t · r · o.
Tight bounding box of that group (computed from the path data):
  x 235.88 → 606.01  (width 370.13)      y 409.41 → 481.95  (height 72.54)      aspect ≈ 5.10 : 1
=> viewBox="235.88 409.41 370.13 72.54"
Nothing else is inside the group (no background rect) — the rect belongs only to the first group.

## How to inline it in an artboard
- Copy the 9 shapes of the second group (5 `<path>`, 1 `<rect>`, 1 `<circle>`, 2 `<polygon>`) verbatim — geometry untouched.
- Remove every `class="…"`; put an explicit `fill="#hex"` on each shape (or one `fill` on the wrapping `<g>`).
- Wrap as `<svg viewBox="235.88 409.41 370.13 72.54" role="img" aria-label="tAIstro" style="height: 26px; width: auto; display: block;">…</svg>`
  (at 26 px tall the wordmark is ≈ 133 px wide; at 22 px ≈ 112 px).
- Header (dark #292a2e): fill GOLD #cca858 — this is how the user's reference dashboard renders the wordmark.
  Brand-standard alternative is white #ffffff (the official reversed version); switching is a one-attribute change.
- On paper/light surfaces (e.g. login card, report header, print): fill #352f2d (official dark).
- Never stretch (keep width:auto), never add a box behind it, never rebuild the letters with a font.

## Colours
| hex | role |
|---|---|
| #352f2d | official dark wordmark / dark box |
| #ffffff | reversed wordmark |
| #231815 → #3e3a39 | gradient box in the lockup variant (not needed for UI) |
