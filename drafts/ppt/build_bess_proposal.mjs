import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  C,
  addBullets,
  addCallout,
  addCover,
  addHeader,
  addLine,
  addMetric,
  addTable,
  addText,
  connect,
  createDeck,
  exportDeck,
  makeNode,
  setSources,
  styleNode,
} from "./deck-common.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const outputPath = process.argv[2] ?? path.resolve(here, "../../output/ppt/bess-100kwh-design-proposal.pptx");
const previewDir = process.argv[3] ?? path.resolve(here, "_preview_bess");
const SOURCE = "output/pdf/bess-100kwh-design-report.md（設計與運轉控制研究，v0.1）";
const GFL = "GFL A-CPS-7VH4L4-011，314 Ah LFP Product Specification，Rev. A2";
const TOTAL = 12;

const deck = createDeck();

// ============== Slide 1: Cover ==============
{
  const slide = deck.slides.add();
  addCover(
    slide,
    "100 kWh 級電池儲能系統\n（Battery Energy Storage System, BESS）",
    "從 GFL 314 Ah 電芯到併離網運轉架構",
    "對外提案版｜2026-08｜v0.1",
    "DESIGN & OPERATION PROPOSAL",
  );
  setSources(slide, [SOURCE]);
}

// ============== Slide 2: Executive summary ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "單串即可完成 100 kWh，真正要決定的是容量與功率", "Executive summary", 2, TOTAL);
  addCallout(slide, "summary-answer",
    "建議基準：1P96S／1P112S 單串、帶升壓的併離網 PCS、風冷戶外櫃",
    { left: 72, top: 158, width: 1136, height: 74 },
    { fill: C.lightBlue, line: C.blue, fontSize: 28 });
  addMetric(slide, "metric-energy", "96.5–112.5", "kWh 標稱能量",
    { left: 72, top: 268, width: 330, height: 140 }, { valueColor: C.blue });
  addMetric(slide, "metric-power", "48–113", "kW 功率範圍",
    { left: 437, top: 268, width: 330, height: 140 }, { valueColor: C.teal });
  addMetric(slide, "metric-runtime", "1–2", "h 額定運轉時間",
    { left: 802, top: 268, width: 330, height: 140 }, { valueColor: C.orange });
  addBullets(slide, "summary-bullets", [
    "功率轉換系統（Power Conversion System, PCS）負責毫秒級併離網控制與安全跳脫。",
    "能源管理系統（Energy Management System, EMS）負責排程、備援策略、記錄與告警。",
    "先由用途選擇 0.5C／1C，再由容量門檻決定 96S／112S。",
  ], { left: 86, top: 448, width: 1040, height: 170 }, { fontSize: 23, spaceAfter: 9 });
  setSources(slide, [SOURCE], ["以一句話先回答系統形狀，再進入選型依據。"]);
}

