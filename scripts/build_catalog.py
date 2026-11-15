#!/usr/bin/env python3
"""
build_catalog.py — turn the vault's book records into everything the site reads.

    python3 scripts/build_catalog.py --vault ../corpus-extendum-vault-01

Writes, in the library repo:
    data/catalog.json       every book, merged from every vault
    data/search-index.json  tokens for the client-side search
    data/categories.json    the rail, with counts
    data/shards.json        the vault registry
    index.txt               the whole catalogue, plain text, human readable

And in the vault:
    index.txt               that vault's own catalogue
    manifest.json           the same, machine-readable

The catalogue build is the final authority on identity: if two records share a
text hash, the later one is quarantined here and disappears from the site. A
sealed vault is never edited — the catalogue simply stops showing the book.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CAP_BOOKS = 600
CAP_MB = 2500


def load(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default


def size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 1)


def vault_index(vault: Path, books: list[dict], state: str) -> str:
    head = (f"# {vault.name} | {len(books)} books | {size_mb(vault)} MB | "
            f"cap {CAP_BOOKS} books / {CAP_MB} MB | state: {state} | "
            f"built {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}")
    cols = ("# id | slug | title | author | year | category | lang | pd_basis | "
            "formats | pdf_kb | epub_kb | path | file_sha8 | text_sha8")
    lines = [head, cols]
    for b in sorted(books, key=lambda x: x["slug"]):
        f = b["files"]
        pdf_kb = int((vault / f["pdf"]).stat().st_size / 1024) if (vault / f["pdf"]).exists() else 0
        epub_kb = int((vault / f["epub"]).stat().st_size / 1024) if (vault / f["epub"]).exists() else 0
        lines.append("|".join([
            b["id"], b["slug"], b["title"], b["author"]["file_as"], str(b["year"]),
            b["category"], b["language"], b["rights"]["basis"].split(" — ")[0],
            ",".join(b["formats"]), str(pdf_kb), str(epub_kb),
            f"books/{b['slug']}", b.get("file_sha8", ""), b.get("text_sha256", "")[:8],
        ]))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", action="append", required=True)
    ap.add_argument("--library", default=".")
    args = ap.parse_args()

    lib = Path(args.library).resolve()
    data = lib / "data"
    data.mkdir(exist_ok=True)

    catalog, shards, seen_text, quarantined = [], [], {}, []
    for vpath in args.vault:
        vault = Path(vpath).resolve()
        books = []
        for meta_path in sorted(vault.glob("books/*/meta.json")):
            m = load(meta_path, None)
            if not m:
                continue
            books.append(m)

        mb = size_mb(vault)
        state = "sealed" if (len(books) >= CAP_BOOKS or mb >= CAP_MB) else "open"
        shards.append({
            "name": vault.name, "repo": f"drsamonline/{vault.name}",
            "cdn": f"https://cdn.jsdelivr.net/gh/drsamonline/{vault.name}@main",
            "raw": f"https://raw.githubusercontent.com/drsamonline/{vault.name}/main",
            "books": len(books), "mb": mb, "state": state,
            "cap_books": CAP_BOOKS, "cap_mb": CAP_MB,
        })
        (vault / "index.txt").write_text(vault_index(vault, books, state))
        (vault / "manifest.json").write_text(json.dumps(
            {"vault": vault.name, "state": state, "books": len(books), "mb": mb,
             "cap": {"books": CAP_BOOKS, "mb": CAP_MB}, "records": books},
            indent=2, ensure_ascii=False) + "\n")

        for m in books:
            tsha = m.get("text_sha256", "")
            if tsha and tsha in seen_text:
                m["quarantined"] = f"duplicate of {seen_text[tsha]}"
                quarantined.append((m["slug"], seen_text[tsha]))
                continue
            if tsha:
                seen_text[tsha] = m["slug"]
            catalog.append(m)

    catalog.sort(key=lambda b: (b["category"], b["year"], b["title"]))
    (data / "catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")

    cats = {}
    for b in catalog:
        cats[b["category"]] = cats.get(b["category"], 0) + 1
    (data / "categories.json").write_text(json.dumps(
        sorted(cats.items(), key=lambda kv: (-kv[1], kv[0])), indent=2) + "\n")

    # search tokens: title, author, category, subjects, blurb — cheap and enough
    index = []
    for b in catalog:
        hay = " ".join([b["title"], b["author"]["name"], b["category"],
                        " ".join(b.get("subjects", [])), b.get("blurb", "")]).lower()
        toks = sorted({t for t in re.findall(r"[a-z0-9]{2,}", hay)})
        index.append({"slug": b["slug"], "t": toks})
    (data / "search-index.json").write_text(json.dumps(index, separators=(",", ":")) + "\n")
    (data / "shards.json").write_text(json.dumps(shards, indent=2) + "\n")

    # the library's own plain-text catalogue
    out = [f"# corpus-extendum | {len(catalog)} books | {len(shards)} vault(s) | "
           f"built {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}",
           "# id | slug | title | author | year | category | formats | vault"]
    for b in catalog:
        out.append("|".join([b["id"], b["slug"], b["title"], b["author"]["file_as"],
                             str(b["year"]), b["category"], ",".join(b["formats"]), b["vault"]]))
    (lib / "index.txt").write_text("\n".join(out) + "\n")

    report = [f"build {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}",
              f"catalogued {len(catalog)}", f"vaults {len(shards)}",
              f"quarantined {len(quarantined)}"]
    report += [f"  {s} (duplicate of {o})" for s, o in quarantined]
    (lib / "dedupe-report.txt").write_text("\n".join(report) + "\n")

    print("\n".join(report))
    for s in shards:
        print(f"  {s['name']}: {s['books']} books, {s['mb']} MB, {s['state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
