"""产出文档批量导出（v1.8，CODE_REVIEW.md F6）测试。"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from server.services import document_service


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    for day, names in (("2026-10-09", ["a.md", "b.md"]), ("2026-10-10", ["c.md"])):
        d = tmp_path / day
        d.mkdir(parents=True)
        for name in names:
            (d / name).write_text(f"# {name} 标题\n\n## 一、项目基础大白话介绍\n\n正文内容。\n",
                                  encoding="utf-8")
    monkeypatch.setattr(document_service, "OUTPUTS_DIR", tmp_path)
    return tmp_path


def _names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return sorted(zf.namelist())


def test_export_all_documents(outputs):
    data, filename, note = document_service.build_export_zip()
    assert data is not None
    assert filename == "github-trend-learner-all.zip"
    assert _names(data) == [
        "2026-10-09/a.md", "2026-10-09/b.md", "2026-10-10/c.md", "MANIFEST.txt",
    ]
    assert "3 份" in note


def test_export_single_date(outputs):
    data, filename, _ = document_service.build_export_zip("2026-10-10")
    assert filename == "github-trend-learner-2026-10-10.zip"
    assert _names(data) == ["2026-10-10/c.md", "MANIFEST.txt"]


def test_manifest_lists_files_and_scope(outputs):
    data, _, _ = document_service.build_export_zip("2026-10-09")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest = zf.read("MANIFEST.txt").decode("utf-8")
    assert "2026-10-09" in manifest
    assert "2026-10-09/a.md" in manifest
    assert "文档数量：2" in manifest


def test_export_returns_none_when_no_match(outputs):
    data, filename, note = document_service.build_export_zip("1999-01-01")
    assert data is None and filename == ""
    assert "没有匹配" in note


def test_export_zip_is_readable_and_content_intact(outputs):
    data, _, _ = document_service.build_export_zip()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert zf.testzip() is None, "ZIP 结构必须完整"
        assert "正文内容" in zf.read("2026-10-10/c.md").decode("utf-8")


# ---------------- 路由层 ----------------

def _req(path: str):
    from server.http.request import Request

    return Request.from_raw("GET", path, {}, b"")


def test_route_export_returns_zip(outputs):
    from server.routes.documents import export_documents

    resp = export_documents(_req("/api/documents/export"))
    assert resp.status == 200
    assert resp.content_type == "application/zip"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in resp.headers["Content-Disposition"]
    assert _names(resp.body)[-1] == "MANIFEST.txt"


def test_route_export_rejects_bad_date(outputs):
    from server.routes.documents import export_documents

    resp = export_documents(_req("/api/documents/export?date=2026-13-99x"))
    assert resp.status == 400
    assert json.loads(resp.body)["error"]["code"] == "INVALID_DATE"


def test_route_export_404_when_empty(outputs):
    from server.routes.documents import export_documents

    resp = export_documents(_req("/api/documents/export?date=1999-01-01"))
    assert resp.status == 404
    assert json.loads(resp.body)["error"]["code"] == "NOTHING_TO_EXPORT"


def test_export_route_registered_before_detail_route(outputs):
    """`/api/documents/export` 必须能匹配到导出处理器，而不是被详情路由吞掉。"""
    from server.app import build_router

    matched = build_router().match("GET", "/api/documents/export")
    assert matched is not None
    handler, params = matched
    assert params == {}, "导出路径不应带路径参数"
    resp = handler(_req("/api/documents/export"))
    assert resp.content_type == "application/zip"
