"""维度打标（app/classify.py，design.md §16.4 / Req13）。"""
from app import classify


def test_word_boundary_avoids_false_positive():
    """回归：早期子串匹配让「rest」命中「interesting」，把资料仓库误判为后端项目。"""
    d = classify.classify(
        "sindresorhus/awesome",
        "Awesome lists about all kinds of interesting topics",
        ["awesome", "list"],
        "Markdown",
    )
    assert d["highlight"] == "待进一步了解"
    assert d["deployable"] == "no"


def test_deployable_yes_with_tree():
    d = classify.classify("ollama/ollama", "Get up and running", ["llm"], "Go",
                          tree=["go.mod", "Dockerfile", "main.go", "README.md"])
    assert d["deployable"] == "yes"
    assert "go.mod" in d["reasons"]["deployable"][0]


def test_deployable_no_with_tree_when_no_artifacts():
    d = classify.classify("sindresorhus/awesome", "Awesome lists", ["awesome"], "Markdown",
                          tree=["readme.md", "contributing.md"])
    assert d["deployable"] == "no"


def test_tree_artifact_reason_prefers_root():
    """判定理由优先展示根目录的依赖文件。"""
    d = classify.classify("a/b", "x", [], "JavaScript",
                          tree=["deep/nested/package.json", "package.json", "src/index.js"])
    reason = d["reasons"]["deployable"][0]
    assert reason.index("package.json") < reason.index("deep/nested/package.json") or \
        "deep/nested" not in reason


def test_practical_tool_yes():
    d = classify.classify("jqlang/jq", "Command-line JSON processor", ["cli", "json"], "C")
    assert d["practical_tool"] == "yes"
    assert d["deployable"] == "yes"


def test_practical_tool_no_for_resource():
    d = classify.classify("x/awesome-tools", "Awesome list of tools", ["awesome"], "Markdown")
    assert d["practical_tool"] == "no"


def test_playfulness_high_for_ai():
    d = classify.classify("2noise/ChatTTS", "A generative speech model", ["ai", "tts"], "Python")
    assert d["playfulness"] == "high"


def test_playfulness_medium_for_cli():
    d = classify.classify("jqlang/jq", "Command-line JSON processor", ["cli"], "C")
    assert d["playfulness"] == "medium"


def test_learnable_maps_language_and_type():
    d = classify.classify("vercel/next.js", "The React Framework", ["framework"], "JavaScript")
    assert "JavaScript" in d["learnable"] or "JS" in d["learnable"]
    assert d["project_type"] in ("framework", "tool")


def test_learnable_falls_back_for_resource_repo():
    """资料类仓库无对应技术点映射时，回退为「待深入解析后给出」（Req13.4）。"""
    d = classify.classify("x/awesome-list", "Awesome list of things", ["awesome"], None)
    assert d["project_type"] == "resource"
    assert d["learnable"] == "待深入解析后给出"


def test_reasons_always_present():
    """Req13.2：每个维度都要给出判定理由。"""
    d = classify.classify("a/b", "test project", ["tool"], "Python")
    for key in ("deployable", "playfulness", "practical_tool", "highlight", "learnable"):
        assert key in d["reasons"]
        assert isinstance(d["reasons"][key], list)
