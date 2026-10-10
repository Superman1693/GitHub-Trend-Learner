"""输出组装（templates 口径）：六模块文档 + 邮件正文 + 摘要抽取。"""
from app.contracts import FinalDoc, RepoMeta
from app.render import extract_digest, render_email_body, render_final_doc


def _meta() -> RepoMeta:
    return RepoMeta(
        full_name="psf/requests", html_url="https://github.com/psf/requests",
        description="HTTP library", stars=52000, forks=9000, language="Python",
        license="Apache-2.0", topics=["http"], default_branch="main",
        head_sha="abc", fetched_at="2026-09-27 10:00", source="trending_page",
        readme="", tree=[], core_files=[], degraded=False, degrade_reason="",
    )


def _final() -> FinalDoc:
    modules = {
        "intro": "### 一句话说明它是干嘛的\n一个让人人都能轻松发 HTTP 请求的 Python 库。\n",
        "principle": "它就像自动售货机：你投币（发请求），它出货（返回响应）。\n",
        "tutorial": "### 极简版：3 分钟上手\n1. 安装 requests\n2. 写三行代码发请求\n3. 查看返回内容\n",
        "source-code": "核心文件 `src/main.py`。\n",
        "deploy": "### 环境准备\n安装 Python 3.10 以上版本即可开始。\n",
        "growth": "先跑起来，再改配置。\n",
        "_project_type": "tool",
    }
    return FinalDoc(task_id="t1", repo_full_name="psf/requests",
                    generated_at="2026-09-27 10:00", modules=modules,
                    gate_result="pass", rejected_items=[], glossary=[])


def test_render_contains_six_standard_titles():
    doc = render_final_doc(_meta(), _final())
    for title in ("一、项目基础大白话介绍", "二、零基础通俗原理讲解", "三、新手入门使用教程",
                  "四、源码核心逻辑通俗分析", "五、本地一键部署完整方案",
                  "六、新手学习提升指南"):
        assert title in doc  # global.md §2.1 标准命名
    assert "数据来源：主方案 trending 页面" in doc  # Req1.6 来源标注
    assert "部署与使用常见报错大全" not in doc  # v1.5：报错大全已删除


def test_render_marks_degraded():
    meta = _meta()
    meta.degraded = True
    meta.degrade_reason = "目录树过大"
    f = _final()
    f.gate_result = "degraded"
    f.rejected_items = [{"module": "deploy", "check": "V7", "issue": "缺 macOS"}]
    doc = render_final_doc(meta, f)
    assert "降级解析" in doc and "降级交付" in doc


def test_extract_digest():
    d = extract_digest(_final().modules)
    assert "HTTP 请求" in d["one_liner"]
    assert "自动售货机" in d["analogy"]
    assert d["quick_steps"] == ["安装 requests", "写三行代码发请求", "查看返回内容"]


def test_email_body_structure():
    top = [{"full_name": "psf/requests", "stars": 52000, "language": "Python",
            "html_url": "https://github.com/psf/requests", **extract_digest(_final().modules)}]
    body = render_email_body("2026-09-27", "trending_page",
                             "今日热门以 Python 为主。", top,
                             [{"full_name": "a/b", "language": "Go", "description": "工具"}],
                             ["ℹ️ 今日热门榜单为主数据源不可用，已降级使用 Search API，榜单口径可能与官方 trending 略有差异。"])
    assert "GitHub 今日热点解读 · 2026-09-27" in body
    assert "今日精选（Top 3 要点速览）" in body  # v1.3 口径：正文放要点速览
    assert "其余热门项目（速览）" in body
    assert "已降级使用 Search API" in body  # 降级标注（Req1.6）
