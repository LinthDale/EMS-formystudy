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
const outputPath = process.argv[2] ?? path.resolve(here, "../../output/ppt/bms-100kwh-specification-proposal.pptx");
const previewDir = process.argv[3] ?? path.resolve(here, "_preview_bms");
const SOURCE = "output/pdf/bms-100kwh-specification.md（BMS 規格書，v0.1）";
const GFL = "GFL A-CPS-7VH4L4-011，314 Ah LFP Product Specification，Rev. A2";
const TOTAL = 19;

const deck = createDeck();

// ============== Slide 1: Cover ==============
{
  const slide = deck.slides.add();
  addCover(
    slide,
    "100 kWh 級電池管理系統\n（Battery Management System, BMS）",
    "適用 1P96S／1P112S GFL 314 Ah LFP 的規格提案",
    "對外提案版｜2026-08｜v0.1",
    "BMS TECHNICAL PROPOSAL",
  );
  setSources(slide, [SOURCE]);
}

// ============== Slide 2: Positioning ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "BMS 把電芯保固轉成可執行的安全邊界", "Value proposition", 2, TOTAL);
  addCallout(slide, "positioning",
    "電芯保固條件的執行者＋電池安全狀態的權威來源＋PCS 的最高硬夾箝",
    { left: 72, top: 158, width: 1136, height: 80 },
    { fill: C.lightBlue, line: C.blue, fontSize: 29, alignment: "center" });
  const bms = makeNode(slide, "role-bms", { left: 466, top: 302, width: 348, height: 158 });
  const cells = makeNode(slide, "role-cells", { left: 82, top: 322, width: 250, height: 118 });
  const pcs = makeNode(slide, "role-pcs", { left: 948, top: 252, width: 250, height: 118 });
  const ems = makeNode(slide, "role-ems", { left: 948, top: 454, width: 250, height: 118 });
  connect(slide, cells, bms, { kind: "straight", fromSide: "right", toSide: "left", color: C.blue });
  connect(slide, bms, pcs, { kind: "elbow", fromSide: "right", toSide: "left", color: C.teal });
  connect(slide, bms, ems, { kind: "elbow", fromSide: "right", toSide: "left", color: C.muted, style: "dashed" });
  styleNode(cells, "GFL 314 Ah 電芯\nV／I／T／保固條件", { fill: C.lightBlue, line: C.blue, fontSize: 23 });
  styleNode(bms, "BMS 本地安全層\n監測・限制・預充・跳脫", { fill: C.lightTeal, line: C.teal, fontSize: 27 });
  styleNode(pcs, "功率轉換系統\n（Power Conversion System, PCS）\n服從限制並即時控流", { fill: C.white, line: C.teal, fontSize: 20 });
  styleNode(ems, "能源管理系統\n（Energy Management System, EMS）\n監看・記錄・派工", { fill: C.slate, line: C.muted, fontSize: 20 });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 3: Two-tier architecture ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "兩層主從架構即可同時支援 96S 與 112S", "System architecture", 3, TOTAL);
  const modules = [];
  for (let i = 0; i < 7; i += 1) {
    modules.push(makeNode(slide, `module-${i + 1}`, { left: 76, top: 218 + i * 50, width: 280, height: 42 }));
  }
  const bcu = makeNode(slide, "bcu", { left: 482, top: 264, width: 292, height: 166 });
  const hv = makeNode(slide, "hv-box", { left: 936, top: 188, width: 250, height: 112 });
  const pcs = makeNode(slide, "arch-pcs", { left: 936, top: 334, width: 250, height: 112 });
  const ems = makeNode(slide, "arch-ems", { left: 936, top: 480, width: 250, height: 112 });
  for (const module of modules) {
    connect(slide, module, bcu, { kind: "elbow", fromSide: "right", toSide: "left", color: C.blue, width: 2, noHead: true });
  }
  connect(slide, bcu, hv, { kind: "elbow", fromSide: "right", toSide: "left", color: C.orange });
  connect(slide, bcu, pcs, { kind: "straight", fromSide: "right", toSide: "left", color: C.teal });
  connect(slide, bcu, ems, { kind: "elbow", fromSide: "right", toSide: "left", color: C.muted, style: "dashed" });
  addText(slide, "bmu-heading", "電池監測單元\n（Battery Monitoring Unit, BMU）× 6／7",
    { left: 54, top: 146, width: 324, height: 64 }, { fontSize: 22, bold: true, color: C.blue, alignment: "center", verticalAlignment: "middle" });
  modules.forEach((module, index) => styleNode(module,
    `模組 ${index + 1}｜BMU ${index + 1}（16S）`,
    { fill: index === 6 ? C.lightOrange : C.lightBlue, line: index === 6 ? C.orange : C.blue, fontSize: 22, shadow: "shadow-none" }));
  styleNode(bcu, "電池控制單元\n（Battery Control Unit, BCU）\n狀態估測・功率邊界\n接觸器與故障管理", { fill: C.lightTeal, line: C.teal, fontSize: 23 });
  styleNode(hv, "高壓箱\n預充・接觸器・熔斷", { fill: C.lightOrange, line: C.orange, fontSize: 22 });
  styleNode(pcs, "PCS\n動態夾箝與控流", { fill: C.white, line: C.teal, fontSize: 22 });
  styleNode(ems, "EMS\n唯讀監看與長期保存", { fill: C.slate, line: C.muted, fontSize: 21 });
  addText(slide, "arch-config", "第 7 片 BMU 為可組態選配，不以不同硬體鎖死 96S／112S",
    { left: 430, top: 568, width: 450, height: 44 }, { fontSize: 20, color: C.muted, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 4: Design basis ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "同一套 BMS 覆蓋兩種容量，量測與保護能力一次到位", "Design basis", 4, TOTAL);
  addTable(slide, "design-basis-table", [
    ["項目", "96S 方案", "112S 方案"],
    ["模組／BMU", "6 × 16S", "7 × 16S"],
    ["標稱簇電壓", "307.2 V", "358.4 V"],
    ["標稱能量", "96.5 kWh", "112.5 kWh"],
    ["工作電壓窗", "240–350.4 V", "280–408.8 V"],
    ["0.5C 基準", "157 A", "157 A"],
    ["1C 基準", "314 A", "314 A"],
  ], { left: 72, top: 166, width: 744, height: 402 }, [252, 246, 246], { fontSize: 21, headerSize: 21 });
  addMetric(slide, "bms-voltage-range", "0–500 V 直流", "簇電壓量測範圍",
    { left: 866, top: 178, width: 300, height: 126 }, { valueColor: C.blue, valueSize: 34 });
  addMetric(slide, "bms-current-range", "至少 ±500 A", "簇電流量測範圍",
    { left: 866, top: 328, width: 300, height: 126 }, { valueColor: C.teal, valueSize: 34 });
  addCallout(slide, "basis-rule", "磷酸鐵鋰（Lithium Iron Phosphate, LFP）單體先達門檻時，簇總壓正常也必須保護",
    { left: 842, top: 484, width: 348, height: 118 }, { fill: C.lightOrange, line: C.orange, fontSize: 22, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 5: Measurement ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "量測一致性決定 LFP 的狀態估測與均衡品質", "Measurement performance", 5, TOTAL);
  addMetric(slide, "measure-v", "±5 mV", "單體電壓準確度\n目標 ±2 mV",
    { left: 72, top: 164, width: 260, height: 150 }, { valueColor: C.blue });
  addMetric(slide, "measure-sync", "≤100 ms", "全串更新週期\n通道差 ≤10 ms",
    { left: 352, top: 164, width: 260, height: 150 }, { valueColor: C.teal });
  addMetric(slide, "measure-temp", "±1°C", "每 16S 至少 4 點",
    { left: 632, top: 164, width: 260, height: 150 }, { valueColor: C.orange });
  addMetric(slide, "measure-current", "≤10 ms", "電流取樣\n讀值的 ±0.5%",
    { left: 912, top: 164, width: 260, height: 150 }, { valueColor: C.navy2 });
  addBullets(slide, "measure-bullets", [
    "電壓解析度 ≤1 mV，但解析度不得冒充準確度。",
    "相對通道誤差 ≤3 mV，並在 1 秒內完成開線診斷。",
    "電流零點漂移校正後 ≤0.1 A，避免待機積分破壞荷電估測。",
    "快速過流保護不得只依賴軟體輪詢；感測飽和與交叉診斷須有明確處置。",
  ], { left: 92, top: 356, width: 1090, height: 240 }, { fontSize: 24, spaceAfter: 10 });
  setSources(slide, [SOURCE]);
}

// ============== Slide 6: SOC and SOH ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "SOC 要可恢復，SOH 要能對應到單顆電芯的壽命終止", "State estimation", 6, TOTAL);
  addText(slide, "soc-title", "荷電狀態（State of Charge, SOC）", { left: 92, top: 166, width: 510, height: 44 }, { fontSize: 30, bold: true, color: C.blue });
  addBullets(slide, "soc-list", [
    "以庫倫積分為主，搭配端點與溫度模型。",
    "靜置時以開路電壓（Open Circuit Voltage, OCV）校正。",
    "斷電、即時時鐘（Real-Time Clock, RTC）失效或更換 BCU 後，須有恢復程序。",
    "SOC 無效時，單體電壓與溫度硬保護仍須有效。",
  ], { left: 84, top: 226, width: 520, height: 292 }, { fontSize: 22, fill: C.lightBlue, line: { style: "solid", fill: C.blue, width: 1.2 }, borderRadius: 18 });
  addText(slide, "soh-title", "健康狀態（State of Health, SOH）", { left: 690, top: 166, width: 510, height: 44 }, { fontSize: 30, bold: true, color: C.teal });
  addBullets(slide, "soh-list", [
    "容量 SOH 與內阻 SOH 分開輸出並保留趨勢。",
    "壽命終止（End of Life, EOL）判據需明訂。",
    "初始門檻：內阻達 150%，或容量低於 70%。",
    "容量、內阻與異常次數須綁定序號及更換紀錄。",
  ], { left: 676, top: 226, width: 520, height: 292 }, { fontSize: 22, fill: C.lightTeal, line: { style: "solid", fill: C.teal, width: 1.2 }, borderRadius: 18 });
  addCallout(slide, "state-estimation-rule", "LFP 中段 OCV 不得作為唯一 SOC 來源",
    { left: 322, top: 552, width: 636, height: 62 }, { fill: C.lightOrange, line: C.orange, fontSize: 25, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 7: Dynamic clamps ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "充放電電流上限是 PCS 每 100 ms 必須服從的動態安全邊界", "Dynamic capability", 7, TOTAL);
  const inputs = [
    ["溫度", 78, 168, C.blue], ["單體 Vmax／Vmin", 78, 248, C.blue],
    ["SOC／SOH", 78, 328, C.teal], ["GFL 倍率曲線", 78, 408, C.teal],
    ["接觸器／熔斷器／線材", 78, 488, C.orange], ["PCS／系統額定", 78, 568, C.orange],
  ];
  const limit = makeNode(slide, "dynamic-limit", { left: 790, top: 282, width: 344, height: 176 });
  const shapes = inputs.map(([label, left, top]) => makeNode(slide, `input-${label}`, { left, top, width: 320, height: 54 }));
  shapes.forEach((shape) => connect(slide, shape, limit, { kind: "elbow", fromSide: "right", toSide: "left", color: C.muted, width: 2 }));
  inputs.forEach(([label, , , color], index) => styleNode(shapes[index], label, { fill: C.white, line: color, fontSize: 20, shadow: "shadow-none" }));
  styleNode(limit, "允許充電電流\n（Charge Current Limit, CCL）\n允許放電電流\n（Discharge Current Limit, DCL）", { fill: C.lightTeal, line: C.teal, fontSize: 24 });
  addMetric(slide, "limit-half-c", "157 A", "0.5C 正常上限",
    { left: 848, top: 492, width: 250, height: 116 }, { valueColor: C.blue, valueSize: 34 });
  addMetric(slide, "limit-one-c", "314 A", "1C 正常上限",
    { left: 470, top: 492, width: 250, height: 116 }, { valueColor: C.teal, valueSize: 34 });
  addText(slide, "limit-note", "正常允許電流 ≠ 過流跳脫點",
    { left: 450, top: 164, width: 700, height: 42 }, { fontSize: 24, bold: true, color: C.red, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 8: Protection levels ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "四級保護讓系統從告警、降載到硬體切斷逐步收斂", "Protection hierarchy", 8, TOTAL);
  const levels = [
    ["L1", "告警", "記錄並上報\n允許持續運轉", C.lightBlue, C.blue],
    ["L2", "降載", "動態降低 CCL／DCL\nPCS 平滑降功率", C.lightTeal, C.teal],
    ["L3", "方向禁止", "CCL 或 DCL 歸零\n禁止充電或放電", C.lightOrange, C.orange],
    ["L4", "緊急跳脫", "PCS 停流＋開接觸器\n極端事件硬體切斷", C.lightRed, C.red],
  ];
  levels.forEach(([code, title, body, fill, line], index) => {
    const top = 162 + index * 118;
    addText(slide, `level-code-${code}`, code, { left: 90, top: top + 17, width: 94, height: 50 }, { fontSize: 34, bold: true, color: line, alignment: "center" });
    addCallout(slide, `level-${code}`, `${title}\n${body}`, { left: 200, top, width: 910, height: 92 }, { fill, line, fontSize: 24, alignment: "left", shadow: "shadow-none" });
  });
  addText(slide, "protection-matrix", "每一項都必須定義：門檻、延遲、遲滯、回復、鎖定、復歸權限與故障碼",
    { left: 162, top: 632, width: 956, height: 32 }, { fontSize: 21, bold: true, color: C.navy, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 9: Voltage and temperature ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "電壓與溫度採漸進降載，不把絕對極限當作工作點", "Voltage & temperature", 9, TOTAL);
  addText(slide, "voltage-head", "單體電壓", { left: 86, top: 160, width: 500, height: 42 }, { fontSize: 30, bold: true, color: C.blue, alignment: "center" });
  addTable(slide, "voltage-table", [
    ["門檻", "初始設定", "動作"],
    ["高壓預警", "3.55–3.60 V", "L1／L2"],
    ["充電禁止", "保證實際 ≤3.65 V", "L3"],
    ["低壓預警", "2.80 V", "L1／L2"],
    ["放電禁止", "2.60 V", "L3"],
    ["絕對低壓", ">0°C 不得 <2.50 V", "L4"],
  ], { left: 72, top: 214, width: 548, height: 350 }, [210, 220, 118], { fontSize: 21, headerSize: 21 });
  addText(slide, "temp-head", "溫度與溫差", { left: 694, top: 160, width: 500, height: 42 }, { fontSize: 30, bold: true, color: C.teal, alignment: "center" });
  addTable(slide, "temperature-table", [
    ["條件", "動作"],
    ["<0°C", "禁止充電 L3"],
    [">45°C", "動態降載 L2"],
    ["≥55°C", "停止充放 L3"],
    ["≥60°C", "緊急跳脫 L4"],
    ["≥65°C", "鎖定關機 L4"],
    ["溫差 >8／12°C", "告警／降載"],
  ], { left: 660, top: 214, width: 548, height: 350 }, [270, 278], { fontSize: 21, headerSize: 21 });
  addCallout(slide, "threshold-note", "名義設定必須計入 ±5 mV 誤差、通訊延遲與 PCS 過衝",
    { left: 228, top: 590, width: 824, height: 58 }, { fill: C.lightOrange, line: C.orange, fontSize: 23, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 10: Current and fail-safe ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "短路與重大失效必須有不依賴 EMS 或一般通訊的本地路徑", "Fail-safe protection", 10, TOTAL);
  addTable(slide, "fail-safe-table", [
    ["故障", "判定／要求", "系統動作"],
    ["連續／瞬時過流", "與 CCL／DCL、PCS 脈衝及熔斷器曲線協調", "降載、方向禁止或開接觸器"],
    ["短路", "最大預期短路電流與直流分斷能力", "硬體切斷"],
    ["絕緣下降", "1 MΩ 告警／500 kΩ 跳脫初值", "告警或停機"],
    ["BMU／感測失效", "不得使用最後值無限運轉", "受控停流後斷開"],
    ["接觸器黏著", "輔助接點＋兩側電壓交叉判定", "鎖定故障"],
    ["消防／緊急停止", "常閉硬線安全迴路", "立即進入緊急安全態"],
  ], { left: 72, top: 164, width: 1136, height: 402 }, [220, 510, 406], { fontSize: 21, headerSize: 21 });
  addCallout(slide, "overcurrent-warning", "157 A／314 A 是正常能力基準，不可直接當作過流跳脫值",
    { left: 196, top: 594, width: 888, height: 60 }, { fill: C.lightRed, line: C.red, color: C.red, fontSize: 24, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 11: Balancing ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "314 Ah 大電芯應用修正能力驗收，而不是只看均衡拓撲", "Cell balancing", 11, TOTAL);
  addMetric(slide, "balance-target", "1% SOC", "3.14 Ah 差異",
    { left: 88, top: 178, width: 280, height: 138 }, { valueColor: C.blue });
  addMetric(slide, "balance-time", "≤12 h", "修正至驗收範圍",
    { left: 390, top: 178, width: 280, height: 138 }, { valueColor: C.teal });
  addMetric(slide, "balance-passive", "≥300 mA", "被動均衡參考",
    { left: 692, top: 178, width: 280, height: 138 }, { valueColor: C.orange });
  addMetric(slide, "balance-active", "1–5 A", "主動均衡參考",
    { left: 994, top: 178, width: 198, height: 138 }, { valueColor: C.navy2, valueSize: 34 });
  addBullets(slide, "balance-bullets", [
    "啟動條件：高 SOC、低充電電流、充電尾段或經確認的靜置狀態。",
    "判定必須使用電壓差＋工作狀態，不依賴 LFP 中段 OCV。",
    "停止條件包含目標壓差、SOC／電流區、電芯溫度與 BMU 板溫。",
    "供應商需提交最壞熱條件、效率、故障隔離與待機功耗實測。",
  ], { left: 92, top: 354, width: 1090, height: 236 }, { fontSize: 24, spaceAfter: 10 });
  addText(slide, "balance-comparison", "100 mA 修正 1% SOC 約需 31.4 h，足以作為性能比較基準",
    { left: 192, top: 612, width: 896, height: 34 }, { fontSize: 21, bold: true, color: C.orange, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 12: High-voltage box ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "高壓箱是 BMS 保護命令真正落地的執行機構", "High-voltage box", 12, TOTAL);
  addCallout(slide, "hv-definition", "高壓（High Voltage, HV）箱由 BMS 控制，並與 PCS 直流鏈共同完成預充與切斷",
    { left: 72, top: 156, width: 1136, height: 70 }, { fill: C.lightBlue, line: C.blue, fontSize: 26, alignment: "center" });
  addBullets(slide, "hv-components", [
    "主正／主負接觸器＋輔助接點：拒動與黏著交叉診斷。",
    "預充接觸器／電阻：依直流鏈（Direct Current Link, DC-link）電容、壓差、時間與重複週期計算。",
    "直流熔斷器：依短路電流、I²t、線材與接觸器完成協調。",
    "維修斷開裝置（Manual Service Disconnect, MSD）。",
    "高壓互鎖迴路（High Voltage Interlock Loop, HVIL）。",
    "絕緣監測裝置（Insulation Monitoring Device, IMD）介面。",
  ], { left: 82, top: 262, width: 744, height: 330 }, { fontSize: 23, spaceAfter: 8 });
  addMetric(slide, "hv-current", "314 A", "1C 連續電流",
    { left: 900, top: 286, width: 244, height: 126 }, { valueColor: C.teal });
  addMetric(slide, "hv-class", "400 A 級", "僅作初始尺寸估算",
    { left: 900, top: 438, width: 244, height: 126 }, { valueColor: C.orange, valueSize: 33 });
  setSources(slide, [SOURCE]);
}

// ============== Slide 13: Precharge state machine ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "預充必須有成功判據、重試上限與人工復歸", "Precharge sequence", 13, TOTAL);
  const off = makeNode(slide, "pre-off", { left: 88, top: 286, width: 174, height: 96 }, "ellipse");
  const test = makeNode(slide, "pre-test", { left: 336, top: 286, width: 194, height: 96 });
  const pre = makeNode(slide, "pre-charge", { left: 602, top: 286, width: 216, height: 96 });
  const run = makeNode(slide, "pre-run", { left: 914, top: 182, width: 190, height: 96 });
  const fault = makeNode(slide, "pre-fault", { left: 914, top: 424, width: 190, height: 96 });
  connect(slide, off, test, { kind: "straight", fromSide: "right", toSide: "left", color: C.blue });
  connect(slide, test, pre, { kind: "straight", fromSide: "right", toSide: "left", color: C.blue });
  connect(slide, pre, run, { kind: "elbow", fromSide: "right", toSide: "left", color: C.teal });
  connect(slide, pre, fault, { kind: "elbow", fromSide: "right", toSide: "left", color: C.red });
  connect(slide, run, off, { kind: "curved", fromSide: "left", toSide: "top", color: C.muted });
  connect(slide, run, fault, { kind: "straight", fromSide: "bottom", toSide: "top", color: C.red });
  connect(slide, fault, off, { kind: "curved", fromSide: "left", toSide: "bottom", color: C.muted });
  styleNode(off, "OFF", { fill: C.slate, line: C.muted, fontSize: 25 });
  styleNode(test, "SELFTEST\n自檢＋絕緣", { fill: C.lightBlue, line: C.blue, fontSize: 22 });
  styleNode(pre, "PRECHARGE\n預充", { fill: C.lightOrange, line: C.orange, fontSize: 23 });
  styleNode(run, "RUN", { fill: C.lightTeal, line: C.teal, fontSize: 26 });
  styleNode(fault, "FAULT\n鎖定故障", { fill: C.lightRed, line: C.red, color: C.red, fontSize: 23 });
  addText(slide, "pre-success", "PCS 側電壓達電池側 90–95%\n且電流降至門檻以下",
    { left: 650, top: 184, width: 220, height: 68 }, { fontSize: 19, color: C.teal, alignment: "center" });
  addText(slide, "pre-failure", "逾時／異常／過熱",
    { left: 650, top: 456, width: 220, height: 44 }, { fontSize: 19, color: C.red, alignment: "center" });
  addCallout(slide, "pre-rule", "失敗後不得無限重試；正常停機先確認 PCS 零電流再開接觸器",
    { left: 248, top: 578, width: 784, height: 58 }, { fill: C.lightBlue, line: C.blue, fontSize: 22, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 14: BMS to PCS communication ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "BMS↔PCS 通訊：資料完整性與失聯動作缺一不可", "PCS interface", 14, TOTAL);
  addText(slide, "can-title", "控制器區域網路（Controller Area Network, CAN）2.0B｜即時週期 ≤100 ms",
    { left: 86, top: 160, width: 1090, height: 42 }, { fontSize: 25, bold: true, color: C.navy, alignment: "center" });
  addBullets(slide, "can-signals", [
    "CCL、DCL、允許電壓、enable、SOC、SOH、簇 V／I。",
    "cell Vmax／Vmin、Tmax／Tmin、接觸器與故障狀態。",
    "循環冗餘校驗（Cyclic Redundancy Check, CRC）、checksum、alive counter、rolling counter、版本識別。",
    "提供受版本控制的通訊資料庫（Database Container, DBC）定義檔，含倍率、偏移、端序、無效值與逾時。",
  ], { left: 72, top: 224, width: 632, height: 324 }, { fontSize: 22, fill: C.lightBlue, line: { style: "solid", fill: C.blue, width: 1.2 }, borderRadius: 18 });
  addText(slide, "timeout-title", "失聯處置", { left: 782, top: 220, width: 380, height: 40 }, { fontSize: 30, bold: true, color: C.teal, alignment: "center" });
  addCallout(slide, "timeout-step1", "3–5 個即時週期遺失\nPCS 平滑降功率至零",
    { left: 778, top: 278, width: 392, height: 104 }, { fill: C.lightTeal, line: C.teal, fontSize: 24, alignment: "center" });
  addCallout(slide, "timeout-step2", "持續失聯且安全停流後\nBMS 開接觸器",
    { left: 778, top: 408, width: 392, height: 104 }, { fill: C.lightOrange, line: C.orange, fontSize: 24, alignment: "center" });
  addText(slide, "timeout-l4", "L4 故障不等待通訊或正常停流程序",
    { left: 764, top: 548, width: 420, height: 44 }, { fontSize: 22, bold: true, color: C.red, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 15: EMS and data ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "完整資料鏈是保固條款，不是附加功能", "Data & warranty", 15, TOTAL);
  addCallout(slide, "data-architecture", "BMS 本地循環緩衝＋EMS／歷史資料庫保存整個設計壽命",
    { left: 72, top: 156, width: 1136, height: 70 }, { fill: C.lightTeal, line: C.teal, fontSize: 27, alignment: "center" });
  addMetric(slide, "data-normal", "≤1 s", "常態資料週期",
    { left: 88, top: 260, width: 250, height: 126 }, { valueColor: C.blue });
  addMetric(slide, "data-local", "≥12 月", "BMS 本地循環保存",
    { left: 358, top: 260, width: 250, height: 126 }, { valueColor: C.teal });
  addMetric(slide, "data-blackbox", "±30 s", "事件前後黑盒子\n≤100 ms 取樣",
    { left: 628, top: 260, width: 250, height: 126 }, { valueColor: C.orange });
  addMetric(slide, "data-life", "全壽命", "EMS 長期保存",
    { left: 898, top: 260, width: 250, height: 126 }, { valueColor: C.navy2 });
  addBullets(slide, "data-bullets", [
    "全單體 V／T、簇 V／I、SOC、SOH、CCL／DCL、絕緣、均衡與接觸器狀態。",
    "支援網路時間協定（Network Time Protocol, NTP）、斷線補傳、缺口標記與校時事件。",
    "匯出格式須公開且具欄位說明，不依賴單一專有軟體取證。",
  ], { left: 92, top: 430, width: 1088, height: 176 }, { fontSize: 23, spaceAfter: 9 });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 16: Power and environment ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "長期停機與戶外環境不能讓 BMS 自己把電池耗到欠壓", "Power & environment", 16, TOTAL);
  addText(slide, "power-title", "24 V 與待機", { left: 96, top: 164, width: 500, height: 44 }, { fontSize: 30, bold: true, color: C.blue, alignment: "center" });
  addBullets(slide, "power-list", [
    "優先使用受監控的外部 24 V 直流輔助電源。",
    "若由高壓電池取電，deep-sleep 等效簇電流目標 ≤2 mA。",
    "支援喚醒與排程維護，避免無限重啟。",
    "靜置 >30 天：SOC 維持 25–40%，至少每 3 個月維護一次。",
  ], { left: 82, top: 224, width: 520, height: 320 }, { fontSize: 22, fill: C.lightBlue, line: { style: "solid", fill: C.blue, width: 1.2 }, borderRadius: 18 });
  addText(slide, "environment-title", "環境與可靠度", { left: 686, top: 164, width: 500, height: 44 }, { fontSize: 30, bold: true, color: C.teal, alignment: "center" });
  addBullets(slide, "environment-list", [
    "電子元件工作溫度至少 -30～70°C。",
    "相對濕度（Relative Humidity, RH）5–95%、無凝露。",
    "印刷電路板組件（Printed Circuit Board Assembly, PCBA）三防塗覆。",
    "連接器防呆、鎖固、維修防誤插。",
    "工業電磁相容性（Electromagnetic Compatibility, EMC）、振動／衝擊與關鍵元件降額可追溯。",
  ], { left: 676, top: 224, width: 520, height: 320 }, { fontSize: 22, fill: C.lightTeal, line: { style: "solid", fill: C.teal, width: 1.2 }, borderRadius: 18 });
  addCallout(slide, "environment-close", "BMS 設計壽命須與電池系統一致",
    { left: 322, top: 574, width: 636, height: 62 }, { fill: C.lightOrange, line: C.orange, fontSize: 25, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

// ============== Slide 17: Certification ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "認證要看整套系統涵蓋範圍，不能只看零組件證書", "Safety & certification", 17, TOTAL);
  addTable(slide, "certification-table", [
    ["層級", "主要路徑", "採購驗證重點"],
    ["單電池／電池系統", "CNS 62619", "電芯型號、串數與延燒要求"],
    ["BMS 功能安全", "IEC／UL 60730-1、IEC 61508 SIL 2、UL 991＋1998 或 ISO 13849", "證書是否涵蓋韌體與組態"],
    ["儲能系統／案場", "CNS 62933-5-2", "風險評鑑、工廠／現場允收、大型燃燒測試"],
    ["PCS", "CNS／IEC 62477-1", "併聯規範與工業 EMC"],
    ["外箱／運輸", "防護等級（Ingress Protection, IP）54、UN 38.3", "防腐蝕、防凝露與運輸條件"],
  ], { left: 72, top: 166, width: 1136, height: 398 }, [230, 440, 466], { fontSize: 21, headerSize: 21 });
  addCallout(slide, "certification-warning", "UL 1973／UL 9540／UL 9540A 是否需要，取決於目標市場與業主要求",
    { left: 180, top: 594, width: 920, height: 60 }, { fill: C.lightOrange, line: C.orange, fontSize: 23, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 18: FAT and SAT ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "工廠與現場允收必須逐項驗證量測、故障與高壓動作", "Verification", 18, TOTAL);
  addText(slide, "fat-title", "工廠允收試驗（Factory Acceptance Test, FAT）", { left: 80, top: 160, width: 550, height: 48 }, { fontSize: 28, bold: true, color: C.blue, alignment: "center" });
  addBullets(slide, "fat-list", [
    "96S／112S 組態、全通道精度與開線。",
    "SOC／SOH／CCL／DCL 參考循環與故障注入。",
    "通訊斷線、時鐘、韌體更新與事件黑盒子。",
    "預充、接觸器、絕緣、均衡與硬線安全迴路。",
  ], { left: 72, top: 224, width: 560, height: 286 }, { fontSize: 22, fill: C.lightBlue, line: { style: "solid", fill: C.blue, width: 1.2 }, borderRadius: 18 });
  addText(slide, "sat-title", "現場允收試驗（Site Acceptance Test, SAT）", { left: 650, top: 160, width: 550, height: 48 }, { fontSize: 28, bold: true, color: C.teal, alignment: "center" });
  addBullets(slide, "sat-list", [
    "實際電池簇、PCS、EMS、消防與 24 V 端到端。",
    "低電壓定功率下驗證 PCS 服從 CCL／DCL。",
    "預充波形、接觸器切換、DC-link 放電與殘壓。",
    "溫升、時間對齊、歷史資料與版本一致性。",
  ], { left: 648, top: 224, width: 560, height: 286 }, { fontSize: 22, fill: C.lightTeal, line: { style: "solid", fill: C.teal, width: 1.2 }, borderRadius: 18 });
  addCallout(slide, "soc-acceptance", "SOC 驗收：新電池 25±2°C 全工作區 ≤±5%；端點校正後 ≤±3%；溫度／老化條件 ≤±8%",
    { left: 112, top: 552, width: 1056, height: 78 }, { fill: C.lightOrange, line: C.orange, fontSize: 22, alignment: "center" });
  setSources(slide, [SOURCE]);
}

// ============== Slide 19: Proposal close ==============
{
  const slide = deck.slides.add();
  addHeader(slide, "規格閉環完成後，BMS 才能成為可簽約的安全承諾", "Proposal close", 19, TOTAL);
  addBullets(slide, "close-list", [
    "確認 96S／112S 與 0.5C／1C 的最終配置。",
    "取得 GFL 受控規格與 BMS 設計審查同意。",
    "凍結 PCS 協定、DBC、過流曲線與熔斷器協調。",
    "選定功能安全證書路徑與 SOC 驗收程序。",
    "定義全服役期資料容量、備份與保固年限。",
    "把故障矩陣、原始 FAT／SAT 數據與版本清單納入交付。",
  ], { left: 80, top: 164, width: 720, height: 410 }, { fontSize: 24, spaceAfter: 10 });
  addCallout(slide, "close-loop",
    "感測精度\n＋ 動態限制\n＋ 故障矩陣\n＋ 高壓切斷\n＋ 通訊失效\n＋ 全壽命資料",
    { left: 876, top: 174, width: 280, height: 326 }, { fill: C.lightTeal, line: C.teal, fontSize: 28, alignment: "center" });
  addText(slide, "close-note", "完整閉環比單一過壓／欠壓數字更能降低整合與保固風險",
    { left: 824, top: 536, width: 384, height: 70 }, { fontSize: 22, bold: true, color: C.navy, alignment: "center" });
  setSources(slide, [SOURCE, GFL]);
}

await exportDeck(deck, outputPath, previewDir);
