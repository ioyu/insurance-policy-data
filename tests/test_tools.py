import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_manifest  # noqa: E402
import validate  # noqa: E402

SHA = "a" * 64


def write(root: Path, path: str, value) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8", newline="\n")


def document(**overrides):
    doc = {
        "id": "d1",
        "company_id": "c1",
        "product_id": "p1",
        "name": "條款",
        "version": "2026-07-01",
        "effective_date": "2026-07-01",
        "document_type": "policy_terms",
        "source_url": "https://example.com/a.pdf",
        "file_name": "a.pdf",
        "file_size": 10,
        "sha256": SHA,
        "status": "active",
    }
    doc.update(overrides)
    return doc


def make_catalog(root: Path, documents=None, products=None) -> Path:
    write(root, "companies.json", [{"id": "c1", "name": "測試人壽"}])
    write(root, "products/c1.json", products or [{"id": "p1", "company_id": "c1", "name": "商品"}])
    write(root, "documents/c1.json", documents or [document()])
    write(root, "manifest.json", {"schema_version": 1, "data_version": 2026100501})
    return root


def test_file_entries_hash_and_size(tmp_path):
    root = make_catalog(tmp_path)
    entries = build_manifest.file_entries(root)
    assert [e["path"] for e in entries] == [
        "companies.json",
        "documents/c1.json",
        "products/c1.json",
    ]
    data = (root / "companies.json").read_bytes()
    assert entries[0] == {
        "path": "companies.json",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def test_next_data_version():
    today = dt.date(2026, 10, 8)
    assert build_manifest.next_data_version(2026100501, today) == 2026100801
    assert build_manifest.next_data_version(2026100801, today) == 2026100802


def test_build_writes_files_then_is_stable(tmp_path):
    root = make_catalog(tmp_path)
    assert build_manifest.main(["--root", str(root), "--today", "2026-10-08"]) == 0
    manifest = json.loads((root / "manifest.json").read_bytes())
    assert manifest["data_version"] == 2026100801
    assert manifest["files"] == build_manifest.file_entries(root)
    assert manifest["generated_at"].endswith("Z")

    # 內容沒變 → 不遞增
    assert build_manifest.main(["--root", str(root), "--today", "2026-10-08"]) == 0
    assert json.loads((root / "manifest.json").read_bytes())["data_version"] == 2026100801


def test_check_fails_when_stale_and_writes_nothing(tmp_path):
    root = make_catalog(tmp_path)
    before = (root / "manifest.json").read_bytes()
    assert build_manifest.main(["--root", str(root), "--check"]) == 1
    assert (root / "manifest.json").read_bytes() == before

    build_manifest.main(["--root", str(root), "--today", "2026-10-08"])
    assert build_manifest.main(["--root", str(root), "--check"]) == 0


def test_manifest_written_with_lf(tmp_path):
    root = make_catalog(tmp_path)
    build_manifest.main(["--root", str(root), "--today", "2026-10-08"])
    assert b"\r\n" not in (root / "manifest.json").read_bytes()


def built(tmp_path, **kwargs) -> Path:
    root = make_catalog(tmp_path, **kwargs)
    build_manifest.main(["--root", str(root), "--today", "2026-10-08"])
    return root


def test_validate_ok(tmp_path):
    assert validate.validate(built(tmp_path)) == []


def test_validate_duplicate_document_id(tmp_path):
    errors = validate.validate(built(tmp_path, documents=[document(), document()]))
    assert any("duplicate id d1" in e for e in errors)


def test_validate_missing_product(tmp_path):
    errors = validate.validate(built(tmp_path, documents=[document(product_id="nope")]))
    assert any("product_id" in e for e in errors)


def test_validate_company_mismatch(tmp_path):
    root = built(
        tmp_path,
        documents=[document(company_id="c2")],
    )
    assert any("company_id" in e for e in validate.validate(root))


def test_validate_product_company_missing(tmp_path):
    root = built(tmp_path, products=[{"id": "p1", "company_id": "nope", "name": "x"}])
    assert any("company_id" in e for e in validate.validate(root))


def test_validate_bad_status_sha_size_url(tmp_path):
    root = built(
        tmp_path,
        documents=[
            document(id="d1", status="old"),
            document(id="d2", sha256="XYZ"),
            document(id="d3", file_size=0),
            document(id="d4", source_url="ftp://x/a.pdf"),
        ],
    )
    errors = validate.validate(root)
    assert any("d1" in e and "status" in e for e in errors)
    assert any("d2" in e and "sha256" in e for e in errors)
    assert any("d3" in e and "file_size" in e for e in errors)
    assert any("d4" in e and "source_url" in e for e in errors)


def test_validate_missing_required_field(tmp_path):
    bad = document()
    del bad["version"]
    assert any("version" in e for e in validate.validate(built(tmp_path, documents=[bad])))


def test_validate_bad_manifest_path(tmp_path):
    root = built(tmp_path)
    manifest = json.loads((root / "manifest.json").read_bytes())
    manifest["files"].append({"path": "../x.json", "sha256": SHA, "size": 1})
    write(root, "manifest.json", manifest)
    assert any("bad path" in e for e in validate.validate(root))


def test_validate_missing_file(tmp_path):
    root = built(tmp_path)
    (root / "documents/c1.json").unlink()
    assert any("documents/c1.json" in e for e in validate.validate(root))


def test_repo_data_is_valid():
    assert validate.validate(ROOT) == []
    assert build_manifest.main(["--root", str(ROOT), "--check"]) == 0
