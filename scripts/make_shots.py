#!/usr/bin/env python3
"""make_shots.py — compose the README screenshots from real library assets.

Not a browser screenshot: these are drawn from the same palette, the same type
and the actual cover files and PDF pages the site serves, so what the README
shows is what the site is. Regenerate with:

    python3 scripts/make_shots.py --vault ../corpus-extendum-vault-01
"""
import argparse, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PAPER = (250, 247, 242); INK = (22, 19, 15); INK2 = (58, 51, 43)
MUTED = (110, 100, 89); LINE = (226, 218, 205); LINE2 = (211, 200, 183)
ACCENT = (140, 58, 43); TEAL = (31, 78, 70); CARD = (255, 253, 249)
DARK = (13, 11, 9); DARK2 = (16, 13, 11); DARK3 = (26, 22, 19)

SERIF = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
SERIF_B = "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"
SERIF_I = "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"


def f(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def cover(path, w, h):
    try:
        im = Image.open(path).convert("RGB")
        r = max(w / im.width, h / im.height)
        im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
        left = (im.width - w) // 2
        im = im.crop((left, 0, left + w, h))
        return im
    except Exception:
        return Image.new("RGB", (w, h), (42, 35, 28))


def shelf(catalog, vault, out):
    W, H = 1440, 980
    img = Image.new("RGB", (W, H), PAPER); d = ImageDraw.Draw(img)

    # header
    d.rectangle([0, 0, W, 68], fill=PAPER)
    d.line([0, 68, W, 68], fill=LINE, width=1)
    d.rounded_rectangle([40, 18, 74, 52], 8, fill=ACCENT)
    d.text((48, 25), "CE", font=f(SERIF_B, 17), fill=(251, 243, 233))
    d.text((86, 18), "Corpus Extendum", font=f(SERIF_B, 19), fill=INK)
    d.text((86, 40), "PUBLIC DOMAIN LIBRARY", font=f(SANS_B, 9), fill=MUTED)
    for i, item in enumerate(["Browse", "How it works", "Vaults", "Support"]):
        d.text((330 + i * 120, 28), item, font=f(SANS, 13), fill=INK2)
    d.rounded_rectangle([W - 300, 16, W - 108, 52], 9, fill=CARD, outline=LINE2)
    d.text((W - 284, 27), "Title, author, subject", font=f(SANS, 12), fill=MUTED)
    d.rounded_rectangle([W - 74, 16, W - 40, 52], 9, fill=CARD, outline=LINE2)

    # hero
    d.text((40, 106), "PUBLIC DOMAIN · FREE TO READ, FREE TO KEEP", font=f(SANS_B, 10), fill=MUTED)
    d.text((40, 130), "The public domain,", font=f(SERIF, 52), fill=INK)
    d.text((40, 186), "properly shelved.", font=f(SERIF_I, 52), fill=ACCENT)
    lede = ("Every book here is free to read, free to keep, and free of a paywall — because its "
            "copyright has expired. Open any title as a PDF, EPUB or plain text in the page.")
    y = 258
    for line in wrap(d, lede, f(SANS, 14), 620):
        d.text((40, y), line, font=f(SANS, 14), fill=INK2); y += 22

    # stats
    sx, sy = 760, 130
    labels = [(str(len(catalog)), "BOOKS"), ("1", "VAULT REPO"), ("10", "CATEGORIES"), ("12", "FORMATS")]
    for i, (n, l) in enumerate(labels):
        cx, cy = sx + (i % 2) * 300, sy + (i // 2) * 96
        d.rounded_rectangle([cx, cy, cx + 288, cy + 86], 10, fill=PAPER, outline=LINE)
        d.text((cx + 18, cy + 14), n, font=f(SERIF, 28), fill=INK)
        d.text((cx + 18, cy + 56), l, font=f(SANS_B, 9), fill=MUTED)

    # shard bar
    d.rounded_rectangle([40, 360, W - 40, 412], 11, fill=(243, 238, 229), outline=LINE)
    d.text((60, 380), "corpus-extendum-vault-01", font=f(SANS_B, 12), fill=INK)
    d.rounded_rectangle([300, 384, 980, 391], 4, fill=LINE2)
    d.rounded_rectangle([300, 384, 320, 391], 4, fill=TEAL)
    d.text((1000, 380), f"{len(catalog)} / 600 books · 53 MB / 2500 MB · open", font=f(SANS, 12), fill=MUTED)

    # chips
    cats = [("All", len(catalog))] + [(c, sum(1 for b in catalog if b["category"] == c))
                                      for c in dict.fromkeys(b["category"] for b in catalog)][:7]
    cx = 40
    for i, (c, n) in enumerate(cats):
        w = int(d.textlength(c, font=f(SANS, 13))) + 54
        on = i == 0
        d.rounded_rectangle([cx, 436, cx + w, 470], 17, fill=INK if on else CARD, outline=INK if on else LINE2)
        d.text((cx + 15, 446), c, font=f(SANS, 13), fill=PAPER if on else INK2)
        d.text((cx + w - 26, 447), str(n), font=f(SANS, 10), fill=PAPER if on else MUTED)
        cx += w + 9

    # shelf heading
    d.text((40, 496), "The shelf", font=f(SERIF, 22), fill=INK)
    d.text((150, 502), f"{len(catalog)} books", font=f(SANS, 13), fill=MUTED)

    # cards
    cw, ch = 190, 285
    for i, b in enumerate(catalog[:6]):
        x = 40 + i * (cw + 24)
        y = 540
        d.rectangle([x + 4, y + 4, x + cw + 4, y + ch + 4], fill=(238, 232, 222))
        cv = cover(vault / "books" / b["slug"] / "cover.jpg", cw, ch)
        img.paste(cv, (x, y))
        d.rectangle([x, y, x + 8, y + ch], fill=(120, 110, 98))
        d.rounded_rectangle([x + cw - 88, y + 10, x + cw - 10, y + 32], 5, fill=(30, 26, 22))
        d.text((x + cw - 80, y + 16), "PUBLIC DOMAIN", font=f(SANS_B, 7), fill=(242, 233, 219))
        ty = y + ch + 14
        for line in wrap(d, b["title"], f(SERIF, 14), cw)[:3]:
            d.text((x, ty), line, font=f(SERIF, 14), fill=INK); ty += 17
        d.text((x, ty + 2), b["author"]["name"][:24], font=f(SANS, 11), fill=MUTED)
        d.text((x, ty + 22), b["category"].upper(), font=f(SANS_B, 8), fill=TEAL)

    img.save(out, "PNG", optimize=True)
    return out


def reader_shot(catalog, vault, out, tmp):
    import pymupdf
    b = next(x for x in catalog if x["slug"] == "pride-and-prejudice")
    doc = pymupdf.open(vault / "books" / b["slug"] / f"{b['slug']}.pdf")
    page_png = tmp / "reader_page.png"
    doc[7].get_pixmap(dpi=150).save(page_png)

    W, H = 1440, 880
    img = Image.new("RGB", (W, H), DARK); d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 56], fill=DARK2)
    d.line([0, 56, W, 56], fill=DARK3)
    d.text((20, 12), b["title"], font=f(SERIF, 15), fill=(237, 230, 218))
    d.text((20, 32), b["author"]["name"], font=f(SANS, 11), fill=(154, 144, 131))
    d.rounded_rectangle([520, 14, 596, 42], 6, fill=DARK3, outline=(51, 44, 38))
    d.text((536, 21), "Page 8", font=f(SANS, 11), fill=(201, 192, 178))
    x = 610
    for i, (lab, on) in enumerate([("PDF", True), ("EPUB", False), ("TXT", False), ("JSON", False)]):
        w = 46 if lab != "JSON" else 52
        d.rounded_rectangle([x, 14, x + w, 42], 6, fill=(51, 43, 36) if on else DARK3, outline=(51, 44, 38))
        d.text((x + 12, 21), lab, font=f(SANS, 11), fill=(246, 238, 226) if on else (154, 144, 131))
        x += w + 3
    d.rounded_rectangle([W - 200, 14, W - 60, 42], 6, fill=DARK3, outline=(51, 44, 38))
    d.text((W - 188, 21), "Download", font=f(SANS, 11), fill=(201, 192, 178))

    pg = Image.open(page_png)
    ph = 760; pw = int(pg.width * ph / pg.height)
    pg = pg.resize((pw, ph), Image.LANCZOS)
    px = (W - 320 - pw) // 2 + 10
    img.paste(pg, (px, 72))
    d.rectangle([px - 2, 72, px + pw + 2, 72 + ph], outline=(60, 54, 48), width=1)

    sx = W - 320
    d.rectangle([sx, 56, W, H], fill=DARK2)
    d.line([sx, 56, sx, H], fill=DARK3)
    d.text((sx + 22, 82), "ABOUT THIS EDITION", font=f(SANS_B, 9), fill=(126, 117, 104))
    d.text((sx + 22, 104), b["title"], font=f(SERIF, 19), fill=(244, 236, 223))
    d.text((sx + 22, 132), b["author"]["name"], font=f(SANS, 12), fill=(154, 144, 131))
    rows = [("First published", str(b["year"])), ("Category", b["category"]),
            ("Language", "English"), ("Source", b["source"]["name"]),
            ("Rights", "Public domain"), ("Stored in", "vault-01")]
    y = 168
    for k, v in rows:
        d.text((sx + 22, y), k, font=f(SANS, 11), fill=(126, 117, 104))
        vw = d.textlength(v, font=f(SANS, 11))
        d.text((W - 22 - vw, y), v, font=f(SANS, 11), fill=(143, 192, 178) if k == "Rights" else (214, 204, 189))
        d.line([sx + 22, y + 22, W - 22, y + 22], fill=(36, 31, 27))
        y += 30
    for i, f_ in enumerate(["Download PDF", "Download EPUB", "Plain text", "Record (JSON)"]):
        yy = y + 14 + i * 38
        d.rounded_rectangle([sx + 22, yy, W - 22, yy + 30], 7, fill=(25, 21, 18), outline=(46, 40, 35))
        d.text((sx + 34, yy + 8), f_, font=f(SANS, 11), fill=(214, 204, 189))

    img.save(out, "PNG", optimize=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--library", default=".")
    args = ap.parse_args()
    vault = Path(args.vault).resolve()
    lib = Path(args.library).resolve()
    catalog = json.loads((lib / "data" / "catalog.json").read_text())
    assets = lib / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    tmp = Path("/scratch/work/_tmp"); tmp.mkdir(exist_ok=True)
    print(shelf(catalog, vault, assets / "shelf.png"))
    print(reader_shot(catalog, vault, assets / "reader.png", tmp))


if __name__ == "__main__":
    main()
