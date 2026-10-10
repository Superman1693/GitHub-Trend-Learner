"""数据契约：merge_modules 防 LLM 局部输出丢内容。"""
from app.contracts import merge_modules


def test_new_overwrites_nonempty():
    base = {"intro": "旧", "growth": "g"}
    out = merge_modules(base, {"intro": "新"})
    assert out["intro"] == "新" and out["growth"] == "g"


def test_empty_string_keeps_base():
    base = {"intro": "旧"}
    out = merge_modules(base, {"intro": "", "growth": "新"})
    assert out["intro"] == "旧" and out["growth"] == "新"


def test_none_and_non_string_ignored():
    base = {"intro": "旧"}
    assert merge_modules(base, None) == base
    out = merge_modules(base, {"intro": None, "x": 123})
    assert out["intro"] == "旧" and "x" not in out


def test_partial_repair_does_not_lose_modules():
    """修复轮 LLM 只返回 1 个模块时，其余模块必须保留（第三轮缺陷 #2 回归）。"""
    base = {"intro": "A", "principle": "B", "tutorial": "C", "source-code": "D",
            "deploy": "E", "growth": "G"}
    out = merge_modules(base, {"deploy": "E-fixed"})
    assert set(out) == set(base)  # 六模块一个不丢
    assert out["deploy"] == "E-fixed"
    assert out["intro"] == "A"


def test_modules_order_is_six():
    """v1.5：模块口径为六模块，报错大全已删除，学习指南前移为 M6。"""
    from app.contracts import MODULE_KEYS, MODULES_ORDER

    assert MODULE_KEYS == ["intro", "principle", "tutorial", "source-code", "deploy", "growth"]
    assert MODULES_ORDER[-1] == ("growth", "六、新手学习提升指南")
    assert all(key != "errors" for key, _ in MODULES_ORDER)


def test_modes_exclude_error_fix():
    """v1.5：error_fix 路由模式已随 Req5 删除。"""
    from app.contracts import MODES

    assert MODES == ("daily_trend", "custom_repo")
    assert "error_fix" not in MODES


def test_draft_doc_requires_six_modules():
    """DraftDoc 缺任一模块键即交接违约。"""
    import pytest

    from app.contracts import DraftDoc

    with pytest.raises(ValueError):
        DraftDoc(project_type="tool", modules={"intro": "a"})


def test_deploy_plan_has_run_check_no_m6():
    """v1.5：DeployPlan 去掉 error_kb_hits / m6_markdown，新增 run_check。"""
    import dataclasses

    from app.contracts import DeployPlan

    names = {f.name for f in dataclasses.fields(DeployPlan)}
    assert "run_check" in names
    assert "error_kb_hits" not in names
    assert "m6_markdown" not in names
