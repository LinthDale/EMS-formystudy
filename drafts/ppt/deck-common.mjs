// Shared presentation helpers for the two 100 kWh BESS proposal decks.
// Generated with @oai/artifact-tool; all geometry is in 1280 x 720 CSS pixels.

import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

export const W = 1280;
export const H = 720;
export const FONT = "Microsoft JhengHei";
export const C = {
  navy: "#0B2A4A",
  navy2: "#123E67",
  blue: "#1D5F91",
  teal: "#009C95",
  orange: "#F59E0B",
  red: "#D94B4B",
  green: "#2B8A66",
  text: "#17202A",
  muted: "#5B677A",
  line: "#D6E0E8",
  bg: "#F7F9FC",
  white: "#FFFFFF",
  lightBlue: "#E9F2FA",
  lightTeal: "#E7F7F5",
  lightOrange: "#FFF4DD",
  lightRed: "#FCEBEC",
  slate: "#EDF1F5",
};

export function createDeck() {
  const deck = Presentation.create({ slideSize: { width: W, height: H } });
  deck.theme.colorScheme = {
    name: "BESS Proposal",
    themeColors: {
      accent1: C.blue,
      accent2: C.teal,
      accent3: C.orange,
      accent4: C.red,
      accent5: C.navy2,
      accent6: C.green,
      bg1: C.white,
      bg2: C.bg,
      tx1: C.text,
      tx2: C.muted,
      dk1: "#000000",
      dk2: C.navy,
      lt1: C.white,
      lt2: C.line,
      hlink: C.blue,
      folHlink: "#6D4AA5",
    },
  };
  return deck;
}

export function addText(slide, name, text, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: 22,
    color: C.text,
    verticalAlignment: "top",
    autoFit: "shrinkText",
    wrap: "square",
    insets: { top: 2, right: 2, bottom: 2, left: 2 },
    ...style,
  };
  return shape;
}

export function addLine(slide, name, left, top, width, color = C.line, weight = 2) {
  return slide.shapes.add({
    geometry: "line",
    name,
    position: { left, top, width, height: 0 },
    fill: "none",
    line: { style: "solid", fill: color, width: weight },
  });
}

export function addHeader(slide, title, section, page, total) {
  slide.background.fill = C.bg;
  addText(slide, `section-${page}`, section.toUpperCase(),
    { left: 72, top: 28, width: 400, height: 24 },
    { fontSize: 16, bold: true, color: C.teal });
  addText(slide, `title-${page}`, title,
    { left: 72, top: 56, width: 1090, height: 66 },
    { fontSize: 46, bold: true, color: C.navy, lineSpacing: 0.95 });
  addLine(slide, `title-rule-${page}`, 72, 130, 1136, C.line, 1.5);
  addText(slide, `page-${page}`, `${String(page).padStart(2, "0")} / ${String(total).padStart(2, "0")}`,
    { left: 1110, top: 666, width: 98, height: 24 },
    { fontSize: 16, bold: true, color: C.muted, alignment: "right" });
  addText(slide, `footer-${page}`, "100 kWh BESS 提案",
    { left: 72, top: 666, width: 260, height: 24 },
    { fontSize: 16, color: C.muted });
}

export function addCover(slide, title, subtitle, meta, deckKind) {
  slide.background.fill = "linear(135deg, #071B30 0%, #0B2A4A 58%, #1D5F91 100%)";
  slide.shapes.add({
    geometry: "rect",
    name: "cover-accent",
    position: { left: 72, top: 94, width: 12, height: 466 },
    fill: C.teal,
    line: { style: "solid", fill: "none", width: 0 },
  });
  addText(slide, "cover-kicker", deckKind,
    { left: 116, top: 92, width: 620, height: 34 },
    { fontSize: 20, bold: true, color: "#7DE2DB" });
  addText(slide, "cover-title", title,
    { left: 116, top: 148, width: 1030, height: 192 },
    { fontSize: 66, bold: true, color: C.white, lineSpacing: 0.9 });
  addText(slide, "cover-subtitle", subtitle,
    { left: 116, top: 366, width: 950, height: 94 },
    { fontSize: 30, color: "#D6E9F6", lineSpacing: 1.05 });
  addLine(slide, "cover-rule", 116, 492, 930, "#5A8BAD", 2);
  addText(slide, "cover-meta", meta,
    { left: 116, top: 514, width: 900, height: 42 },
    { fontSize: 20, color: "#BFD3E2" });
}

export function addBullets(slide, name, items, position, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: options.fill ?? "none",
    line: options.line ?? { style: "solid", fill: "none", width: 0 },
    borderRadius: options.borderRadius,
  });
  shape.text.set(items.map((item) => ({
    bulletCharacter: "•",
    marginLeft: 25,
    indent: -13,
    spaceAfter: options.spaceAfter ?? 7,
    runs: [{ run: item }],
  })));
  shape.text.style = {
    typeface: FONT,
    fontSize: options.fontSize ?? 23,
    color: options.color ?? C.text,
    lineSpacing: options.lineSpacing ?? 1.12,
    verticalAlignment: options.verticalAlignment ?? "top",
    autoFit: "shrinkText",
    wrap: "square",
    insets: options.insets ?? { top: 8, right: 8, bottom: 8, left: 8 },
  };
  return shape;
}

