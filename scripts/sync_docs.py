#!/usr/bin/env python3
"""
sync_docs.py — mirror this repository's documentation into another repository.

    python3 scripts/sync_docs.py --target ../audit/reports/2026-11-corpus-extendum
    python3 scripts/sync_docs.py --target … --check

The audit repo is the fleet's change log: a report is a measurement or a plan,
with its evidence beside it. The evidence here is the documentation itself, so
this copies it and records exactly what was copied — source commit, timestamp,
and a hash per file — into `SYNC.json` next to it.

`--check` compares instead of copying and exits 1 if the mirror has drifted from
the source, which is the only way a mirror stays honest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The document set. Deliberately explicit: a glob would one day sweep up a
# scratch file, and the audit repo is not a scratch pad.
DOCS = [
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/README.md",
    "docs/ARCHITECTURE.md",
    "docs/PIPELINE.md",
    "docs/DATA-MODEL.md",
    "docs/OPERATIONS.md",
    "docs/FRONTEND.md",
    "docs/VAULTS.md",
    "docs/DECISIONS.md",
    "docs/RIGHTS.md",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def git_head(library: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=library,
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default=".")
    ap.add_argument("--target", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--subdir", default="docs", help="folder inside the target for the mirror")
    args = ap.parse_args()

    library = Path(args.library).resolve()
    target = Path(args.target).resolve()
    mirror = target / args.subdir

    present = [d for d in DOCS if (library / d).exists()]
    missing = [d for d in DOCS if not (library / d).exists()]
    if missing:
        print(f"  warning: not found, skipped: {', '.join(missing)}")

    manifest = {
        "source": "drsamonline/corpus-extendum",
        "commit": git_head(library),
        "synced": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "files": {d: sha(library / d) for d in present},
    }

    if args.check:
        existing = target / "SYNC.json"
        if not existing.exists():
            print(f"  no SYNC.json in {target} — the mirror has never been synced")
            return 1
        old = json.loads(existing.read_text())
        drift = [d for d, h in manifest["files"].items()
                 if old.get("files", {}).get(d) != h]
        if drift:
            print("  drifted:", ", ".join(drift))
            return 1
        print(f"  mirror matches the source ({len(present)} files, commit {manifest['commit'][:7]})")
        return 0

    mirror.mkdir(parents=True, exist_ok=True)
    copied = 0
    for d in present:
        # Preserve the relative path. Flattening by filename silently lost
        # README.md to docs/README.md, because both are called README.md.
        dest = mirror / d
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(library / d, dest)
        copied += 1
    (target / "SYNC.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"  copied {copied} files to {mirror}")
    print(f"  wrote {target / 'SYNC.json'} (commit {manifest['commit'][:7]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
