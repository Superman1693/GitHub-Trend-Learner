"""文档全文检索（v1.8，CODE_REVIEW.md F5）测试。

此前只按文件名/标题匹配，正文关键词搜不到。测试通过临时 outputs 目录隔离。
"""
from __future__ import annotations

import pytest

from server.services import document_service


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    """把 OUTPUTS_DIR 指向临时目录，构造 2 份文档。"""
    day = tmp_path / "2026-10-10"
    day.mkdir(parents=True)
    (day / "alpha.md").write_text(
        "# alpha/tool 新手解读\n\n## 一、项目基础大白话介绍\n\n这是一个虚拟环境管理工具。\n"
        "## 五、本地一键部署完整方案\n\n先创建虚拟环境，再执行部署。\n",
        encoding="utf-8",
    )
    (day / "beta.md").write_text(
        "# beta/lib 新手解读\n\n## 一、项目基础大白话介绍\n\n纯计算库，无部署步骤。\n",
        encoding="utf-8",
    )
    # 文件名与正文不重合，用于验证「仅命中文件名」的分支
    (day / "delta_odd.md").write_text(
        "# 另一个项目 新手解读\n\n## 一、项目基础大白话介绍\n\n与关键词无关的正文。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(document_service, "OUTPUTS_DIR", tmp_path)
    return tmp_path


def test_search_matches_body_not_only_title(outputs):
    hits = document_service.search_documents("虚拟环境")
    names = [h["name"] for h in hits]
    assert names == ["alpha.md"], "应命中正文内容，而非只看文件名/标题"


def test_search_returns_snippet_and_count(outputs):
    hit = document_service.search_documents("部署")[0]
    assert hit["match_count"] == 2          # 标题「本地一键部署完整方案」+ 正文
    assert "部署" in hit["snippet"]
    assert hit["snippet"].startswith("…") or hit["snippet"].endswith("…")


def test_search_matches_title_even_without_body_hit(outputs):
    """命中只来自文件名时，也应返回结果并标注 matched_in。"""
    hits = document_service.search_documents("delta_odd")
    assert [h["name"] for h in hits] == ["delta_odd.md"]
    assert hits[0]["match_count"] == 0, "正文不含该词，命中次数应为 0"
    assert "标题" in hits[0]["matched_in"]


def test_search_title_and_body_hit_is_counted(outputs):
    """标题行本身也是正文的一部分，命中次数应包含它。"""
    hit = document_service.search_documents("beta/lib")[0]
    assert hit["match_count"] >= 1
    assert "正文" in hit["matched_in"]


def test_search_is_case_insensitive(outputs):
    assert document_service.search_documents("ALPHA")[0]["name"] == "alpha.md"


def test_search_ranks_by_match_count(outputs):
    hits = document_service.search_documents("虚拟环境")
    assert len(hits) == 1

    many = document_service.search_documents("a")   # alpha 命中远多于 beta
    assert many[0]["name"] == "alpha.md"


def test_search_empty_query_returns_nothing(outputs):
    assert document_service.search_documents("") == []
    assert document_service.search_documents("   ") == []


def test_search_no_match(outputs):
    assert document_service.search_documents("绝不存在的关键词zzz") == []


def test_search_respects_limit(outputs):
    assert len(document_service.search_documents("a", limit=1)) == 1
