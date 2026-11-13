"""Detailed dump: every drawing (rect, fill, even_odd, item count), text spans, image smask."""
import json
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source.pdf"
OUT = ROOT / "tools" / "detail.json"


def hx(c):
    if c is None:
        return None
    if len(c) == 1:
        v = round(c[0] * 255)
        return "#%02X%02X%02X" % (v, v, v)
    return "#%02X%02X%02X" % tuple(round(x * 255) for x in c[:3])


def main():
    doc = fitz.open(SRC)
    out = {"pages": []}
    for pno in range(doc.page_count):
        page = doc[pno]
        pg = {"no": pno + 1, "drawings": [], "spans": [], "images": []}
        for i, d in enumerate(page.get_drawings(extended=True)):
            kind = d.get("type")
            entry = {
                "i": i,
                "type": kind,
                "level": d.get("level"),
                "rect": [round(v, 3) for v in d["rect"]] if d.get("rect") else None,
            }
            if kind in ("f", "fs", "s"):
                entry.update({
                    "fill": hx(d.get("fill")),
                    "fill_opacity": d.get("fill_opacity"),
                    "stroke": hx(d.get("color")),
                    "even_odd": d.get("even_odd"),
                    "n_items": len(d.get("items", [])),
                    "layer": d.get("layer"),
                    "seqno": d.get("seqno"),
                })
            elif kind == "clip":
                entry.update({"scissor": [round(v, 3) for v in d.get("scissor", [])],
                              "even_odd": d.get("even_odd")})
            elif kind == "group":
                entry.update({"isolated": d.get("isolated"), "knockout": d.get("knockout"),
                              "blendmode": d.get("blendmode"), "opacity": d.get("opacity")})
            pg["drawings"].append(entry)
        td = page.get_text("rawdict")
        for b in td["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                for s in line["spans"]:
                    txt = "".join(ch["c"] for ch in s["chars"])
                    pg["spans"].append({
                        "text": txt,
                        "font": s["font"],
                        "size": round(s["size"], 3),
                        "color": "#%06X" % s["color"],
                        "alpha": s.get("alpha"),
                        "bbox": [round(v, 3) for v in s["bbox"]],
                        "flags": s["flags"],
                    })
        for im in page.get_images(full=True):
            xref = im[0]
            info = {"xref": xref, "smask": im[1], "w": im[2], "h": im[3], "cs": im[5],
                    "alt_cs": im[6], "name": im[7]}
            pix = fitz.Pixmap(doc, xref)
            info["pix_n"] = pix.n
            info["pix_alpha"] = pix.alpha
            info["pix_cs"] = str(pix.colorspace)
            # distinct colours in the base image (after palette expansion)
            if pix.colorspace and pix.colorspace.n != 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            samples = pix.samples
            step = pix.n
            colours = {}
            for k in range(0, len(samples), step * 7):
                key = bytes(samples[k:k + 3]).hex().upper()
                colours[key] = colours.get(key, 0) + 1
            top = sorted(colours.items(), key=lambda kv: -kv[1])[:12]
            info["top_colours_sampled"] = top
            info["n_distinct_sampled"] = len(colours)
            # xref object source (dictionary only)
            info["obj"] = doc.xref_object(xref, compressed=True)[:600]
            if im[1]:
                info["smask_obj"] = doc.xref_object(im[1], compressed=True)[:600]
            pg["images"].append(info)
        out["pages"].append(pg)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
