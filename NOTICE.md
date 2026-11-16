# Attribution and notices

Every book here is a public-domain work. The **edition** used to produce the
files is named in that book's record, and the credit stays there permanently.

## Software bundled in this repository

The reader ships its renderers locally, so a reading page makes no third-party
request. That means their licences travel with them, and they are recorded here.

| Component | Version | Licence | Licence text | Used for |
|---|---|---|---|---|
| [pdf.js](https://github.com/mozilla/pdf.js) | 3.11.174 | Apache-2.0 | [`assets/vendor/LICENSE-pdfjs.txt`](assets/vendor/LICENSE-pdfjs.txt) | rendering PDF pages to a canvas |
| [epub.js](https://github.com/futurepress/epub.js) | 0.3.93 | BSD-2-Clause | [`assets/vendor/LICENSE-epubjs.txt`](assets/vendor/LICENSE-epubjs.txt) | reflowable EPUB rendering |
| [JSZip](https://github.com/Stuk/jszip) | bundled with epub.js | MIT **or** GPLv3, at your choice | [`assets/vendor/LICENSE-jszip.md`](assets/vendor/LICENSE-jszip.md) | reading the EPUB archive |

- The Apache-2.0 notice in `pdf.min.js` is intact and is reproduced in full in
  the file linked above.
- JSZip is used under the **MIT** option of its dual licence.
- None of these files has been modified beyond being minified by their authors.

## Fonts

The page loads **Fraunces** and **Inter** from Google Fonts. Both are licensed
under the SIL Open Font License 1.1, which permits this use. They are not
redistributed by this repository — if Google Fonts is blocked, the page falls
back to a system serif and loses nothing but the exact typeface.

## Book sources

### Standard Ebooks

Forty-two of the shelved books are based on Standard Ebooks editions
(<https://standardebooks.org>). Their contributions to those editions — the
proofreading, the typesetting, the artwork — are released by them under the
**CC0 1.0 Universal Public Domain Dedication**, which is why they can be reused
here without conditions.

The PDFs in this library are **ours**, not theirs: typeset from their source
XHTML with our own stylesheet, at A5, with our own title page. If you want the
edition as Standard Ebooks intended it, take the EPUB — that is their file,
unmodified apart from image downscaling.

### Project Gutenberg, via the GITenberg mirror

Some texts come from the GITenberg mirror of Project Gutenberg. The texts are
public domain; the licence Project Gutenberg attaches is a separate agreement,
whose terms are respected here:

- attribution to the source ebook number is kept in the record;
- redistribution here is free of charge;
- no Project Gutenberg name, logo or trademark is used, and nothing here
  suggests Project Gutenberg endorses this library.

### Internet Archive

Used for scans that exist nowhere else. Its `collection:gutenberg` items were
checked and carry no text, only a readme, so the adapter looks in the dated
public-domain collections instead (`americana`, `cdl`, `toronto` and similar).

For each item the adapter reads the archive's own statement before anything is
downloaded — `possible-copyright-status` and `licenseurl` — and refuses the item
if it is not marked public domain. That signal is necessary but not sufficient:
a search for it turns up 2001 books, so the author gate still runs on top.

The PDF is the archive's scan, unmodified. The EPUB is built from the item's OCR
text. Credit and the item identifier are in the book's record.

## What is ours

Catalogue records, metadata, typesetting, generated covers, the site, the
pipeline and this documentation: **CC0 1.0**. Take them.

## Corrections

If a rights basis, an attribution or a licence here is wrong, open an issue. A
wrong attribution is a bug like any other and gets fixed in one commit.
