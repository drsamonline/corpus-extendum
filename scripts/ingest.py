#!/usr/bin/env python3
"""
ingest.py — fetch a public-domain book, gate it, typeset it, shelve it.

    python3 ingest.py --vault ../corpus-extendum-vault-01 --only 1342
    python3 ingest.py --vault ../corpus-extendum-vault-01 --all

Sources, in order of preference:
  1. Standard Ebooks  — CC0 editions, GitHub-hosted source trees (best typography)
  2. GITenberg        — Project Gutenberg texts mirrored on GitHub
  3. archive.org      — scans, for anything the first two do not hold

Why not gutenberg.org directly: it refuses datacenter IPs (HTTP 403 from every
cloud runner we have tried). The GITenberg mirror carries the same texts and
GitHub serves it happily, so the pipeline does not depend on being run from a
residential connection. `--source gutenberg` still exists for local runs.

Zero third-party dependencies beyond WeasyPrint and Pillow.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "corpus-extendum/1.0 (+https://github.com/drsamonline/corpus-extendum)"}
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

# --------------------------------------------------------------------------- #
# The seed shelf
# --------------------------------------------------------------------------- #
BOOKS = [
    dict(id=1342, slug="pride-and-prejudice", title="Pride and Prejudice",
         author="Jane Austen", author_file="Austen, Jane", year=1813, death=1817,
         category="Fiction", se="jane-austen_pride-and-prejudice",
         blurb="Elizabeth Bennet and Mr Darcy, and the most quoted opening sentence in English fiction. A comedy of manners that doubles as an argument about how people judge each other.",
         subjects=["Courtship -- Fiction", "England -- Social life and customs"]),
    dict(id=84, slug="frankenstein", title="Frankenstein; or, The Modern Prometheus",
         author="Mary Wollstonecraft Shelley", author_file="Shelley, Mary Wollstonecraft", year=1818, death=1851,
         category="Gothic & Horror", se="mary-shelley_frankenstein",
         blurb="Written by a teenager on a wet summer holiday, and still the sharpest book about making something you cannot look after.",
         subjects=["Frankenstein's monster (Fictitious character)", "Horror tales"]),
    dict(id=1661, slug="sherlock-holmes", title="The Adventures of Sherlock Holmes",
         author="Arthur Conan Doyle", author_file="Doyle, Arthur Conan", year=1892, death=1930,
         category="Mystery & Detective", se="arthur-conan-doyle_the-adventures-of-sherlock-holmes",
         blurb="Twelve cases, from A Scandal in Bohemia to The Copper Beeches. The template for every detective story written since.",
         subjects=["Holmes, Sherlock (Fictitious character)", "Detective and mystery stories"]),
    dict(id=35, slug="the-time-machine", title="The Time Machine",
         author="H. G. Wells", author_file="Wells, H. G.", year=1895, death=1946,
         category="Science Fiction", se="h-g-wells_the-time-machine",
         blurb="The book that gave science fiction its time-travel grammar, and its darkest question: what does progress actually lead to?",
         subjects=["Time travel -- Fiction", "Science fiction"]),
    dict(id=2680, slug="meditations", title="Meditations",
         author="Marcus Aurelius", author_file="Marcus Aurelius, Emperor of Rome", year=180, death=180,
         category="Philosophy", se="marcus-aurelius_meditations_george-long",
         translator="George Long", translator_death=1879,
         blurb="A Roman emperor's private notes to himself, never meant for publication. The most practical ethics ever written down.",
         subjects=["Stoics", "Ethics -- Early works to 1800"]),
    dict(id=7164, slug="gitanjali", title="Gitanjali",
         author="Rabindranath Tagore", author_file="Tagore, Rabindranath", year=1912, death=1941,
         category="Poetry", se="rabindranath-tagore_gitanjali",
         blurb="The English Gitanjali, translated by Tagore himself with an introduction by W. B. Yeats, won the 1913 Nobel Prize in Literature — the first for Asia.",
         subjects=["Indic poetry -- Translations into English", "Prose poems, Bengali"]),
    dict(id=2388, slug="the-song-celestial", title="The Song Celestial; or, Bhagavad-Gita",
         author="trans. Sir Edwin Arnold", author_file="Arnold, Edwin, Sir", year=1885, death=1904,
         category="Sacred Texts",
         gitenberg="GITenberg/The-Song-Celestial--Or-Bhagavad-G-t---from-the-Mah-bh-rata---13-Being-a-discourse-between-Arju__2388",
         blurb="Arnold's verse translation of the Gita, the version Gandhi called the best he had read in English. Krishna and Arjuna, on duty, action and letting go of the result.",
         subjects=["Hinduism -- Sacred books", "Sanskrit poetry -- Translations into English"]),
    dict(id=408, slug="souls-of-black-folk", title="The Souls of Black Folk",
         author="W. E. B. Du Bois", author_file="Du Bois, W. E. B.", year=1903, death=1963,
         category="Essays", se="w-e-b-du-bois_the-souls-of-black-folk",
         blurb="Fourteen essays that gave American thought the idea of double consciousness. Required reading on race, education and the cost of the colour line.",
         subjects=["African Americans", "United States -- Race relations"]),
    dict(id=2814, slug="dubliners", title="Dubliners",
         author="James Joyce", author_file="Joyce, James", year=1914, death=1941,
         category="Short Stories", se="james-joyce_dubliners",
         blurb="Fifteen stories that move from childhood to public life across a single city. The Dead alone is worth the whole shelf.",
         subjects=["Dublin (Ireland) -- Fiction", "Short stories"]),
    dict(id=11, slug="alice-in-wonderland", title="Alice's Adventures in Wonderland",
         author="Lewis Carroll", author_file="Carroll, Lewis", year=1865, death=1898,
         category="Children's & Fable",
         se="lewis-carroll_alices-adventures-in-wonderland_john-tenniel",
         blurb="A book written for one child and owned by every generation since. Logic, nonsense, and a Queen who wants the sentence first.",
         subjects=["Fantasy fiction", "Alice (Fictitious character from Carroll)"]),
]

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def log(msg):
    print(msg, flush=True)


def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    if TOKEN and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def api(url):
    return json.loads(fetch(url))


def tarball(repo, dest: Path):
    """Download a GitHub repo tarball and extract it. Returns the root dir.

    codeload.github.com, deliberately: it serves source archives without the
    API's 60-requests-an-hour unauthenticated limit, so the pipeline needs no
    token at all and cannot be throttled mid-batch.
    """
    dest.mkdir(parents=True, exist_ok=True)
    last = None
    for branch in ("master", "main"):
        try:
            data = fetch(f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{branch}", timeout=180)
        except Exception as e:
            last = e
            continue
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            tf.extractall(dest, filter="data")
        roots = [p for p in dest.iterdir() if p.is_dir()]
        if roots:
            return roots[0]
    raise RuntimeError(f"tarball failed for {repo}: {last}")


def strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|blockquote|section)>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", "", html)
    text = (text.replace("&mdash;", "—").replace("&ndash;", "–").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
                .replace("&rsquo;", "’").replace("&lsquo;", "‘").replace("&ldquo;", "“")
                .replace("&rdquo;", "”").replace("&#8217;", "’").replace("&quot;", '"'))
    text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def normalise_text(text: str) -> str:
    """The dedupe basis: what survives is the words, in order."""
    t = text.lower()
    t = re.sub(r"\*\*\*\s*(start|end) of (the )?project gutenberg.*?\*\*\*", " ", t, flags=re.S)
    t = re.sub(r"produced by .{0,200}", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def text_sha(text: str) -> str:
    return hashlib.sha256(normalise_text(text).encode()).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# cover
# --------------------------------------------------------------------------- #
def make_cover(path: Path, title: str, author: str, category: str):
    """A typographic cover, drawn to match the library's own palette."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 800, 1200
    paper, ink, accent = (250, 247, 242), (22, 19, 15), (140, 58, 43)
    img = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 14, H], fill=(200, 190, 175))
    d.rectangle([0, 0, W, 10], fill=accent)

    def font(size, bold=False):
        for cand in (["/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"] if bold
                     else ["/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"]):
            if os.path.exists(cand):
                return ImageFont.truetype(cand, size)
        return ImageFont.load_default()

    def wrap(text, f, maxw):
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if d.textlength(trial, font=f) <= maxw:
                cur = trial
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        return lines

    pad = 90
    cat_f = font(26)
    d.text((pad, 120), category.upper(), font=cat_f, fill=accent)
    d.line([pad, 168, pad + d.textlength(category.upper(), font=cat_f), 168], fill=accent, width=2)

    size = 92
    while size > 44:
        f = font(size, bold=True)
        lines = wrap(title, f, W - 2 * pad)
        if len(lines) * (size + 14) < 520:
            break
        size -= 6
    y = 260
    for line in lines:
        d.text((pad, y), line, font=f, fill=ink)
        y += size + 14

    d.line([pad, y + 40, pad + 120, y + 40], fill=(200, 190, 175), width=2)
    af = font(38)
    for line in wrap(author, af, W - 2 * pad)[:3]:
        d.text((pad, y + 76), line, font=af, fill=(58, 51, 43))
        y += 48

    sf = font(22)
    d.text((pad, H - 130), "CORPUS EXTENDUM", font=sf, fill=(150, 140, 125))
    d.text((pad, H - 96), "PUBLIC DOMAIN", font=sf, fill=(150, 140, 125))
    img.save(path, "JPEG", quality=88, optimize=True)


