# pytest 根目录标记：保证 `import app` 可用
import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_dirs(tmp_path, monkeypatch):
    """测试不得污染真实 `logs/` 与 `cache/`。

    此前 `_stage_retry` 等被测代码会经 `app.log.event` 写入
    `logs/run-YYYYMMDD.jsonl`，把单元测试的事件混进真实运行日志。
    """
    from app import log
    from app.config import Settings

    monkeypatch.setattr(log, "LOGS_DIR", tmp_path / "logs")
    # Settings.load() 有进程内缓存（v1.8.2），每个测试前清空，
    # 保证 monkeypatch.setenv 的结果一定被读到
    Settings.invalidate()
    yield
    Settings.invalidate()
