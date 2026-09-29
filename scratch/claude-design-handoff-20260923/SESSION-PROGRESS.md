# EMS 前端設計 — session progress (2026-09-23)

## Task
Design the tAIstro EMS front-end screens on a Claude Design canvas, following the frontend-design skill,
matching synaiq-web's style/architecture and the user's reference image (1.webp).

## Canvas
- URL: https://claude.ai/artifact/GioXq64zsCubTuLNX5cndw (Design type, empty shell created)
- Type rules saved at: scratchpad\artifact-files\7f4f4023-e6f6-414d-9339-cd37c69002ea\ (SKILL.md, format.md, craft.md)
- Publish contract: ONE call with url + root=<root> + file_path=<root>\project\canvas.json + files={project/*.dc.html}

## Paths
- Reference image: ...\images\1.webp
- synaiq-web (style source): C:\Users\User\synaiq\synaiq-web
- EMS code (user-confirmed): \\wsl.localhost\Ubuntu\home\dalelin\synaiq\EMS
- EMS report docs: C:\Users\User\Documents\EMS
- Build root (worker output): scratchpad\ems-design\ (PLAN.md, project\)

## Agents in flight
1. DONE — synaiq-web audit distilled to scratchpad\synaiq-web-tokens.md (live site = docs\design\live-prototype,
   paper #f4f4f2 / ink #282825 / olive #647956 / gold #cca858, Newsreader+Noto Serif TC over Manrope+Noto Sans TC,
   logos: LP\assets\synaiq-logo-ink.svg + public\brand\synaiq-logo-light.svg; "tAIstro" not in repo; no dark mode)
2. DONE — EMS domain audit distilled to scratchpad\ems-domain.md (today = simulated meter + KC factory demo; planned
   100 kWh-class BESS EMS; PRD-0005 direction "Precise / Industrial / Alive", visual design assigned to Claude Design;
   no live site — 台北南港展覽館 is only the reference image's label; no tariff rates exist)
USER DECISIONS: 2026-09-23 — screen list = 混合 7 畫面: Main 能源總覽 / Monitor 即時監控 / Demand 需量管理 /
   Storage 儲能管理 / Alarms 警報中心 / Devices 設備分析 / Reports 報表中心. Worker told (Phase 1 update, not GO).
   Wordmark = OFFICIAL tAIstro logo from PDF: \\192.168.0.97\行銷部\99.進行中專案\20260922_taistro_logo\20260922_星洋taistro_LOGO.pdf
   (Read tool cannot render PDFs here — no pdftoppm; extraction agent (opus) produces scratchpad\taistro-logo\
   page-N.png + SVG/PNG variants + README.md with colours). Then: upload PNG as asset if SVG not clean → GO worker.
   User also uploaded a JPG of the logo: ...\images\2.jpg — MONOCHROME geometric sans wordmark "tAIstro", the "A" is a
   stylised upward arrow/chevron mark, dotted "i"; two variants: white on near-black (#231f20-ish) box, black on white.
   In the reference dashboard the wordmark is rendered GOLD on the dark header → use logo paths with fill #cca858.
   SETTLED: official SVGs copied to scratchpad\taistro-logo\ (taistro-01/02/03.svg + jpg) with README.md
   (use taistro-01.svg second <g>, viewBox "235.88 409.41 370.13 72.54", explicit fills). PDF agent was killed by user
   (not needed). Company = 星洋智能科技股份有限公司 / tAistro co., ltd.
3. general-purpose (opus) — design-build worker, PHASE 1 = plan only (PLAN.md), waits for "GO"

## Design worker PHASE 2 DONE (2026-09-23 ~03:05Z): 7 artboards + canvas.json in scratchpad\ems-design\project\
  (Main 1440×900; Monitor 1160; Demand 1080; Storage 1240; Alarms 1120; Devices 1200; Reports 1120 tall; row 2 at y 1360).
  Self-check PASS (check.txt / check.mjs). Tweaks: Main alarmState, Storage mode, all showSketch. Published as
  "v1 seven artboards". Worker now on PHASE 3 (css\). Caveat: gold 2.12:1 → gold marks always have labels/legend.

## Incident 2026-09-23: user saw raw {{holes}} — it was the app Browser pane's auto-opened file:// previews of the
  7 artboards (no support.js runtime locally), NOT the canvas. User confirmed. Tabs closed. Built-in browser cannot
  view claude.ai (not signed in) → canvas rendering is verified only by the user. Runtime files saved for diagnosis
  if ever needed: scratchpad\artifact-files\7f4f4023-…\artifact-type\dc-runtime.js (186 KB) and app.js (3.3 MB).

## Next steps
- 2026-09-23: USER WAIVED plan review ("計畫好了就直接動工，不用再等我確認"). GO sent to the worker with the logo
  hand-off (gold wordmark on dark header, #352f2d on light) and the Phase 2 report format.
- When the Phase 2 report arrives: spot-check (Glob project/*.dc.html, JSON-parse canvas.json, sizes) →
  publish ONE call: url=https://claude.ai/artifact/GioXq64zsCubTuLNX5cndw, root=scratchpad\ems-design,
  file_path=<root>\project\canvas.json, files={"project/X.dc.html":"project/X.dc.html" × 7} → give user the link.
- User judges visually; revisions go through the same worker (SendMessage keeps its context).
- 2026-09-23 USER ADDED: CSS conventions like synaiq-web → worker PHASE 3 builds <root>\css\ (ems-tokens.css numbered
  sections, ems-app.css BEGIN/END blocks with .ems-* classes, STYLE-GUIDE.md zh-Hant incl. Tailwind v4 @theme mapping,
  css-lint.mjs no-hex/no-seconds + artboard hex coverage). Publish css under project/css/ too + SendUserFile.
- 2026-09-23 USER ASKED whether the design references the backend API spec. Honest status: data vocabulary came from
  the audit (openapi.yml PostgREST + registry, BFF measurement route, TimescaleDB schema, ARCH planned entities) via
  ems-domain.md, but NO per-widget endpoint mapping was done. Dispatched an opus agent to write
  scratchpad\ems-design\API-MAPPING.md (API inventory w/ file:line, screen→widget→endpoint table, gap list with
  proposed shapes, naming alignment). Next: feed Part 4 naming to the worker; publish API-MAPPING.md with the package.
- 2026-09-23 USER ASKED: write the gap APIs into the backend PRD (WSL repo doc\prd\). Dispatched PRD-author agent
  (opus) PHASE A = read global guideline C:\Users\User\.claude\guidelines\PRD-Architecture-Guideline.md + repo PRD
  conventions + git status → plan; PHASE B on GO with API-MAPPING.md. Rules: no commit, no code/openapi edits,
  branch dev has uncommitted frontend work — do not disturb. Main session checks the plan; ask user only if ambiguous.
  PHASE A DONE: plan = new PRD-0017-console-data-api-gaps.md (Draft, FR-17xx, 15 guideline chapters, §10 checklist;
  openapi sync + ADR deferred to implementation PR) + one row in doc\prd\README.md. Decisions taken (defaults):
  PRD-0017; convention /api/v1/sites/{site_id}/… + envelope {success,data,error,meta} + cursor pagination +
  Idempotency-Key/If-Match; no reviewer agents. Skeleton drafted in scratchpad\ems-design\prd\ until GO.
  Same convention sent to the API-mapping agent for proposed shapes. Caveats to relay: PRD-0007–0016 numbers are
  provisionally claimed in untracked drafts; guideline mirror differs in paths (not re-synced); untracked
  architecture/program docs will be cited (links break unless committed).
