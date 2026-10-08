#!/usr/bin/env python3
"""Validate the catalog the same way the app does before importing it."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
STATUSES = {"draft", "active", "superseded", "withdrawn", "unknown"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_DOCUMENT_FIELDS = (
    "id",
    "company_id",
    "product_id",
    "name",
    "version",
    "effective_date",
    "document_type",
    "source_url",
    "file_name",
    "file_size",
    "sha256",
    "status",
)


REQUIRED_COMPANY_FIELDS = ("id", "name")
REQUIRED_PRODUCT_FIELDS = ("id", "company_id", "name")


def _bad_path(path: str) -> bool:
    return (
        not path
        or path.startswith("/")
        or "\\" in path
        or ":" in path
        or ".." in path.split("/")
    )


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    def load(path: str):
        try:
            return json.loads((root / path).read_bytes())
        except FileNotFoundError:
            errors.append(f"{path}: missing file")
        except json.JSONDecodeError as e:
            errors.append(f"{path}: invalid JSON ({e})")
        return None

    def objects(value, ctx: str) -> list[dict]:
        """A JSON array of objects; anything else is reported, not raised."""
        if value is None:
            return []
        if not isinstance(value, list):
            errors.append(f"{ctx}: must be a JSON array")
            return []
        items = []
        for item in value:
            if isinstance(item, dict):
                items.append(item)
            else:
                errors.append(f"{ctx}: entry is not a JSON object ({item!r})")
        return items

    def require_strings(item: dict, keys, ctx: str) -> None:
        for key in keys:
            if key not in item:
                errors.append(f"{ctx} missing {key}")
            elif not isinstance(item[key], str):
                errors.append(f"{ctx} {key} must be a string")

    def unique(items: list[dict], kind: str) -> None:
        seen: set = set()
        for item in items:
            item_id = item.get("id")
            if not isinstance(item_id, str):
                continue
            if item_id in seen:
                errors.append(f"{kind}: duplicate id {item_id}")
            seen.add(item_id)

    manifest = load("manifest.json")
    if manifest is not None and not isinstance(manifest, dict):
        errors.append("manifest.json: must be a JSON object")
        manifest = None
    manifest = manifest or {}
    for key in ("schema_version", "data_version", "files"):
        if key not in manifest:
            errors.append(f"manifest.json: missing {key}")
    for entry in objects(manifest.get("files"), "manifest.json files"):
        path = entry.get("path")
        if not isinstance(path, str) or _bad_path(path):
            errors.append(f"manifest.json: bad path {path!r}")

    companies = objects(load("companies.json"), "companies.json")
    for company in companies:
        require_strings(company, REQUIRED_COMPANY_FIELDS, f"companies: {company.get('id')}")
    unique(companies, "companies")
    products: list[dict] = []
    documents: list[dict] = []
    for company in companies:
        company_id = company.get("id")
        if not isinstance(company_id, str):
            continue
        for kind, target in (("products", products), ("documents", documents)):
            path = f"{kind}/{company_id}.json"
            target += objects(load(path), path)
    unique(products, "products")
    unique(documents, "documents")

    company_ids = {c["id"] for c in companies if isinstance(c.get("id"), str)}
    product_company: dict[str, str] = {}
    for product in products:
        ctx = f"products: {product.get('id')}"
        require_strings(product, REQUIRED_PRODUCT_FIELDS, ctx)
        if product.get("company_id") not in company_ids:
            errors.append(f"{ctx} company_id not found ({product.get('company_id')})")
        if isinstance(product.get("id"), str):
            product_company[product["id"]] = product.get("company_id")

    for doc in documents:
        ctx = f"documents: {doc.get('id')}"
        for key in REQUIRED_DOCUMENT_FIELDS:
            if key not in doc:
                errors.append(f"{ctx} missing {key}")
            elif key != "file_size" and not isinstance(doc[key], str):
                errors.append(f"{ctx} {key} must be a string")
        product_id = doc.get("product_id")
        company = product_company.get(product_id) if isinstance(product_id, str) else None
        if company is None:
            errors.append(f"{ctx} product_id not found ({product_id})")
        elif company != doc.get("company_id"):
            errors.append(f"{ctx} company_id ({doc.get('company_id')}) does not match its product")
        if doc.get("status") not in STATUSES:
            errors.append(f"{ctx} status not one of {sorted(STATUSES)} ({doc.get('status')})")
        if not SHA256.match(str(doc.get("sha256", ""))):
            errors.append(f"{ctx} sha256 must be 64 lowercase hex characters")
        size = doc.get("file_size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{ctx} file_size must be a positive integer")
        if not str(doc.get("source_url", "")).startswith(("https://", "http://")):
            errors.append(f"{ctx} source_url must be http(s)")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    errors = validate(args.root)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("catalog is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
