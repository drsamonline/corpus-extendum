#!/usr/bin/env python3
"""
update_docs.py — keep the numbers in the documentation true.

    python3 scripts/update_docs.py --check    # exit 1 if any doc has drifted
    python3 scripts/update_docs.py --write    # rewrite the anchors from the data

Documentation rots in one specific way: the counts. "43 books" is correct on the
day it is typed and wrong the next time a book is shelved. Every such number in
this repository is an *anchor* — a pattern this script knows how to find and
rewrite from `data/catalog.json` and `data/shards.json`.

The weekly scan runs `--write`, so the docs cannot drift by more than one run.
`--check` exists so a pull request can be failed for drift instead of a reader
discovering it.

Nothing outside the anchors is touched. Prose is not generated.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# (file, pattern, replacement template) — {books} {cats} {mb} {kb} {date}
RULES = [
    ("README.md", r"books-\d+-1F4E46", "books-{books}-1F4E46"),
    ("README.md", r"\d+ books, \d+ categories, one shelf",
     "{books} books, {cats} categories, one shelf"),
    ("docs/README.md", r"\*\*What is on the shelf right now:\*\* \d+ books, \d+ categories, [\d.]+ MB",
     "**What is on the shelf right now:** {books} books, {cats} categories, {mb} MB"),
    ("docs/VAULTS.md", r"\| `corpus-extendum-vault-01` \| \d+ \| [\d.]+ MB \| open \|",
     "| `corpus-extendum-vault-01` | {books} | {mb} MB | open |"),
    ("docs/VAULTS.md", r"Headroom: \d+ books or \d+ MB\.",
     "Headroom: {headroom_books} books or {headroom_mb} MB."),
    ("docs/DATA-MODEL.md", r"At \d+ books it is \d+ KB\.", "At {books} books it is {kb} KB."),
    ("docs/README.md", r"^_Updated [\d-]+\.?_$", "_Updated {date}._"),
]


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def facts(library: Path) -> dict:
    catalog = load(library / "data" / "catalog.json", []) or []
    cats = load(library / "data" / "categories.json", []) or []
    shards = load(library / "data" / "shards.json", []) or []
    open_shard = next((s for s in shards if s.get("state") == "open"), {})
    catalog_bytes = (library / "data" / "catalog.json")
    return {
        "books": len(catalog),
        "cats": len(cats),
        "mb": open_shard.get("mb", 0),
        "kb": round(catalog_bytes.stat().st_size / 1024) if catalog_bytes.exists() else 0,
        "headroom_books": open_shard.get("cap_books", 0) - open_shard.get("books", 0),
        "headroom_mb": round(open_shard.get("cap_mb", 0) - open_shard.get("mb", 0), 1),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default=".")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    library = Path(args.library).resolve()
    f = facts(library)
    if not args.write and not args.check:
        args.check = True

    drifted, changed = [], []
    for rel, pattern, template in RULES:
        path = library / rel
        if not path.exists():
            continue
        text = path.read_text()
        want = template.format(**f)
        new = re.sub(pattern, want, text, flags=re.M)
        if new != text:
            if args.write:
                path.write_text(new)
                changed.append(f"{rel}: → {want}")
            else:
                found = re.search(pattern, text, flags=re.M)
                drifted.append(f"{rel}: has {found.group(0)!r}, should be {want!r}")

    for line in changed:
        print(f"  updated  {line}")
    for line in drifted:
        print(f"  drifted  {line}")

    if args.check and drifted:
        print(f"\n{len(drifted)} anchor(s) out of date — run --write")
        return 1
    if not changed and not drifted:
        print(f"  docs match the catalogue: {f['books']} books, {f['cats']} categories, {f['mb']} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