def use_or_make_cover(src_cover: Path | None, dest: Path, book: dict):
    from PIL import Image
    if src_cover and src_cover.exists():
        try:
            im = Image.open(src_cover).convert("RGB")
            w, h = im.size
            target_w = 800
            im = im.resize((target_w, int(h * target_w / w)), Image.LANCZOS)
            im.save(dest, "JPEG", quality=88, optimize=True)
            return "source"
        except Exception as e:
            log(f"    cover from source failed ({e}); drawing one")
    make_cover(dest, book["title"], book["author"], book["category"])
    return "generated"


# --------------------------------------------------------------------------- #
# PDF + EPUB from a Standard Ebooks source tree
# --------------------------------------------------------------------------- #
PDF_CSS = """
@page { size: A5; margin: 17mm 15mm 18mm 15mm;
        @bottom-center { content: counter(page); font-size: 8pt; color: #8a8175; } }
@page :first { @bottom-center { content: none; } }
.ce-title { text-align: center; page-break-after: always; padding-top: 55mm; }
.ce-title h1 { text-align: center; font-size: 26pt; line-height: 1.18; margin: 0 0 10pt; }
.ce-title .ce-author { text-align: center; text-indent: 0; font-size: 14pt; color: #3a332b; margin: 0; }
.ce-title .ce-rule { border-top: 1px solid #c8bfae; width: 60mm; margin: 16pt auto; }
.ce-title .ce-src { text-align: center; text-indent: 0; font-size: 8.5pt; letter-spacing: .08em;
                    text-transform: uppercase; color: #8a8175; margin-top: 70mm; }
html { font-size: 10.5pt; }
body { font-family: "Liberation Serif", "DejaVu Serif", Georgia, serif;
       color: #1b1712; line-height: 1.5; text-align: justify; hyphens: auto; }
h1, h2, h3, h4, h5, h6 { text-align: left; line-height: 1.22; page-break-after: avoid;
       font-weight: 700; color: #16130f; }
h1 { font-size: 19pt; margin: 0 0 6pt; }
h2 { font-size: 15pt; margin: 20pt 0 9pt; }
h3 { font-size: 12.5pt; margin: 15pt 0 7pt; }
h4 { font-size: 11pt; margin: 13pt 0 6pt; }
p { margin: 0 0 5.5pt; text-indent: 1.3em; }
p:first-of-type, h1 + p, h2 + p, h3 + p, h4 + p, blockquote p,
p.noindent, p.first, .verse p, .poem p, .stanza p { text-indent: 0; }
blockquote { margin: 8pt 10mm; font-style: italic; }
blockquote p { text-indent: 0; }
hr { border: 0; border-top: 1px solid #d8d0c2; margin: 12pt 0; width: 40%; }
img { max-width: 100%; height: auto; }
svg { max-width: 100%; }
section, article, .chapter { page-break-before: always; }
section:first-of-type, body > section:nth-of-type(1) { page-break-before: avoid; }
.verse, .poem, .stanza, .lines { text-align: left; text-indent: 0; }
.verse p, .poem p, .stanza p { margin: 0 0 1.5pt; }
i, em { font-style: italic; }
b, strong { font-weight: 700; }
.titlepage, .halftitlepage { text-align: center; page-break-after: always; }
.titlepage h1, .titlepage h2 { text-align: center; }
"""


