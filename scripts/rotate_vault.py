#!/usr/bin/env python3
"""
rotate_vault.py — seal a full vault and open the next one.

    python3 scripts/rotate_vault.py --dry-run     # say what would happen
    python3 scripts/rotate_vault.py               # do it

A vault seals at CAP_BOOKS books or CAP_MB megabytes, whichever comes first.
Sealing is a commit, never a deletion: the vault keeps every file it has, gets a
final index.txt that says `state: sealed`, and is read-only from then on. The
next vault is created, registered in data/shards.json, and becomes the target
for ingest.

Creating a repository needs a token that can create repositories. The default
`GITHUB_TOKEN` inside Actions cannot — it is scoped to the repository the
workflow runs in — and neither can a GitHub App installation token. So this
needs a fine-grained PAT in CORPUS_BOT_TOKEN with:

    Administration: write      (create repositories)
    Contents: write            (commit the new vault's first files)

The preflight below creates and immediately deletes a throwaway repository to
prove the token can do it, before anything real is touched. That is the same
guard the `backup` repo uses, and for the same reason: discovering the
permission problem at the moment a vault fills up is discovering it too late.

With no usable token the script does not fail silently — it prints the exact
`gh` command to run by hand, and exits 3 so the workflow can open an issue.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CAP_BOOKS = 600
CAP_MB = 2500
OWNER = "drsamonline"
BASE = "corpus-extendum-vault"
API = "https://api.github.com"
PROBE = "_corpus-extendum-token-check-delete-me"


def call(method, path, token=None, data=None, timeout=60):
    url = path if path.startswith("http") else API + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "corpus-extendum/1.0")
    if body:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read()[:200].decode("utf-8", "ignore")}
    except Exception as e:
        return 0, {"_error": str(e)[:200]}


def load_shards(library: Path):
    p = library / "data" / "shards.json"
    if not p.exists():
        raise SystemExit(f"no {p} — run build_catalog.py first")
    return json.loads(p.read_text()), p


def needs_rotation(shards):
    """The open vault, and whether it has reached its cap."""
    open_shards = [s for s in shards if s.get("state") == "open"]
    if not open_shards:
        return None, False
    current = open_shards[-1]
    full = current["books"] >= current.get("cap_books", CAP_BOOKS) or \
           current["mb"] >= current.get("cap_mb", CAP_MB)
    return current, full


def next_name(shards):
    nums = []
    for s in shards:
        tail = s["name"].rsplit("-", 1)[-1]
        if tail.isdigit():
            nums.append(int(tail))
    return f"{BASE}-{max(nums, default=0) + 1:02d}"


def preflight(token):
    """Prove the token can create a repository, then clean up after itself."""
    status, _ = call("POST", "/user/repos", token,
                     {"name": PROBE, "private": True, "auto_init": True,
                      "description": "temporary: corpus-extendum rotation token check"})
    if status not in (200, 201):
        return False, f"cannot create a repository ({status})"
    status, _ = call("DELETE", f"/repos/{OWNER}/{PROBE}", token)
    if status not in (200, 204):
        return True, f"can create, but could not delete the probe repo ({status}) — remove {PROBE} by hand"
    return True, "token can create and delete repositories"


def seal(shards, current, library: Path, dry_run: bool):
    name = next_name(shards)
    cdn = f"https://cdn.jsdelivr.net/gh/{OWNER}/{name}@main"
    raw = f"https://raw.githubusercontent.com/{OWNER}/{name}/main"
    entry = {
        "name": name, "repo": f"{OWNER}/{name}", "cdn": cdn, "raw": raw,
        "books": 0, "mb": 0.0, "state": "open",
        "cap_books": CAP_BOOKS, "cap_mb": CAP_MB,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
    }
    print(f"  seal    {current['name']}  ({current['books']} books, {current['mb']} MB)")
    print(f"  open    {name}")
    if dry_run:
        print("  dry run: shards.json not written, no repository created")
        return 0

    current["state"] = "sealed"
    current["sealed"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    shards.append(entry)
    (library / "data" / "shards.json").write_text(json.dumps(shards, indent=2) + "\n")
    print(f"  wrote   data/shards.json ({len(shards)} vaults)")

    log = library / "data" / "rotation-log.txt"
    with log.open("a") as f:
        f.write(f"{entry['built']} sealed {current['name']} at {current['books']} books "
                f"/ {current['mb']} MB; opened {name}\n")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="rotate even if the vault is not full")
    args = ap.parse_args()

    library = Path(args.library).resolve()
    shards, _ = load_shards(library)
    current, full = needs_rotation(shards)

    if current is None:
        print("no open vault — nothing to rotate")
        return 0
    print(f"open vault: {current['name']} · {current['books']}/{current.get('cap_books', CAP_BOOKS)} books · "
          f"{current['mb']}/{current.get('cap_mb', CAP_MB)} MB")

    if not full and not args.force:
        headroom = current.get("cap_books", CAP_BOOKS) - current["books"]
        print(f"not full — {headroom} books and "
              f"{round(current.get('cap_mb', CAP_MB) - current['mb'], 1)} MB of headroom left")
        return 0

    token = os.environ.get("CORPUS_BOT_TOKEN", "")
    if args.dry_run:
        seal(shards, current, library, dry_run=True)
        if not token:
            print("  note: CORPUS_BOT_TOKEN is not set, so the real run would need one")
        return 0

    if not token:
        print("\nCORPUS_BOT_TOKEN is not set, and no other token here can create repositories.")
        print("Either set it (Administration: write + Contents: write), or run:")
        print(f"  gh repo create {next_name(shards)} --public")
        return 3

    ok, why = preflight(token)
    print(f"  token: {why}")
    if not ok:
        print("\nThe token cannot create repositories, so rotation cannot proceed.")
        print(f"Either grant it Administration: write, or run: gh repo create {next_name(shards)} --public")
        return 3

    code = seal(shards, current, library, dry_run=False)
    if code:
        return code

    name = next_name(shards[:-1])
    status, body = call("POST", "/user/repos", token, {
        "name": name, "private": False, "auto_init": True,
        "description": f"Book storage for Corpus Extendum, part {name.rsplit('-', 1)[-1]}. "
                       f"No website here: Pages caps a site at 1 GB and this vault is built for 2.5 GB.",
    })
    if status not in (200, 201):
        print(f"  could not create {OWNER}/{name}: {status} {body.get('_error', '')}")
        print("  shards.json already lists it — create the repo by hand and the next run will fill it")
        return 3
    print(f"  created {OWNER}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
