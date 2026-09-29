"""Render every page at 150 dpi.

page-<n>.png        : faithful render, transparent background (the PDF pages carry no
                      page-background fill), RGBA.
tools/preview-<n>.png: same render composited on a checkerboard so white artwork is
                      visible when viewed (inspection only).
"""
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source.pdf"
DPI = 150


def checker_png(pix_rgba, path, cell=12, a=(0x9A, 0x9A, 0x9A), b=(0x6E, 0x6E, 0x6E)):
    w, h = pix_rgba.width, pix_rgba.height
    base = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    buf = bytearray(w * h * 3)
    for y in range(h):
        for x in range(w):
            c = a if ((x // cell) + (y // cell)) % 2 == 0 else b
            o = (y * w + x) * 3
            buf[o:o + 3] = bytes(c)
    base = fitz.Pixmap(fitz.csRGB, w, h, bytes(buf), False)
    # alpha-composite pix_rgba over base
    src = pix_rgba.samples
    out = bytearray(buf)
    for i in range(w * h):
        al = src[i * 4 + 3]
        if al == 0:
            continue
        for ch in range(3):
            fg = src[i * 4 + ch]  # premultiplied? PyMuPDF samples are NOT premultiplied
            bg = out[i * 3 + ch]
            out[i * 3 + ch] = (fg * al + bg * (255 - al) + 127) // 255
    res = fitz.Pixmap(fitz.csRGB, w, h, bytes(out), False)
    res.save(str(path))


def main():
    doc = fitz.open(SRC)
    (ROOT / "tools").mkdir(exist_ok=True)
    for pno in range(doc.page_count):
        page = doc[pno]
        pix = page.get_pixmap(dpi=DPI, alpha=True)
        p = ROOT / f"page-{pno + 1}.png"
        pix.save(str(p))
        print(p.name, pix.width, pix.height, "n=", pix.n, "alpha=", pix.alpha)
        small = page.get_pixmap(dpi=72, alpha=True)
        checker_png(small, ROOT / "tools" / f"preview-{pno + 1}.png")


if __name__ == "__main__":
    main()