FRONTMATTER = {"halftitlepage", "titlepage", "imprint", "colophon", "uncopyright",
               "copyright-page", "copyright", "toc", "nav"}


def se_spine(root: Path):
    """Read content.opf and return the spine documents in reading order.

    Standard Ebooks' own front matter (half-title, title, imprint, colophon,
    uncopyright) is dropped: it duplicates the title, embeds their logo, and is
    not part of the work. We print our own title page instead, and credit the
    source there — which is also what keeps the attribution honest.
    """
    opf_path = root / "src" / "epub" / "content.opf"
    if not opf_path.exists():
        cands = list(root.glob("**/content.opf"))
        if not cands:
            raise RuntimeError("no content.opf")
        opf_path = cands[0]
    opf = opf_path.read_text(encoding="utf-8", errors="ignore")
    manifest = dict(re.findall(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', opf))
    for m in re.finditer(r"<item\b[^>]*>", opf):
        tag = m.group(0)
        i = re.search(r'\bid="([^"]+)"', tag)
        h = re.search(r'\bhref="([^"]+)"', tag)
        if i and h:
            manifest[i.group(1)] = h.group(1)
    spine_block = re.search(r"(?s)<spine[^>]*>(.*?)</spine>", opf)
    order = re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', spine_block.group(1) if spine_block else "")
    docs = []
    for idref in order:
        href = manifest.get(idref)
        if not href:
            continue
        p = opf_path.parent / href
        if p.exists() and p.stem not in FRONTMATTER:
            docs.append(p)
    if not docs:
        docs = [p for p in sorted(opf_path.parent.glob("text/*.xhtml")) if p.stem not in FRONTMATTER]
    return docs


def shrink_tree(src: Path, dest: Path, max_px=900, quality=82) -> Path:
    """Mirror an EPUB source tree with raster images downscaled for the screen.

    The plates in a Victorian illustrated edition arrive at print resolution —
    Alice came out at 42 MB for one book. At 900 px and q82 the same
    illustrations are indistinguishable on a screen and the book is 3 MB, which
    also keeps every file comfortably under jsDelivr's 20 MB ceiling.
    """
    import base64
    from PIL import Image
    dest.mkdir(parents=True, exist_ok=True)
    shrunk = 0
    renamed = {}
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        target = dest / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix.lower() == ".svg":
            # Standard Ebooks' illustrated editions wrap a huge raster inside an
            # SVG (3 MB per plate). Pull the raster out, shrink it, and rewrite
            # the references below — otherwise one book is 40 MB of PDF.
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"data:image/(?:png|jpeg|jpg);base64,([A-Za-z0-9+/=\s]+)", raw)
                if m and len(m.group(1)) > 150_000:
                    blob = base64.b64decode(re.sub(r"\s+", "", m.group(1)))
                    im = Image.open(io.BytesIO(blob)).convert("RGB")
                    im.thumbnail((max_px, max_px), Image.LANCZOS)
                    jpg = target.with_suffix(".jpg")
                    im.save(jpg, "JPEG", quality=quality, optimize=True)
                    renamed[rel.as_posix()] = jpg.relative_to(dest).as_posix()
                    shrunk += 1
                    continue
            except Exception:
                pass
            # No embedded raster: the plate is real vector art (Standard Ebooks'
            # Alice is 42 SVGs of path data, ~760 KB each). Rasterise it once at
            # screen size instead of asking the PDF engine to draw it.
            try:
                im = svg_to_image(p, max_px)
                if im is not None:
                    jpg = target.with_suffix(".jpg")
                    im.save(jpg, "JPEG", quality=quality, optimize=True)
                    renamed[rel.as_posix()] = jpg.relative_to(dest).as_posix()
                    shrunk += 1
                    continue
            except Exception:
                pass
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}:
            try:
                im = Image.open(p)
                if im.width > max_px or im.height > max_px:
                    im.thumbnail((max_px, max_px), Image.LANCZOS)
                    shrunk += 1
                if im.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    im = im.convert("RGBA")
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
                im.save(target, "JPEG", quality=quality, optimize=True)
                continue
            except Exception:
                pass
        shutil.copy2(p, target)

    if renamed:
        for f in list(dest.rglob("*.xhtml")) + list(dest.rglob("*.opf")):
            try:
                t = f.read_text(encoding="utf-8")
            except Exception:
                continue
            orig = t
            for old, new in renamed.items():
                oname, nname = Path(old).name, Path(new).name
                t = t.replace(oname, nname)
                t = re.sub(r'(<item\b[^>]*href="%s"[^>]*media-type=")image/svg\+xml'
                           % re.escape(nname), r"\1image/jpeg", t)
            if t != orig:
                f.write_text(t, encoding="utf-8")
    if shrunk:
        log(f"    downscaled {shrunk} images")
    return dest


