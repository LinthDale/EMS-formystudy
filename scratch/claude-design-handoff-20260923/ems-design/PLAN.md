# tAIstro EMS — Claude Design canvas build plan

Status: FINAL (Phase 1 + coordinator update + GO, 2026-09-23). Inputs: reference image `images/1.webp`,
`synaiq-web-tokens.md` (token source), `ems-domain.md` (metrics, states, demo set), `taistro-logo/` (wordmark).
Evidence for every colour decision: `_tools/` (contrast + dataviz validator runs, ASCII reports).

---

## A. Aesthetic statement

**Direction: "Paper-and-Ink Control Room" (紙墨控制室)** — luxury-refined industrial, rendered in the synaiq-web idiom:
warm paper, ink type, olive as the working accent, gold used sparingly, light serif display over a sans body.

| Adjective (PRD-0005) | How it is executed | Maps to reference |
|---|---|---|
| **Precise** | Newsreader Light numerals (-0.055em, unit at 0.38em), hairline-ruled rows, every number derived from ONE snapshot object so widgets always agree (186 + 142 + 58 = 386 kW) | bronze serif numerals with small kW units; hairline cards |
| **Industrial** | charcoal chrome (#292a2e header / #1d1e20 sidebar), line-art assets (pylon, PV array, hall, BESS container), single-line-diagram vocabulary, state machine for BESS modes | dark header/sidebar, illustrated energy assets, blueprint texture |
| **Alive** | flow strokes whose weight scales with live kW, "5 秒前更新" recency, data-quality flags (GOOD / STALE), hover crosshair on trends, state-driven ack / shelve / confirm | olive arrows between assets, live-looking dashboard |

**The ONE unforgettable element:** the energy-flow drawing on 能源總覽 — the site drawn as a pencil elevation on paper
(pylon, PV array under a gold sun, exhibition hall, BESS container), joined by flow lines coloured by source whose stroke
weight is proportional to the live kW, with each reading set like an engineer's annotation in Newsreader Light numerals.

Motion: none. The canvas format keeps CSS inline (no keyframes, no :hover in `<helmet>`), so "Alive" is carried by data
cues, not animation. The CSS package (Phase 3) carries the site's motion tokens + reduced-motion switch for the real app.

## B. Artboards (7) and canvas layout

| file | title | w×h | x, y | interactive | purpose |
|---|---|---|---|---|---|
| Main.dc.html | 能源總覽 | 1440×900 | 0, 0 | true | reference-faithful site overview: flow drawing, demand card + status, KPI row, today's load vs contract, energy mix, alert card |
| Monitor.dc.html | 即時監控 | 1440×1160 | 1520, 0 | true | query bar (point, metrics, range, aggregation, 查詢, 匯出 CSV), 24 h history (kW + V + A small multiples), live readings, all-points table |
| Demand.dc.html | 需量管理 | 1440×1080 | 3040, 0 | true | display-only: contract vs 15-min demand (96 bars), month peak, over-contract risk, Taipower 3-period TOU ribbons, bill 估算 |
| Storage.dc.html | 儲能管理 | 1440×1240 | 4560, 0 | true | SOC ring with SOC bands, SOH, mode state machine, schedule + actual P + SOC, BMS cells, PCS P/Q, protection thresholds |
| Alarms.dc.html | 警報中心 | 1440×1120 | 0, 1360 | true | level summary, active list with 確認 / 擱置 (state), detail with lifecycle + runbook, 7-day history |
| Devices.dc.html | 設備分析 | 1440×1200 | 1520, 1360 | true | fleet KPIs, device list (lifecycle, comm, last seen, availability), AI confirmation queue (state), fleet status bars |
| Reports.dc.html | 報表中心 | 1440×1120 | 3040, 1360 | true | report filters, Aug-2026 monthly report (KPIs + daily stacked bars), generated list, audit & command history |

Spacing: 80 px between frames in a row (x = 0 / 1520 / 3040 / 4560); 120 px between rows
(row 1 bottom = tallest frame 1240 → row 2 y = 1360).

Notes (kind `title1`, one per row, ≥ 223 px above it, over nothing, off name strips):
- `row1`: x 0, y -300, "能源營運／ENERGY OPERATIONS", maxW 6000 (row 1 width).
- `row2`: x 0, y 1060, "維運與報表／O&M · REPORTS", maxW 1440 — sits in the free band under Main (Main ends at y 900,
  Monitor starts at x 1520), 300 px above row 2. Invariant: row 1's tallest frame must stay ≥ 1200 so the note keeps
  ≥ 120 px clear of Main.
canvas.json: `{"v":3,"createdOnFiles":{"v":1,"at":<now>},"title":"tAIstro EMS 前端畫面","launch":{"view":"canvas"},
"pages":[],"boards":{…},"order":[7 files],"notes":{row1,row2},"designSystems":[]}`.
Style-sheet artboard: not built (decision I-1).

## C. Per-screen content inventory (sample snapshot 2026-09-23 週三 14:32:05, Asia/Taipei — every screen carries a 示意資料 slip)

Tags: **[D]** from ems-domain.md coherent set · **[=]** derived arithmetically from [D] · **[S]** invented sample (示意資料) ·
**[P]** unknown fact → visible [PLACEHOLDER] / "以台電公告為準" tag.

Shared chrome: header (tAIstro wordmark gold · hairline · "EMS 能源管理系統" gold serif letter-spaced; site switcher
"台北南港展覽館專案" [D demo label]; bell "2 則未讀" [S]; user "使用者 · 維運" [D role label]); sidebar 7 links
能源總覽 · 即時監控 · 需量管理 · 儲能管理 · 警報中心 · 設備分析 · 報表中心 (active = aria-current + inset 2 px gold bar +
olive-lifted band); sidebar footer "星洋智能科技股份有限公司 / tAistro co., ltd.".

**Main 能源總覽**
- 即時能源流: 電網 186 kW [D] · 太陽能 142 kW [D] (≈180 kWp) · 儲能系統 58 kW 放電 [D] · 廠區負載 386 kW [D];
  flow weights 1.25 + 0.015·kW px [=]; tagline 智慧能源 驅動永續未來 (reference copy).
- 需量管理 card: 契約容量 500 kW [D] · 本月最高需量 428 kW [D] · meter 達約 85.6 % [=].
- System status: 系統正常 / 能源系統運行正常，無異常警示。(tweak `alarmState=alarm` → 需注意, 1 重要 + 1 一般).
- KPI row: 即時用電 386 kW · 太陽能發電 142 kW · 儲能狀態 78 % (SOH 98 % · GRID_TIE · 放電 58 kW [D]) ·
  今日節省 NT$ 2,360 估算 [S] (reference's 12,680 is ~3× what 180 kWp PV + 209 kWh BESS can save by 14:32).
- 本日用電趨勢: load 00:00–14:30 in 15-min points [S shape, peak 452 kW 13:15], contract line 500 kW + gold callout,
  now marker 14:32, hover crosshair (time · kW · % of contract).
- 能源組成 (即時): 太陽能 142 (36.8 %) · 電網 186 (48.2 %) · 儲能放電 58 (15.0 %) [=]; centre 即時負載 386 kW.
  The reference's "其他 1 %" and "今日總用電 386 kW" (energy labelled with a power unit) are corrected.
- 即時警示: empty state 目前無警示事件 + link "前往警報中心" → Alarms.dc.html (the new console replaces "查看報表").

**Monitor 即時監控** (replaces the Grafana "EMS 能源監控" dashboard)
- Query bar: 量測點 PCC 台電受電點 · M-01; 指標 checkboxes 功率 / 電壓 / 電流 / 頻率 / 功率因數; 時間範圍 radio
  近 1 小時 / 近 24 小時 / 近 7 天 / 自訂; 彙總 1 分 / 15 分 / 1 小時; buttons 查詢, 匯出 CSV.
- History (rolling 24 h, 15-min): 有效功率 kW (grid import 180–330 kW [S]) + small multiples 電壓 V (376–384, ±5 % band)
  and 電流 A [=] on one shared x axis (no dual axis); crosshair shared by the three plots.
- Live readings (PCC, 1-min avg): 186.0 kW · 79.2 kvar [=] · 380.4 V [D] · 307 A [=] · 60.00 Hz [D] · PF 0.92 [D] ·
  累計電量 1,284,562 kWh [S] · 品質 GOOD.
- All points (kW / kvar / V / A / Hz / PF / 品質 / 更新): PCC 186.0/79.2 · PV INV-01~03 142.0/0.0 PF 1.00 ·
  PCS-01 58.0/13.2 · 空調 LV-A 212.0/53.1 PF 0.97 · 照明插座 LV-B 96.0/13.7 PF 0.99 · 動力 LV-C 78.0/25.6 PF 0.95
  (loads sum 386 kW; PCC Q = 92.4 − 13.2 = 79.2 kvar → PF 0.92) [=] with [S] split.

**Demand 需量管理** (display-only, release 1)
- KPIs: 契約容量 500 kW [D] · 本月最高需量 428 kW (09/12 16:45 [S]) · 目前 15 分鐘需量 186 kW (區間 14:30–14:45) [=] ·
  超約風險 低 (距契約 72 kW [=]).
- 96-slot 15-min demand bars (grid import; 58 complete + 1 in progress) [S shape], lines 契約容量 500 (gold-deep dashed)
  and 本月最高 428 (muted dashed), per-bar hover; demand defined as 15-min average aligned to :00/:15/:30/:45 [D].
- TOU (台電三段式時間電價): ribbons 夏月平日 / 夏月週六 / 非夏月平日 / 週日及離峰日 in off / mid / peak tints,
  windows drawn as a sample with a visible "[PLACEHOLDER] 時段以台電最新公告為準" tag [P]; today = 夏月平日.
- 本月電費估算 (估算・示意, no rate shown): 基本電費 NT$ 118,000 · 流動電費 NT$ 554,000 · 功率因數 0.92 無附加 ·
  超約附加費 NT$ 0 · 合計 NT$ 672,000 [S]; rule text only: 超約部分依台電規定加倍計收 [D].

**Storage 儲能管理**
- SOC 78 % [D] ring with bands 95 max · 30 黑啟動 · 25 備援 · 10 孤島 [D]; SOH 98 % [D]; 58 kW 放電 [D];
  可用能量 163.0 kWh [=] of 209 kWh / 200 kW [D]; 距備援下限約 1.9 h [=].
- Mode state machine STANDBY / GRID_TIE / ISLAND / FAULT [D] (tweak `mode` previews each); dispatch priority
  安全 > 備援 > 需量／削峰 > 時間電價套利 > 太陽能自用 [D].
- Schedule [D example + S]: 離峰充電 00:00–06:00 · 半尖峰放電 14:00–15:00 · 夜尖峰放電 18:00–20:00 (執行率目標 ≥ 80 % [D]);
  hourly actual P (charge below zero) + SOC line 25 → 95 → 92.8 → 78 (now) → 65 → 25 % [=].
- BMS: 電芯 Vmax 3.42 / Vmin 3.38 V [D] · Tmax 31 °C [D] / Tmin 27 °C [S] · 絕緣 3.2 MΩ [S] · 允許充放電流 280 A [S].
- PCS: P 58.0 kW · Q 13.2 kvar [=] · 380.6 V / 60.00 Hz · DC 716.8 V / 83.4 A [S/=] · 上限 200 kW [D].
- Protection: SOC bands; 45 降載 / 55 暫停 / 65 停機 °C; 電芯 3.55–3.60 V 預警 / 2.80 V 低壓; 絕緣 1 MΩ 警告 /
  500 kΩ 跳脫; L1 警報 · L2 降載 · L3 禁止充放 · L4 緊急跳脫 [D].

**Alarms 警報中心** (scale P0 緊急 / P1 重要 / P2 一般 / 資訊 — design scale, domain leaves it undefined [D])
- Summary: P0 0 · P1 1 · P2 2 · 資訊 1 [S].
- Active [S, rules from D]: P1 空調控制器 HVAC-01 資料中斷超過 2 分鐘 (STALE, 14:29:48) · P2 AI 分類防護攔截 6 次／小時
  (ENV-02) · P2 LLM 預算用量 82 % (ACKED 13:05) · 資訊 儲能排程 14:00 開始半尖峰放電.
- Actions: 確認 (ACKED ≠ CLEARED) and 擱置 (SHELVED) per row, tab filter 進行中 / 已擱置 / 全部, row select → detail.
- Detail: lifecycle NORMAL → PENDING → ACTIVE → ACKED → CLEARED [D]; runbook (P0/P1 carry runbooks [D]);
  escalation → Telegram 維運群組 [D] → "[PLACEHOLDER] 值班主管".
- History 7 days [S], e.g. PCS-01 通訊逾時 (CLEARED), 電芯電壓預警 3.55 V (L1), PCC 需量 ≥ 385 kW (本月最高 90 %).

**Devices 設備分析**
- KPIs [S]: 裝置總數 24 · 通訊正常 22 · 資料延遲 1 (STALE) · 維護中 1 · 待人工確認 3 · 30 天可用率 99.4 %.
- Device list (type / 協定 / 位置 / 生命週期 candidate→confirmed→active→maintenance→retired / 通訊 GOOD·STALE /
  最後上線 / 可用率) [D fields, S rows]: PCC M-01 grid_meter · BMS-01 battery · PCS-01 battery · INV-01..03
  solar_inverter · HVAC-01 hvac (STALE, consistent with the P1 alarm) · ENV-02 temperature · FP-01 消防盤 (type [P]).
- AI confirmation queue [S]: 10.0.3.27:502 → solar_inverter 0.91 · MQTT sub-07 → electricity 0.74 · 10.0.3.41:502 →
  hvac 0.58; evidence signal chips; actions 確認 / 修正類型 / 退回 (state).
- Fleet status: 100 % stacked bars for lifecycle and comm quality (replaces Grafana's pie).

**Reports 報表中心**
- Filters: 報表類型 日報 / 月報, 期間 2026 年 8 月, 場域, 產生報表; header buttons 匯出 PDF / 匯出 CSV.
- Aug-2026 monthly [S, generated deterministically; KPIs are the sums of the bars]: 總用電量 · 市電供電 · 太陽能 ·
  儲能放電 kWh, 最高需量 497 kW (08/14 16:45), 電費估算 NT$ (估算); 31 stacked daily bars grid / PV / BESS.
- Generated list: 09/22 日報 · 09/21 日報 · 2026 年 8 月 月報 · 2026 年 7 月 月報 (下載 buttons).
- 稽核與指令紀錄 (唯讀) [D event types, S rows]: command.pcs.setpoint · guardrail_block · status_advance ·
  ai_feedback_create · schedule run · freeze_override (雙人覆核), actors ops 維運 / ai / system.

## D. Tokens (synaiq-web adopted; derived values marked ◆ with the check that justifies them)

**Fonts** — one css2 link per artboard:
`Manrope 400;500 · Newsreader ital,opsz,wght 6..72 300/400 (+italic) · Noto Sans TC 400;500 · Noto Serif TC 300;400`.
- display: `Newsreader, "Noto Serif TC", "Songti TC", PMingLiU, serif` — H1, card titles, figures, notes.
- body: `Manrope, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif` — UI, tables, axis ticks.
- Figures: weight 300, letter-spacing -0.055em, unit 0.38em (min 12 px), `lining-nums`; tables/axes `tabular-nums`.
- Scale (1.333 × 14): 19 card title · 25 flow/secondary figure · 33 page H1 · 44 KPI figure · 59 hero (SOC); plus site
  fixed sizes 12 eyebrow/caption/axis · 13 small button · 14 body/nav · 15 button. Line-height: body 1.75, UI 1.4,
  headings 1.25, figures 1. Tracking: headings -0.02em, eyebrow 0.06em, header title 0.12em.

**Palette** (contrast on card #f8f8f7 unless noted)

| token | hex | role / check |
|---|---|---|
| chrome-header | #292a2e | header (site --dark) |
| chrome-sidebar | #1d1e20 | sidebar (site dark section) |
| nav-active ◆ | #2d3229 | active nav band, olive-lifted as in the reference (paper text 11.9:1, gold 5.8:1) |
| chrome-hairline ◆ | #5a503b | vertical hairline in the header lockup (gold at 30 % over header) |
| chrome-line ◆ | #45474c | site-switcher outline on dark (decorative) |
| inverse | #c4c4be | nav labels/icons on dark (9.52:1 sidebar, 8.18:1 header) |
| paper | #f4f4f2 | page ground; text on dark (15.15:1 sidebar) |
| card | #f8f8f7 | card surface (paper-light) |
| warm-paper | #f2f0e8 | inner panels, 示意資料 slip |
| film | #d5d5ce | card border, row rules |
| rule | #b4b4ac | axis baseline, strong dividers |
| table-head | #e9e9e3 | table header row, chart gridlines, info tint |
| slip-border | #afafa0 | paper slip border (site paper card) |
| ink | #282825 | text (13.91:1), primary button fill |
| muted | #64645e | secondary text (5.60:1 card, 5.41 paper, 4.89 lit, 4.73 sage) |
| olive | #647956 | working accent: marks, icons, PV series, load area (4.48:1 as mark) — not small text |
| olive-ink ◆ | #576a4a | olive text (5.54:1 card, 4.84 lit) |
| sage | #e1e7dc | icon chips, meter track |
| lit | #e5ebdc | system-normal card, good tint |
| kpi-green | #345e40 | highlighted figure (7.00:1) |
| gold | #cca858 | wordmark, section bars, active nav bar, grid series, callout fill (ink on gold 6.55:1) — never text on light |
| gold-deep ◆ | #9b7b31 | information-bearing gold marks: contract/threshold dashed lines (3.75:1) |
| slate | #34383a | BESS series, avatar (11.15:1) |
| good | #426d4b | status good (5.61:1 card, 4.90 lit) |
| warn ◆ | #a5762e / #8a5f21 / #f6ecd7 | mark 3.78:1 · text 5.28:1 (4.79 on tint) · tint |
| danger ◆ | #a55445 / #96493e / #f9e9e5 | mark 5.00:1 · text 5.95:1 (5.37 on tint) · tint |
| p2-tint ◆ | #f6ead1 | P2 chip tint (ink 12.40:1) with gold mark |
| tou-off/mid/peak ◆ | #f7f3eb / #f1e5cc / #e5d0a6 | TOU ribbons (ink labels ≥ 9.79:1) |
| shadows | #dedfd477 · #28282519 · #0002 | paper slip, tooltip (site) |

Warn / danger were derived by moving hue only (warn H 75, danger H 32) while holding olive's lightness band
(L 0.50–0.60) and gold's chroma (C ≈ 0.10–0.11) — same family, reserved for status, always with icon + label.

**Chart categorical (energy sources, fixed order, never cycled):** PV olive #647956 · Grid gold #cca858 · BESS slate
#34383a. Validator (`_tools/tokens2.txt`, all pairs, card surface): CVD worst ΔE 18.0 (protan) PASS, normal-vision
21.4 PASS; lightness-band / chroma-floor misses are the brand's muted neutrals (documented exception); gold 2.12:1 →
relief: always legend + direct label. No "其他" slot (grey vs gold fails the normal floor at 9.9).

Radii: card 14 · inner panel 9 · button 12 · input 10 · list item 8 · pill 999 · slip 0. Borders: 1 px film; slip
1 px #afafa0 with 3 px bottom, rotate(-1.2deg). Shadows: cards none (hairline only); slip `4px 8px 0 #dedfd477`;
tooltip `0 16px 30px #0002`. Spacing: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40. Layout: header 74 (site nav height),
sidebar 208, content gutter 24, card padding 20, grid gap 16. Buttons: ink fill, paper text, 1 px ink border,
radius 12, min-height 46 (small 42), padding 11 × 20, Manrope 500 15 / 13. Pills: 1 px rule, 999, 12 px 500, 0.06em.

## E. Chart and illustration approach

All geometry is computed in `renderVals()` from one `snap` object and bound through dotted holes; nothing is drawn by
script. Format safety: `<sc-for>` / `<sc-if>` are used ONLY at HTML level (never inside `<svg>`, never inside
`<table>` — tables are CSS-grid divs with ARIA table roles, avoiding HTML foster-parenting); SVG presentation
properties go in inline `style` (stroke, fill, stroke-width, stroke-dasharray); every SVG element is explicitly closed.
Demo series are deterministic arrays / seeded formulas (never Math.random) so hover re-renders never jitter.

| chart | build |
|---|---|
| Area + dashed contract line + callout (Main, Monitor) | `d="{{trend.area}}"` / `{{trend.line}}` from a monotone-cubic path; gridlines as one path; contract `y` → dashed gold-deep line; callout = HTML box positioned by computed `top/left`; tick labels = HTML `<sc-for>` overlay; peak dot r 4 + 2 px surface ring; hover = one overlay div `onMouseMove` → state index → crosshair + tooltip in `<sc-if>` |
| Donut + centre label (Main) | three arc paths (`d="{{mix.pv}}"` …) with 2 px surface gaps; centre and legend in HTML |
| Bars (Demand 96 slots, Storage ± bars, Reports stacked) | whole series merged into one `d` path per colour (4 px rounded data-end, square at baseline, ≤ 24 px); in-progress bar as its own path; hover via overlay index |
| Meter (Main demand, Demand risk, Devices availability) | HTML track (sage) + fill (olive → warn at ≥ 90 % → danger > 100 %) with a contract tick |
| Small multiples + sparkline (Monitor V / A) | separate SVGs sharing x scale; ±5 % band as a rect |
| SOC ring (Storage) | track circle + arc path; SOC-band ticks computed as short radial paths |
| TOU ribbons (Demand, Storage) | HTML grid `repeat(24, minmax(0, 1fr))` via `<sc-for>` of 24 cells per row |
| Stacked 100 % bars (Devices fleet) | HTML flex segments with computed widths, 2 px gaps |

Illustrations (literal static SVG, 1.25 px ink strokes, round joins, minimal fills): pylon (lattice + insulators),
PV array (two tilted panel rows, olive 15 % fill, gold sun), exhibition hall (elevation with mullions, canopy, trees),
BESS container (corrugation, doors, gold bolt), plus pencil sketches (sidebar bottom and flow-card corner) in low-alpha
strokes, toggled by the `showSketch` tweak.

## F. Assets

Logo (settled): official tAIstro wordmark, `taistro-01.svg` second `<g>` — 5 path + 1 rect + 1 circle + 2 polygon,
geometry verbatim, classes removed, explicit `fill` per shape; wrapper
`<svg viewBox="235.88 409.41 370.13 72.54" role="img" aria-label="tAIstro" style="height: 26px; width: auto; display: block;">`.
Header fill gold #cca858; on light surfaces #352f2d. Never stretched, no box behind, never rebuilt with a font.
Lockup: wordmark · 1 px hairline · "EMS 能源管理系統" (display serif, gold, 0.12em). SynaIQ is not shown anywhere.
No raster uploads needed; all icons are inline stroke SVG in the lucide idiom (the React app uses lucide).

## G. Interactivity

- Every artboard: sidebar `<a href="X.dc.html">` to all seven screens (is_interactive true), `aria-current="page"`.
- Main: 前往警報中心 link; trend hover crosshair; tweaks `alarmState`, `showSketch`.
- Monitor: metric checkboxes (state toggles the small multiples), range / aggregation radios (state), shared hover.
- Demand: per-bar hover readout. Storage: tweak `mode` (state machine + chip preview).
- Alarms: tabs, 確認 / 擱置 per row, row select → detail (all state). Devices: filter chips, queue 確認 / 修正 / 退回.
- Reports: 日報 / 月報 radio switches the report heading and bar granularity.
- Static by design: site switcher, bell, user menu, export buttons, 查詢 / 產生報表 (real buttons, no-op).
- No cross-artboard shared state; no global key handlers; no timers.

## H. Build order, size, self-check

Order: Main → Monitor → Demand → Storage → Alarms → Devices → Reports → canvas.json → `check.mjs` → fix → re-run once.
Expected ≈ 650–900 lines per artboard (inline styles on one line per element).
Self-check (`<root>/check.mjs` → `<root>/check.txt`, ASCII only, nothing printed but an exit code):
JSON.parse canvas.json + every data-props (after `&amp;` / `&#39;` decode); boards ↔ order ↔ files; spacing rule and note
offsets; exact `<script src="./support.js"></script>` once; `lang="zh-Hant"`, charset, title; root `width/height` =
board w/h = `$preview`; tag balance with a stack (void elements exempt, no `/>` self-closing anywhere); every attribute
quoted; holes are dotted lookups; sc-for / sc-if carry hint attrs and never sit inside `<svg>` / `<table>`; no emoji
code points; no `innerHTML`, `appendChild`, iframe/object/embed, `data:`, `class=`; only one external URL (fonts css2);
every `href` target exists; every `<button>` has text or aria-label; every `<input>` has a matching `<label for>`.

### Hard-rule compliance map
1 skeleton + exact support.js line → template + check · 2 helmet = font link + base style only → template ·
3 fixed root = board = $preview → check · 4 flex/grid + gap → every sibling group · 5 holes are lookups, geometry in
renderVals → E · 6 no script DOM / iframe / emoji / data: / extra network → check · 7 real controls, aria-label,
contrast → D table + check · 8 sidebar links + is_interactive → G · 9 few tweaks, literal zh-TW copy → G ·
10 canvas.json shape + spacing + notes → B · 11 no filler, samples labelled, unknown facts [PLACEHOLDER] → C ·
12 over-tall not clipped → B sizes.

## I. Decisions (open questions closed at GO with the recommended defaults)

1. Style-sheet artboard — not on the canvas; the Phase 3 CSS package + STYLE-GUIDE.md is the implementation contract.
2. Main alarm state — default = reference-calm (系統正常 / 目前無警示事件); tweak `alarmState=alarm` shows the same
   P1 + P2 alarms as 警報中心, so the two screens can be shown coherently.
3. Page length — full-length pages (1080–1240 tall) for the six non-reference screens; Main stays 1440×900.
4. Reference corrections kept small and stated: 今日總用電 kW → 即時負載 kW; 尖峰需量 → 本月最高需量; savings recomputed
   as a plausible 估算; alert card links to 警報中心; olive arrows re-coloured by source (grid gold, BESS slate) so the
   flow drawing and the donut share one legend.
5. TOU windows are not in the hand-off → drawn as a sample with a visible [PLACEHOLDER] confirm tag.
