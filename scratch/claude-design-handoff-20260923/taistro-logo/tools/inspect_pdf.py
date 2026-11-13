"""Inspect source.pdf: metadata, pages, images, fonts, text, drawings summary."""
import json
import sys
from collections import Counter
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source.pdf"
OUT = ROOT / "tools" / "inspect.json"


def color_hex(c):
    if c is None:
        return None
    if len(c) == 1:
        v = round(c[0] * 255)
        return "#%02X%02X%02X" % (v, v, v)
    if len(c) == 3:
        return "#%02X%02X%02X" % tuple(round(x * 255) for x in c)
    return str(c)


def main():
    doc = fitz.open(SRC)
    report = {
        "pymupdf": fitz.VersionBind,
        "page_count": doc.page_count,
        "metadata": doc.metadata,
        "is_pdf": doc.is_pdf,
        "pages": [],
    }
    for pno in range(doc.page_count):
        page = doc[pno]
        drawings = page.get_drawings()
        fills = Counter()
        strokes = Counter()
        for d in drawings:
            if d.get("fill") is not None:
                fills[color_hex(d["fill"])] += 1
            if d.get("color") is not None and d.get("type") in ("s", "fs"):
                strokes[color_hex(d["color"])] += 1
        imgs = page.get_images(full=True)
        img_info = []
        for im in imgs:
            xref = im[0]
            rects = [list(r) for r in page.get_image_rects(xref)]
            img_info.append({
                "xref": xref, "w": im[2], "h": im[3], "bpc": im[4],
                "cs": im[5], "name": im[7], "filter": im[8], "rects": rects,
            })
        text = page.get_text("text")
        report["pages"].append({
            "no": pno + 1,
            "mediabox": list(page.mediabox),
            "cropbox": list(page.cropbox),
            "rotation": page.rotation,
            "n_drawings": len(drawings),
            "fills": dict(fills.most_common()),
            "strokes": dict(strokes.most_common()),
            "images": img_info,
            "fonts": [list(f) for f in page.get_fonts(full=True)],
            "text": text,
            "drawings_bbox": list(fitz.Rect(*drawings[0]["rect"]).__or__(
                fitz.Rect()) if drawings else []),
        })
        # overall bbox of all drawings
        if drawings:
            bb = fitz.Rect(drawings[0]["rect"])
            for d in drawings[1:]:
                bb |= d["rect"]
            report["pages"][-1]["drawings_bbox"] = [round(v, 3) for v in bb]
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ok", doc.page_count)


if __name__ == "__main__":
    sys.exit(main())