def svg_to_image(svg_path: Path, max_px=900):
    """Rasterise an SVG through the renderer that already draws it correctly.

    cairosvg turns these fill-heavy traced plates into solid black squares.
    WeasyPrint draws them properly, so: SVG -> one-page PDF -> pixmap -> JPEG.
    Aspect ratio comes from the viewBox, so nothing is squashed.
    """
    import pymupdf
    from PIL import Image as _Image
    from weasyprint import HTML
    head = svg_path.read_text(encoding="utf-8", errors="ignore")[:2000]
    m = re.search(r'viewBox="([\d.\s-]+)"', head)
    w, h = 900.0, 1200.0
    if m:
        parts = [float(x) for x in m.group(1).replace(",", " ").split()]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            w, h = parts[2], parts[3]
    scale = max_px / max(w, h)
    pw, ph = max(1, int(w * scale)), max(1, int(h * scale))
    doc_html = (f"<html><head><style>@page{{size:{pw}px {ph}px;margin:0}}"
                f"body{{margin:0}}img{{width:{pw}px;height:{ph}px;display:block}}</style></head>"
                f"<body><img src='{svg_path.as_uri()}'></body></html>")
    pdf_bytes = HTML(string=doc_html).write_pdf()
    d = pymupdf.open("pdf", pdf_bytes)
    pix = d[0].get_pixmap(dpi=150)
    im = _Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d.close()
    return im


