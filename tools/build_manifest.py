#!/usr/bin/env python3
"""Recompute manifest.json's file list and bump data_version (spec §2.2).

Run after every data change, then commit. --check only compares (used by CI).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def catalog_paths(root: Path) -> list[str]:
    """companies.json plus the products/documents file of every company."""
    companies = json.loads((root / "companies.json").read_bytes())
    paths = ["companies.json"]
    for company in companies:
        paths.append(f"products/{company['id']}.json")
        paths.append(f"documents/{company['id']}.json")
    return sorted(paths)


def file_entries(root: Path) -> list[dict]:
    entries = []
    for path in catalog_paths(root):
        data = (root / path).read_bytes()
        entries.append(
            {
                "path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    return entries


def next_data_version(old: int, today: dt.date) -> int:
    return max(int(today.strftime("%Y%m%d")) * 100 + 1, old + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--check", action="store_true", help="fail if stale; write nothing")
    parser.add_argument("--today", type=dt.date.fromisoformat, default=None)
    args = parser.parse_args(argv)

    manifest_path = args.root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    entries = file_entries(args.root)
    if manifest.get("files") == entries:
        print("manifest.json is up to date")
        return 0
    if args.check:
        print("manifest.json is stale: run tools/build_manifest.py", file=sys.stderr)
        return 1

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    today = args.today or now.date()
    manifest = {
        "schema_version": manifest.get("schema_version", 1),
        "data_version": next_data_version(int(manifest.get("data_version", 0)), today),
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "files": entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"data_version -> {manifest['data_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