export function addCallout(slide, name, text, position, options = {}) {
  const shape = slide.shapes.add({
    geometry: "roundRect",
    name,
    position,
    fill: options.fill ?? C.lightBlue,
    line: { style: "solid", fill: options.line ?? C.blue, width: options.lineWidth ?? 1.5 },
    borderRadius: options.radius ?? 18,
    shadow: options.shadow ?? "shadow-sm",
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: options.fontSize ?? 24,
    bold: options.bold ?? true,
    color: options.color ?? C.navy,
    alignment: options.alignment ?? "left",
    verticalAlignment: options.verticalAlignment ?? "middle",
    autoFit: "shrinkText",
    wrap: "square",
    insets: options.insets ?? { top: 12, right: 16, bottom: 12, left: 16 },
  };
  return shape;
}

export function addMetric(slide, name, value, label, position, options = {}) {
  const box = slide.shapes.add({
    geometry: "roundRect",
    name,
    position,
    fill: options.fill ?? C.white,
    line: { style: "solid", fill: options.line ?? C.line, width: 1.2 },
    borderRadius: 18,
    shadow: "shadow-sm",
  });
  addText(slide, `${name}-value`, value,
    { left: position.left + 18, top: position.top + 12, width: position.width - 36, height: 50 },
    { fontSize: options.valueSize ?? 38, bold: true, color: options.valueColor ?? C.blue, alignment: "center" });
  addText(slide, `${name}-label`, label,
    { left: position.left + 18, top: position.top + 64, width: position.width - 36, height: position.height - 74 },
    { fontSize: options.labelSize ?? 19, color: C.muted, alignment: "center", verticalAlignment: "middle" });
  return box;
}

export function addTable(slide, name, values, position, columnWidths, options = {}) {
  const table = slide.tables.add({
    rows: values.length,
    columns: values[0].length,
    left: position.left,
    top: position.top,
    width: position.width,
    height: position.height,
    values,
    columnWidths,
  });
  table.name = name;
  table.borders.assign({ style: "solid", fill: C.line, width: 1 });
  table.cells.block({ row: 0, column: 0, rowCount: values.length, columnCount: values[0].length }).assign({
    textStyle: { typeface: FONT, fontSize: options.fontSize ?? 18, color: C.text },
    margins: { top: 6, right: 8, bottom: 6, left: 8 },
    anchor: "middle",
  });
  for (let c = 0; c < values[0].length; c += 1) {
    const cell = table.getCell(0, c);
    cell.fill = options.headerFill ?? C.navy2;
    cell.text.style = { typeface: FONT, fontSize: options.headerSize ?? 19, bold: true, color: C.white, alignment: options.headerAlign ?? "center" };
  }
  for (let r = 1; r < values.length; r += 1) {
    for (let c = 0; c < values[0].length; c += 1) {
      const cell = table.getCell(r, c);
      cell.fill = r % 2 === 0 ? C.slate : C.white;
    }
  }
  return table;
}

export function makeNode(slide, name, position, geometry = "roundRect") {
  return slide.shapes.add({
    geometry,
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
    borderRadius: geometry === "roundRect" ? 16 : undefined,
  });
}

export function connect(slide, from, to, options = {}) {
  return slide.shapes.connect(from, to, {
    kind: options.kind ?? "elbow",
    fromSide: options.fromSide,
    toSide: options.toSide,
    line: { style: options.style ?? "solid", fill: options.color ?? C.blue, width: options.width ?? 3 },
    head: options.tail ? { type: "triangle", width: "sm", length: "sm" } : undefined,
    tail: options.noHead ? undefined : { type: "triangle", width: "sm", length: "sm" },
  });
}

export function styleNode(shape, text, options = {}) {
  shape.fill = options.fill ?? C.white;
  shape.line = { style: "solid", fill: options.line ?? C.blue, width: options.lineWidth ?? 1.8 };
  shape.shadow = options.shadow ?? "shadow-sm";
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: options.fontSize ?? 21,
    bold: options.bold ?? true,
    color: options.color ?? C.navy,
    alignment: "center",
    verticalAlignment: "middle",
    autoFit: "shrinkText",
    wrap: "square",
    insets: { top: 8, right: 8, bottom: 8, left: 8 },
  };
  return shape;
}

export function setSources(slide, sources, presenterNotes = []) {
  const sourceBlock = ["[Sources]", ...sources.map((source) => `- ${source}`), "[/Sources]"];
  if (presenterNotes.length) {
    sourceBlock.push("", ...presenterNotes);
  }
  slide.speakerNotes.textFrame.setText(sourceBlock.join("\n"));
  slide.speakerNotes.setVisible(true);
}

export async function exportDeck(deck, outputPath, previewDir) {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.mkdir(previewDir, { recursive: true });
  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const png = await deck.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(path.join(previewDir, `${stem}.png`), new Uint8Array(await png.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(previewDir, `${stem}.layout.json`), await layout.text());
  }
  const montage = await deck.export({ format: "webp", montage: { format: "webp", columns: 4, slideWidth: 320, padding: 16, gap: 12, background: "#D7DEE7" }, scale: 1 });
  await fs.writeFile(path.join(previewDir, "montage.webp"), new Uint8Array(await montage.arrayBuffer()));
  const inspect = await deck.inspect({ kind: "slide,textbox,shape,table,chart,notes", maxChars: 120000 });
  await fs.writeFile(path.join(previewDir, "inspect.ndjson"), inspect.ndjson);
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(outputPath);
  console.log(`OK ${outputPath} (${deck.slides.items.length} slides)`);
}