def body_of(xhtml: str) -> str:
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", xhtml)
    inner = m.group(1) if m else xhtml
    inner = re.sub(r"(?is)<nav[^>]*>.*?</nav>", "", inner)
    inner = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", inner)
    return inner.strip()


def build_from_tree(root: Path, out: Path, book: dict, kind: str):
    """kind: 'se' or 'gitenberg'."""
    if kind == "se":
        docs = se_spine(root)
        textdir = docs[0].parent
        src = root / "src"
        if not src.exists():
            src = root
        # one shrunk copy serves both the PDF and the EPUB; the spine must be
        # re-read from THAT copy, because shrink_tree rewrote the image
        # references inside it and the originals no longer resolve.
        shrunk = shrink_tree(src, out / "_tree")
        docs = [shrunk / d.relative_to(src) for d in docs]
        bodies, texts = [], []
        for d in docs:
            raw = d.read_text(encoding="utf-8", errors="ignore")
            bodies.append(body_of(raw))
            texts.append(strip_tags(body_of(raw)))
        title_page = (
            f"<section class='ce-title'><h1>{book['title']}</h1>"
            f"<div class='ce-rule'></div>"
            f"<p class='ce-author'>{book['author']}</p>"
            f"<p class='ce-src'>Public domain · text from {book.get('source_label', 'Standard Ebooks')}</p></section>"
        )
        body_html = title_page + "\n" + "\n".join(bodies)
        full = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{PDF_CSS}</style></head><body>{body_html}</body></html>"
        base = str((shrunk / textdir.relative_to(src)).resolve())
        plain = "\n\n".join(t for t in texts if t.strip())
        # EPUB: the shrunk source tree IS the EPUB layout
        epub_path = out / f"{book['slug']}.epub"
        with zipfile.ZipFile(epub_path, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
            for p in sorted(shrunk.rglob("*")):
                if p.is_file() and p.name != "mimetype":
                    z.write(p, p.relative_to(shrunk).as_posix(), zipfile.ZIP_DEFLATED)
        cover_src = root / "images" / "cover.jpg"
        if not cover_src.exists():
            cover_src = root / "images" / "cover.png"
    else:
        txts = sorted(root.rglob("*.txt"), key=lambda p: (0 if "-0.txt" in p.name else 1, len(p.name)))
        if not txts:
            raise RuntimeError("no .txt in GITenberg repo")
        plain = txts[0].read_text(encoding="utf-8", errors="ignore")
        plain = re.sub(r"(?s)\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", "", plain)
        plain = re.sub(r"(?s)\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*", "", plain)
        plain = plain.strip()
        paras = [p.strip() for p in re.split(r"\n\s*\n", plain) if p.strip()]
        html_paras = []
        for p in paras:
            one = " ".join(p.split())
            if len(one) < 70 and not one.endswith(('.', '!', '?', ':', ';', ',', '—')):
                html_paras.append(f"<h3>{one}</h3>")
            else:
                html_paras.append(f"<p>{one}</p>")
        body_html = "\n".join(html_paras)
        full = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{PDF_CSS}</style></head><body>{body_html}</body></html>"
        base = str(root)
        # a plain but valid EPUB3 built from the same text
        epub_path = out / f"{book['slug']}.epub"
        chapters, chunk, size = [], [], 0
        for p in html_paras:
            chunk.append(p); size += len(p)
            if size > 24000:
                chapters.append("\n".join(chunk)); chunk, size = [], 0
        if chunk:
            chapters.append("\n".join(chunk))
        with zipfile.ZipFile(epub_path, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml",
                       '<?xml version="1.0"?><container version="1.0" '
                       'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                       '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                       '</rootfiles></container>')
            items, spine = [], []
            for i, ch in enumerate(chapters, 1):
                name = f"chapter-{i}.xhtml"
                z.writestr(f"OEBPS/{name}",
                           f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
                           f'<head><title>{book["title"]}</title></head><body>{ch}</body></html>')
                items.append(f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>')
                spine.append(f'<itemref idref="c{i}"/>')
            z.writestr("OEBPS/content.opf",
                       f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" '
                       f'version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                       f'<dc:identifier id="uid">corpus-extendum:{book["slug"]}</dc:identifier>'
                       f'<dc:title>{book["title"]}</dc:title><dc:creator>{book["author"]}</dc:creator>'
                       f'<dc:language>en</dc:language><dc:rights>Public domain</dc:rights></metadata>'
                       f'<manifest>{"".join(items)}</manifest><spine>{"".join(spine)}</spine></package>')
        cover_src = None

    # PDF
    from weasyprint import HTML
    pdf_path = out / f"{book['slug']}.pdf"
    HTML(string=full, base_url=base).write_pdf(str(pdf_path))

    # TXT
    txt_path = out / f"{book['slug']}.txt"
    txt_path.write_text(plain.strip() + "\n", encoding="utf-8")

    cover_path = out / "cover.jpg"
    cover_kind = use_or_make_cover(cover_src, cover_path, book)
    return pdf_path, epub_path, txt_path, cover_path, plain, cover_kind


# --------------------------------------------------------------------------- #
# the gate + the shelf
# --------------------------------------------------------------------------- #
def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="path to the vault repo checkout")
    ap.add_argument("--only", default="", help="comma separated gutenberg ids")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--replace", action="store_true", help="re-ingest a book already on the shelf")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    books_dir = vault / "books"
    books_dir.mkdir(parents=True, exist_ok=True)
    data = vault / ".." / "corpus-extendum" / "data"
    dedupe_path = data / "dedupe.json"
    registry = load_json(dedupe_path, {"source_refs": [], "text_sha256": {}, "work_keys": {}})

    wanted = [b for b in BOOKS if (args.all or str(b["id"]) in args.only.split(","))]
    if not wanted:
        log("nothing selected"); return 1

    # /tmp is a 64 MB tmpfs here; an illustrated edition blows straight through
    # it and tar fails quietly. Work on the real disk instead.
    scratch = Path(os.environ.get("CE_WORK", "/scratch/work/_tmp"))
    scratch.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ce-", dir=scratch))
    ok, failed = [], []
    for b in wanted:
        log(f"\n=== {b['id']} · {b['title']}")
        dest = books_dir / b["slug"]
        if args.replace:
            log("    --replace: clearing the existing copy and its registry entries")
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            registry["source_refs"] = [r for r in registry["source_refs"] if r != f"gutenberg:{b['id']}"]
            registry["text_sha256"] = {k: v for k, v in registry["text_sha256"].items() if v != b["slug"]}
            registry["work_keys"] = {k: v for k, v in registry["work_keys"].items() if v != b["slug"]}
        if (dest / "meta.json").exists():
            log("    already shelved — skipping")
            continue
        try:
            if b.get("se"):
                src_root = tarball(f"standardebooks/{b['se']}", work / b["slug"])
                kind = "se"
                source = dict(name="Standard Ebooks", ref=b["se"],
                              url=f"https://standardebooks.org/ebooks/{b['se'].replace('_', '/', 1)}",
                              licence="CC0 1.0 (edition) · text public domain")
            elif b.get("gitenberg"):
                src_root = tarball(b["gitenberg"], work / b["slug"])
                kind = "gitenberg"
                source = dict(name="GITenberg (Project Gutenberg mirror)", ref=b["gitenberg"],
                              url=f"https://www.gutenberg.org/ebooks/{b['id']}",
                              licence="Project Gutenberg Licence · text public domain")
            else:
                raise RuntimeError("no source configured")

            tmp_out = work / b["slug"] / "_out"
            tmp_out.mkdir(parents=True, exist_ok=True)
            pdf, epub, txt, cover, plain, cover_kind = build_from_tree(src_root, tmp_out, b, kind)

            # ---- dedupe gate -------------------------------------------- #
            tsha = text_sha(plain)
            ref = f"gutenberg:{b['id']}"
            if ref in registry["source_refs"]:
                raise RuntimeError(f"duplicate: source ref {ref} already shelved")
            if tsha in registry["text_sha256"]:
                raise RuntimeError(f"duplicate: text hash matches {registry['text_sha256'][tsha]}")

            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, dest / pdf.name)
            shutil.copy2(epub, dest / epub.name)
            shutil.copy2(txt, dest / txt.name)
            shutil.copy2(cover, dest / "cover.jpg")

            fmts = ["pdf", "epub", "txt"]
            meta = {
                "id": str(b["id"]), "slug": b["slug"], "title": b["title"],
                "author": {"name": b["author"], "file_as": b["author_file"], "death": b["death"]},
                "year": b["year"], "category": b["category"], "language": "en",
                "subjects": b.get("subjects", []), "blurb": b.get("blurb", ""),
                "rights": {
                    "basis": (f"author d. {b['death']}; first published {b['year']} — "
                              f"public domain in India (life + 60) and the United States (pre-1930)"),
                    "india": True, "us": True, "verified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
                "source": source,
                "formats": fmts,
                "files": {f: f"books/{b['slug']}/{b['slug']}.{f}" for f in fmts} | {"cover": f"books/{b['slug']}/cover.jpg"},
                "cover_kind": cover_kind,
                "vault": vault.name,
                "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "file_sha8": file_sha(dest / pdf.name)[:8],
                "text_sha256": tsha,
            }
            if b.get("translator"):
                meta["translator"] = {"name": b["translator"], "death": b["translator_death"]}
                meta["rights"]["basis"] += f"; translation by {b['translator']} (d. {b['translator_death']})"
            (dest / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

            registry["source_refs"].append(ref)
            registry["text_sha256"][tsha] = b["slug"]
            registry["work_keys"][f"{b['author_file'].split(',')[0].lower()}|{b['title'].lower()}|{b['year']}"] = b["slug"]

            kb = lambda p: int(p.stat().st_size / 1024)
            log(f"    pdf {kb(dest/pdf.name)} KB · epub {kb(dest/epub.name)} KB · txt {kb(dest/txt.name)} KB · cover {cover_kind}")
            ok.append(b["slug"])
        except Exception as e:
            log(f"    FAILED: {e}")
            failed.append((b["slug"], str(e)))

    data.mkdir(parents=True, exist_ok=True)
    dedupe_path.write_text(json.dumps(registry, indent=2) + "\n")
    log(f"\nshelved {len(ok)}: {', '.join(ok) or '—'}")
    if failed:
        log(f"failed {len(failed)}: " + "; ".join(f"{s} ({e})" for s, e in failed))
    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
