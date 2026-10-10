"""文档服务（server/services/document_service.py）测试。

此前覆盖率 65%，未覆盖的是「按 ## 切分模块」与「文档头元信息解析」——
这两处直接决定阅读器目录与元信息是否正确显示。
"""
from __future__ import annotations

import pytest

from server.services import document_service as ds


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "OUTPUTS_DIR", tmp_path)
    return tmp_path


_DOC = """# a/b 新手解读

> 仓库地址：https://github.com/a/b
> 数据获取时间：2026-10-10 10:00
> 项目类型：工具 / 应用

## 一、项目基础大白话介绍

这是介绍。

## 二、零基础通俗原理讲解

这是原理。

## 附：本次术语速查表

CLI（命令行界面）
"""


def _write(root, date: str, name: str, text: str):
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


# ---------------- 模块切分 ----------------

def test_split_modules_maps_known_titles_to_keys():
    mods = ds._split_modules(_DOC)
    keys = [m["key"] for m in mods]
    assert keys[:2] == ["intro", "principle"]
    assert mods[0]["title"] == "项目基础大白话介绍", "应去掉「一、」序号前缀"
    assert mods[0]["raw_title"] == "一、项目基础大白话介绍"


def test_split_modules_keeps_unknown_title_as_section():
    """未知标题保留为 section-N，前端照常渲染（兼容六/七模块切换期）。"""
    mods = ds._split_modules(_DOC)
    assert mods[-1]["key"].startswith("section-")
    assert mods[-1]["title"] == "附：本次术语速查表"


def test_split_modules_maps_legacy_errors_key():
    """历史产出里的「报错大全」应仍能识别为 errors（v1.5 已删除该模块）。"""
    text = "# t\n\n## 六、部署与使用常见报错大全\n\n内容\n"
    assert ds._split_modules(text)[0]["key"] == "errors"


def test_split_modules_content_excludes_heading():
    mods = ds._split_modules(_DOC)
    assert mods[0]["content"].startswith("这是介绍")
    assert "## 一、" not in mods[0]["content"]


def test_split_modules_returns_empty_without_h2():
    assert ds._split_modules("# 只有一级标题\n\n正文\n") == []


def test_split_modules_handles_last_section_to_eof():
    text = "## 一、项目基础大白话介绍\n\n结尾没有更多标题\n"
    mods = ds._split_modules(text)
    assert mods[0]["content"] == "结尾没有更多标题"


# ---------------- 文档头元信息 ----------------

def test_head_summary_parses_key_value_lines():
    info = ds._head_summary(_DOC)
    assert info["仓库地址"] == "https://github.com/a/b"
    assert info["项目类型"] == "工具 / 应用"


def test_head_summary_stops_at_first_non_quote_block():
    info = ds._head_summary(_DOC)
    assert "这是介绍" not in str(info)


def test_head_summary_supports_ascii_colon():
    assert ds._head_summary("> key: value\n")["key"] == "value"


def test_head_summary_returns_empty_when_no_meta():
    assert ds._head_summary("# 标题\n\n正文\n") == {}


def test_head_summary_ignores_body_beyond_first_20_lines():
    text = "\n".join(f"行{i}" for i in range(30)) + "\n> 很后面的键：值\n"
    assert ds._head_summary(text) == {}


# ---------------- 列表 ----------------

def test_list_documents_sorted_by_date_desc(outputs):
    _write(outputs, "2026-10-09", "a.md", _DOC)
    _write(outputs, "2026-10-10", "b.md", _DOC)

    docs = ds.list_documents()
    assert [d["date"] for d in docs] == ["2026-10-10", "2026-10-09"]
    assert docs[0]["doc_id"] == "2026-10-10/b.md"


def test_list_documents_skips_non_date_dirs_and_non_md(outputs):
    _write(outputs, "2026-10-10", "a.md", _DOC)
    _write(outputs, "notes", "x.md", _DOC)
    (outputs / "2026-10-10" / "readme.txt").write_text("x", encoding="utf-8")

    docs = ds.list_documents()
    assert len(docs) == 1 and docs[0]["name"] == "a.md"


def test_list_documents_counts_modules_and_size(outputs):
    _write(outputs, "2026-10-10", "a.md", _DOC)
    doc = ds.list_documents()[0]
    assert doc["module_count"] == 3
    assert doc["size"] > 0
    assert doc["title"] == "a/b 新手解读"


def test_list_documents_uses_stem_when_no_h1(outputs):
    _write(outputs, "2026-10-10", "no-title.md", "## 一、项目基础大白话介绍\n\n内容\n")
    assert ds.list_documents()[0]["title"] == "no-title"


def test_list_documents_empty_when_dir_missing(outputs):
    assert ds.list_documents() == []


# ---------------- 详情 ----------------

def test_load_document_returns_full_structure(outputs):
    _write(outputs, "2026-10-10", "a.md", _DOC)
    doc = ds.load_document("2026-10-10", "a.md")

    assert doc is not None
    assert doc["doc_id"] == "2026-10-10/a.md"
    assert doc["title"] == "a/b 新手解读"
    assert doc["meta"]["项目类型"] == "工具 / 应用"
    assert len(doc["modules"]) == 3
    assert doc["markdown"] == _DOC


def test_load_document_returns_none_for_missing(outputs):
    assert ds.load_document("2026-10-10", "nope.md") is None


def test_load_document_rejects_path_traversal(outputs):
    _write(outputs, "2026-10-10", "a.md", _DOC)
    assert ds.load_document("2026-10-10", "../a.md") is None
    assert ds.load_document("../../etc", "passwd.md") is None
    assert ds.load_document("bad-date", "a.md") is None


def test_is_valid_date():
    assert ds.is_valid_date("2026-10-10")
    assert not ds.is_valid_date("2026-1-1")
    assert not ds.is_valid_date("")
    assert not ds.is_valid_date(None)


# ---------------- 统计 ----------------

def test_stats_aggregates_by_date(outputs):
    _write(outputs, "2026-10-09", "a.md", _DOC)
    _write(outputs, "2026-10-09", "b.md", _DOC)
    _write(outputs, "2026-10-10", "c.md", _DOC)

    stats = ds.stats()
    assert stats["total_documents"] == 3
    assert stats["total_dates"] == 2
    assert stats["latest_date"] == "2026-10-10"
    assert {d["date"]: d["count"] for d in stats["dates"]} == {"2026-10-09": 2, "2026-10-10": 1}


def test_stats_empty(outputs):
    stats = ds.stats()
    assert stats["total_documents"] == 0
    assert stats["latest_date"] is None


def test_snippet_truncates_long_context():
    text = "x" * 500 + "关键词" + "y" * 500
    snippet = ds._snippet(text, "关键词")
    assert snippet.startswith("…") and snippet.endswith("…")
    assert "关键词" in snippet


def test_snippet_returns_empty_when_not_found():
    assert ds._snippet("abc", "zzz") == ""