// ============== Slide 3: Cell design basis ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "電芯條件不只決定容量，也直接約束機構、控制與保固", "Design basis", 3, TOTAL);
  addMetric(slide, "cell-v", "3.2 V", "標稱電壓",
    { left: 72, top: 164, width: 245, height: 126 }, { valueColor: C.blue });
  addMetric(slide, "cell-ah", "314 Ah", "標稱容量",
    { left: 337, top: 164, width: 245, height: 126 }, { valueColor: C.teal });
  addMetric(slide, "cell-kwh", "≈1.0 kWh", "每顆標稱能量",
    { left: 602, top: 164, width: 245, height: 126 }, { valueColor: C.orange });
  addMetric(slide, "cell-c", "0.5C / 1C", "標準／最大連續倍率",
    { left: 867, top: 164, width: 341, height: 126 }, { valueColor: C.navy2 });
  addBullets(slide, "cell-constraints", [
    "磷酸鐵鋰（Lithium Iron Phosphate, LFP）電壓窗：2.50–3.65 V。",
    "充電溫度 0–60°C；低於 0°C 禁充，放電溫度 -30–60°C。",
    "成組需 300±50 kgf 預緊並保留 0.5–1.5 mm 膨脹間隙。",
    "電池管理系統（Battery Management System, BMS）須全程記錄電壓／電流／溫度，形成保固證據。",
  ], { left: 72, top: 326, width: 750, height: 274 }, { fontSize: 23, spaceAfter: 9 });
  addCallout(slide, "cell-guardrail", "不可把電芯絕對上限\n當成日常運轉設定",
    { left: 870, top: 346, width: 300, height: 174 },
    { fill: C.lightOrange, line: C.orange, color: C.navy, fontSize: 28, alignment: "center" });
  addText(slide, "cell-guardrail-note", "設計需預留量測誤差、延遲、溫升與老化裕度",
    { left: 870, top: 536, width: 300, height: 66 },
    { fontSize: 19, color: C.muted, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 4: Stack architecture ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "1 顆約 1 kWh，經 16S 模組堆疊成單一高壓電池簇", "System architecture", 4, TOTAL);
  const nodes = [
    makeNode(slide, "cell", { left: 74, top: 250, width: 184, height: 132 }),
    makeNode(slide, "module", { left: 300, top: 250, width: 200, height: 132 }),
    makeNode(slide, "cluster", { left: 542, top: 234, width: 236, height: 164 }),
    makeNode(slide, "pcs", { left: 820, top: 250, width: 184, height: 132 }),
    makeNode(slide, "grid-load", { left: 1046, top: 250, width: 162, height: 132 }),
  ];
  connect(slide, nodes[0], nodes[1], { kind: "straight", fromSide: "right", toSide: "left" });
  connect(slide, nodes[1], nodes[2], { kind: "straight", fromSide: "right", toSide: "left" });
  connect(slide, nodes[2], nodes[3], { kind: "straight", fromSide: "right", toSide: "left" });
  connect(slide, nodes[3], nodes[4], { kind: "straight", fromSide: "right", toSide: "left" });
  styleNode(nodes[0], "電芯\n3.2 V · 314 Ah\n≈1.0 kWh", { fill: C.lightBlue, line: C.blue, fontSize: 21 });
  styleNode(nodes[1], "1P16S 模組\n51.2 V\n16.1 kWh", { fill: C.white, line: C.blue, fontSize: 21 });
  styleNode(nodes[2], "1P96S / 1P112S\n307 / 358 V\n96.5 / 112.5 kWh", { fill: C.lightTeal, line: C.teal, fontSize: 22 });
  styleNode(nodes[3], "雙向 PCS\n升壓＋併離網", { fill: C.white, line: C.teal, fontSize: 21 });
  styleNode(nodes[4], "400 V 交流\n電網／重要負載", { fill: C.lightOrange, line: C.orange, fontSize: 20 });
  addText(slide, "times-16", "×16 串", { left: 242, top: 214, width: 82, height: 28 }, { fontSize: 18, bold: true, color: C.blue, alignment: "center" });
  addText(slide, "times-67", "×6 或 7 串", { left: 470, top: 196, width: 126, height: 28 }, { fontSize: 18, bold: true, color: C.teal, alignment: "center" });
  addCallout(slide, "single-string-reason", "單串（1P）避免並聯環流與串間平衡，讓 BMS 架構最單純",
    { left: 244, top: 470, width: 792, height: 72 }, { fill: C.lightBlue, line: C.blue, fontSize: 26, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 5: Four configurations ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "96S／112S 決定容量，0.5C／1C 決定功率", "Configuration options", 5, TOTAL);
  addTable(slide, "configuration-table", [
    ["方案", "串數", "能量", "倍率", "功率", "工時", "建議 PCS"],
    ["A1", "96S", "96.5 kWh", "0.5C", "48 kW", "2 h", "50 kW"],
    ["A2", "96S", "96.5 kWh", "1C", "96 kW", "1 h", "100 kW"],
    ["B1", "112S", "112.5 kWh", "0.5C", "56 kW", "2 h", "60 kW"],
    ["B2", "112S", "112.5 kWh", "1C", "113 kW", "1 h", "125 kW"],
  ], { left: 72, top: 164, width: 1136, height: 306 }, [118, 130, 170, 132, 150, 120, 190], { fontSize: 20, headerSize: 20 });
  addCallout(slide, "capacity-rule", "容量門檻\n<100 kWh 可選 96S\n需帳面破百選 112S",
    { left: 112, top: 508, width: 470, height: 118 }, { fill: C.lightBlue, line: C.blue, fontSize: 24, alignment: "center" });
  addCallout(slide, "power-rule", "用途門檻\n能量型選 0.5C\n功率型選 1C",
    { left: 698, top: 508, width: 470, height: 118 }, { fill: C.lightTeal, line: C.teal, fontSize: 24, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 6: Decision recommendation ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "先用商業用途選倍率，再用容量規格選串數", "Selection logic", 6, TOTAL);
  addText(slide, "energy-title", "能量型用途", { left: 94, top: 174, width: 470, height: 46 }, { fontSize: 32, bold: true, color: C.blue, alignment: "center" });
  addLine(slide, "energy-line", 122, 228, 414, C.blue, 3);
  addMetric(slide, "energy-c", "0.5C", "2 小時系統",
    { left: 118, top: 260, width: 200, height: 130 }, { valueColor: C.blue });
  addMetric(slide, "energy-heat", "0.8–1.0", "kW 簇發熱",
    { left: 342, top: 260, width: 200, height: 130 }, { valueColor: C.teal });
  addBullets(slide, "energy-use", ["削峰填谷", "時段套利", "光電自用"],
    { left: 130, top: 424, width: 400, height: 164 }, { fontSize: 24, fill: C.lightBlue, line: { style: "solid", fill: C.blue, width: 1.2 }, borderRadius: 16 });
  addText(slide, "power-title", "功率型用途", { left: 716, top: 174, width: 470, height: 46 }, { fontSize: 32, bold: true, color: C.teal, alignment: "center" });
  addLine(slide, "power-line", 744, 228, 414, C.teal, 3);
  addMetric(slide, "power-c", "1C", "1 小時系統",
    { left: 740, top: 260, width: 200, height: 130 }, { valueColor: C.teal });
  addMetric(slide, "power-heat", "3.3–3.9", "kW 簇發熱",
    { left: 964, top: 260, width: 200, height: 130 }, { valueColor: C.orange });
  addBullets(slide, "power-use", ["快速充放", "調頻輔助", "大功率備援"],
    { left: 752, top: 424, width: 400, height: 164 }, { fontSize: 24, fill: C.lightTeal, line: { style: "solid", fill: C.teal, width: 1.2 }, borderRadius: 16 });
  setSources(slide, [SOURCE]);
}

// ============== Slide 7: Thermal design ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "1C 的主要限制從電流轉成散熱與溫差", "Thermal strategy", 7, TOTAL);
  const plot = { left: 132, top: 196, width: 482, height: 280 };
  for (let i = 0; i <= 4; i += 1) {
    const gx = plot.left + (plot.width * i) / 4;
    slide.shapes.add({
      geometry: "line",
      name: `heat-grid-${i}`,
      position: { left: gx, top: plot.top, width: 0, height: plot.height },
      fill: "none",
      line: { style: "solid", fill: C.line, width: 1 },
    });
    addText(slide, `heat-axis-${i}`, String(i), { left: gx - 18, top: 486, width: 36, height: 30 },
      { fontSize: 18, bold: true, color: C.navy, alignment: "center" });
  }
  addLine(slide, "heat-row-top", plot.left, 196, plot.width, C.line, 1);
  addLine(slide, "heat-row-mid", plot.left, 336, plot.width, C.line, 1);
  addLine(slide, "heat-row-bottom", plot.left, 476, plot.width, C.line, 1);
  addText(slide, "heat-cat-1c", "1C", { left: 78, top: 246, width: 42, height: 34 },
    { fontSize: 22, color: C.navy, alignment: "right" });
  addText(slide, "heat-cat-05c", "0.5C", { left: 62, top: 386, width: 58, height: 34 },
    { fontSize: 22, color: C.navy, alignment: "right" });
  slide.shapes.add({ geometry: "rect", name: "heat-bar-1c",
    position: { left: plot.left, top: 220, width: plot.width * 0.90, height: 86 },
    fill: C.teal, line: { style: "solid", fill: C.teal, width: 1 } });
  slide.shapes.add({ geometry: "rect", name: "heat-bar-05c",
    position: { left: plot.left, top: 360, width: plot.width * 0.225, height: 86 },
    fill: C.teal, line: { style: "solid", fill: C.teal, width: 1 } });
  addText(slide, "heat-value-1c", "3.6", { left: 572, top: 247, width: 48, height: 34 },
    { fontSize: 22, bold: true, color: C.navy, alignment: "center" });
  addText(slide, "heat-value-05c", "0.9", { left: 244, top: 387, width: 48, height: 34 },
    { fontSize: 22, bold: true, color: C.navy, alignment: "center" });
  addText(slide, "heat-chart-label", "估算連續發熱（kW）", { left: 90, top: 536, width: 520, height: 34 }, { fontSize: 19, color: C.muted, alignment: "center" });
  addCallout(slide, "hvac-callout", "1C 建議暖通空調\n（Heating, Ventilation and Air Conditioning, HVAC）\n約 2–2.5 冷凍噸",
    { left: 700, top: 174, width: 442, height: 142 }, { fill: C.lightOrange, line: C.orange, fontSize: 25, alignment: "center" });
  addBullets(slide, "thermal-bullets", [
    "電芯進出風端溫差目標 <8°C。",
    "高溫環境與連續滿功率需搭配降載。",
    "感測點需涵蓋電芯、匯流排與熱點。",
  ], { left: 694, top: 350, width: 462, height: 210 }, { fontSize: 23, spaceAfter: 10 });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 8: Grid / island architecture ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "帶升壓的 hybrid PCS 同時對接 307／358 V 直流電池與 400 V 交流母線", "Grid / island architecture", 8, TOTAL);
  const battery = makeNode(slide, "arch-battery", { left: 86, top: 278, width: 220, height: 122 });
  const pcs = makeNode(slide, "arch-pcs", { left: 388, top: 246, width: 260, height: 186 });
  const grid = makeNode(slide, "arch-grid", { left: 848, top: 168, width: 286, height: 118 });
  const load = makeNode(slide, "arch-load", { left: 848, top: 386, width: 286, height: 118 });
  const ems = makeNode(slide, "arch-ems", { left: 400, top: 508, width: 236, height: 96 });
  connect(slide, battery, pcs, { kind: "straight", fromSide: "right", toSide: "left", tail: true, color: C.blue });
  connect(slide, pcs, grid, { kind: "elbow", fromSide: "right", toSide: "left", tail: true, color: C.teal });
  connect(slide, pcs, load, { kind: "elbow", fromSide: "right", toSide: "left", color: C.orange });
  connect(slide, ems, pcs, { kind: "straight", fromSide: "top", toSide: "bottom", color: C.muted, style: "dashed" });
  styleNode(battery, "電池簇\n307 / 358 V 直流", { fill: C.lightBlue, line: C.blue, fontSize: 24 });
  styleNode(pcs, "併離網 PCS 一體機\n升壓＋併網跟隨\n離網組網＋黑啟動", { fill: C.white, line: C.teal, fontSize: 24 });
  styleNode(grid, "電網公共耦合點\n（Point of Common Coupling, PCC）\n並網櫃／防孤島／電表", { fill: C.lightTeal, line: C.teal, fontSize: 21 });
  styleNode(load, "重要負載盤\n靜態切換開關\n（Static Transfer Switch, STS）", { fill: C.lightOrange, line: C.orange, fontSize: 21 });
  styleNode(ems, "EMS\n模式協調／觀測", { fill: C.slate, line: C.muted, fontSize: 21 });
  addCallout(slide, "architecture-boundary", "PCS 執行即時切換與保護；EMS 只下監督式設定值",
    { left: 720, top: 542, width: 452, height: 64 }, { fill: C.lightBlue, line: C.blue, fontSize: 23, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 9: Indoor / outdoor ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "戶外櫃增加箱體成本，但可降低建物整合與消防複雜度", "Deployment form", 9, TOTAL);
  addText(slide, "outdoor-title", "戶外櫃｜建議", { left: 100, top: 168, width: 480, height: 50 }, { fontSize: 32, bold: true, color: C.teal, alignment: "center" });
  addBullets(slide, "outdoor-list", [
    "防護等級（Ingress Protection, IP）54–55。",
    "自帶 HVAC、加熱、防凝露與消防。",
    "需抗紫外線、防雷、抗腐蝕與基座。",
    "洩爆與消防邊界較容易獨立定義。",
  ], { left: 92, top: 232, width: 500, height: 304 }, { fontSize: 23, fill: C.lightTeal, line: { style: "solid", fill: C.teal, width: 1.5 }, borderRadius: 18 });
  addText(slide, "indoor-title", "戶內櫃｜替代方案", { left: 700, top: 168, width: 480, height: 50 }, { fontSize: 32, bold: true, color: C.blue, alignment: "center" });
  addBullets(slide, "indoor-list", [
    "箱體可簡化至 IP20–31。",
    "建物須承擔通風、防火與逃生距離。",
    "建築消防審查與施工界面增加。",
    "適合已有合格機房與環控設施的場址。",
  ], { left: 688, top: 232, width: 500, height: 304 }, { fontSize: 23, fill: C.lightBlue, line: { style: "solid", fill: C.blue, width: 1.5 }, borderRadius: 18 });
  addCallout(slide, "deployment-conclusion", "對一般新建案場：戶外櫃可讓責任邊界更清楚、審查路徑更直接",
    { left: 180, top: 574, width: 920, height: 64 }, { fill: C.lightOrange, line: C.orange, fontSize: 25, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 10: Operating state machine ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "一台本地狀態機完成併網、離網、黑啟動與故障收斂", "Operating state machine", 10, TOTAL);
  const standby = makeNode(slide, "state-standby", { left: 126, top: 282, width: 210, height: 104 }, "ellipse");
  const grid = makeNode(slide, "state-grid", { left: 440, top: 176, width: 226, height: 112 });
  const island = makeNode(slide, "state-island", { left: 440, top: 420, width: 226, height: 112 });
  const fault = makeNode(slide, "state-fault", { left: 842, top: 282, width: 226, height: 112 });
  connect(slide, standby, grid, { kind: "curved", fromSide: "right", toSide: "left", color: C.blue });
  connect(slide, standby, island, { kind: "curved", fromSide: "right", toSide: "left", color: C.orange });
  connect(slide, grid, island, { kind: "straight", fromSide: "bottom", toSide: "top", tail: true, color: C.teal });
  connect(slide, grid, fault, { kind: "curved", fromSide: "right", toSide: "left", color: C.red });
  connect(slide, island, fault, { kind: "curved", fromSide: "right", toSide: "left", color: C.red });
  connect(slide, fault, standby, { kind: "curved", fromSide: "left", toSide: "right", color: C.muted });
  styleNode(standby, "待機", { fill: C.slate, line: C.muted, fontSize: 26 });
  styleNode(grid, "併網運轉", { fill: C.lightBlue, line: C.blue, fontSize: 26 });
  styleNode(island, "離網供電", { fill: C.lightOrange, line: C.orange, fontSize: 26 });
  styleNode(fault, "故障保護", { fill: C.lightRed, line: C.red, color: C.red, fontSize: 26 });
  addText(slide, "state-label-1", "市電正常＋運轉命令", { left: 250, top: 214, width: 210, height: 28 }, { fontSize: 18, color: C.blue, alignment: "center" });
  addText(slide, "state-label-2", "無市電＋備援足夠", { left: 250, top: 462, width: 210, height: 28 }, { fontSize: 18, color: C.orange, alignment: "center" });
  addText(slide, "state-label-3", "失電／復電併回", { left: 676, top: 333, width: 150, height: 28 }, { fontSize: 18, color: C.teal, alignment: "center" });
  addCallout(slide, "state-rule", "EMS 決定要做什麼；PCS 決定如何即時做到",
    { left: 310, top: 574, width: 660, height: 62 }, { fill: C.lightBlue, line: C.blue, fontSize: 25, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 11: SOC reserve ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "荷電狀態分帶把日常收益與停電備援切成可管理邊界", "SOC strategy", 11, TOTAL);
  addText(slide, "soc-fullname", "荷電狀態（State of Charge, SOC）", { left: 72, top: 156, width: 520, height: 36 }, { fontSize: 23, bold: true, color: C.navy });
  const x = 120; const y = 250; const width = 1040; const height = 92;
  slide.shapes.add({ geometry: "rect", name: "soc-stop", position: { left: x, top: y, width: width * 0.10, height }, fill: C.lightRed, line: { style: "solid", fill: C.red, width: 1 } });
  slide.shapes.add({ geometry: "rect", name: "soc-reserve", position: { left: x + width * 0.10, top: y, width: width * 0.15, height }, fill: C.lightOrange, line: { style: "solid", fill: C.orange, width: 1 } });
  slide.shapes.add({ geometry: "rect", name: "soc-daily", position: { left: x + width * 0.25, top: y, width: width * 0.70, height }, fill: C.lightTeal, line: { style: "solid", fill: C.teal, width: 1 } });
  slide.shapes.add({ geometry: "rect", name: "soc-top", position: { left: x + width * 0.95, top: y, width: width * 0.05, height }, fill: C.slate, line: { style: "solid", fill: C.muted, width: 1 } });
  addText(slide, "soc-stop-label", "離網卸載\n0–10%", { left: x, top: y + 15, width: width * 0.10, height: 64 }, { fontSize: 18, bold: true, color: C.red, alignment: "center", verticalAlignment: "middle" });
  addText(slide, "soc-reserve-label", "備援保留\n10–25%", { left: x + width * 0.10, top: y + 15, width: width * 0.15, height: 64 }, { fontSize: 19, bold: true, color: C.orange, alignment: "center", verticalAlignment: "middle" });
  addText(slide, "soc-daily-label", "日常併網循環區\n25–95%", { left: x + width * 0.25, top: y + 15, width: width * 0.70, height: 64 }, { fontSize: 24, bold: true, color: C.teal, alignment: "center", verticalAlignment: "middle" });
  addText(slide, "soc-top-label", "停充", { left: x + width * 0.95, top: y + 27, width: width * 0.05, height: 38 }, { fontSize: 16, bold: true, color: C.muted, alignment: "center" });
  addBullets(slide, "soc-bullets", [
    "併網日常只使用 95%↔25%，保留 15% 給停電時動用。",
    "市電正常但 SOC 低於 25% 時，EMS 優先補回備援線。",
    "BMS 回報的允許充放電電流始終是 PCS 的最高夾箝。",
  ], { left: 132, top: 394, width: 1016, height: 180 }, { fontSize: 24, spaceAfter: 11 });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 12: Decisions and next steps ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "六項外部條件確認後，系統即可收斂成可採購規格", "Proposal close", 12, TOTAL);
  addBullets(slide, "decision-list", [
    "主要用途：削峰／套利，或調頻／大功率備援。",
    "容量門檻：96.5 kWh 是否可接受，或必須 ≥100 kWh。",
    "關鍵負載與停電支撐時間，用來反推備援 SOC。",
    "場址溫度與連續滿功率工況，用來凍結風冷與降載。",
    "公共耦合點（PCC）型式、防孤島與復電併回規則。",
    "切換需求：自動切換為秒級；無縫供電需 <20 ms。",
  ], { left: 82, top: 164, width: 708, height: 410 }, { fontSize: 24, spaceAfter: 10 });
  addCallout(slide, "proposal-recommendation",
    "建議先鎖定\n用途 × 容量 × 併網條件\n再進入 PCS 與櫃體詢價",
    { left: 850, top: 206, width: 316, height: 230 }, { fill: C.lightTeal, line: C.teal, fontSize: 31, alignment: "center" });
  addText(slide, "proposal-close-note", "這三個決策會同步決定功率、熱設計、保護與成本。",
    { left: 836, top: 466, width: 344, height: 78 }, { fontSize: 22, color: C.muted, alignment: "center" });
  setSources(slide, [SOURCE]);
}

await exportDeck(deck, outputPath, previewDir);
