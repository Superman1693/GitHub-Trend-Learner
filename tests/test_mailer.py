"""邮件投递（app/mailer.py）测试。

此前覆盖率仅 25%：归档落盘、SMTP 未配置降级、发送重试这些分支都没测。
发送重试次数写错会导致「明明没发出去却报告成功」，所以必须覆盖。

用假的 smtplib 驱动，不触网、不真实等待。
"""
from __future__ import annotations

import smtplib

import pytest

from app import mailer
from app.config import Settings


def _settings(**kw) -> Settings:
    base = dict(
        github_token=None, llm_base_url=None, llm_api_key=None, llm_model=None,
        smtp_host=None, smtp_port=465, smtp_user=None, smtp_password=None,
        mail_from=None, mail_to=[], trending_top_n=10, candidate_pool_size=60,
        concurrency=3, max_retries=3, max_gate_returns=2,
    )
    base.update(kw)
    return Settings(**base)


_SMTP_READY = dict(smtp_host="smtp.example.com", smtp_port=465,
                   smtp_user="u@example.com", smtp_password="p",
                   mail_from="u@example.com", mail_to=["a@example.com"])


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(mailer.time, "sleep", lambda *_: None)


# ---------------- 归档 ----------------

def test_archive_creates_dir_and_file(tmp_path):
    path = mailer.archive(tmp_path, "2026-10-10", "a.md", "# 标题\n正文")
    assert path == tmp_path / "2026-10-10" / "a.md"
    assert path.read_text(encoding="utf-8") == "# 标题\n正文"


def test_archive_overwrites_atomically(tmp_path):
    mailer.archive(tmp_path, "2026-10-10", "a.md", "旧")
    path = mailer.archive(tmp_path, "2026-10-10", "a.md", "新")
    assert path.read_text(encoding="utf-8") == "新"
    assert not list(path.parent.glob("*.tmp")), "不应残留临时文件"


# ---------------- SMTP 未配置：降级为仅归档 ----------------

def test_not_configured_falls_back_to_archive(tmp_path):
    target = tmp_path / "x.md"
    target.write_text("内容", encoding="utf-8")
    result = mailer.send_or_archive(_settings(), "主题", "正文", target)

    assert result["delivered"] is False
    assert result["attempts"] == 0
    assert "未配置" in result["error"]
    assert result["archive"] == str(target)


# ---------------- 发送成功 ----------------

def test_send_success_with_ssl(monkeypatch, tmp_path):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"], sent["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            sent["login"] = (user, password)

        def sendmail(self, frm, to, msg):
            sent["envelope"] = (frm, list(to))

    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    target = tmp_path / "x.md"
    target.write_text("内容", encoding="utf-8")

    result = mailer.send_or_archive(_settings(**_SMTP_READY), "主题", "正文", target)

    assert result["delivered"] is True
    assert result["attempts"] == 1
    assert sent["host"] == "smtp.example.com" and sent["port"] == 465
    assert sent["login"] == ("u@example.com", "p")
    assert sent["envelope"][0] == "u@example.com"


def test_send_uses_starttls_on_non_465_port(monkeypatch, tmp_path):
    calls = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls["port"] = port

        def starttls(self):
            calls["starttls"] = True

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            pass

        def sendmail(self, *a):
            pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    target = tmp_path / "x.md"
    target.write_text("内容", encoding="utf-8")

    result = mailer.send_or_archive(
        _settings(**{**_SMTP_READY, "smtp_port": 587}), "主题", "正文", target)

    assert result["delivered"] is True
    assert calls == {"port": 587, "starttls": True}


def test_send_skips_login_without_user(monkeypatch, tmp_path):
    logged = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            logged.append(u)

        def sendmail(self, *a):
            pass

    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    target = tmp_path / "x.md"
    target.write_text("内容", encoding="utf-8")

    mailer.send_or_archive(
        _settings(**{**_SMTP_READY, "smtp_user": None}), "主题", "正文", target)
    assert logged == [], "未配置用户时不应尝试登录"


# ---------------- 发送失败与重试 ----------------

def test_send_retries_then_succeeds(monkeypatch, tmp_path):
    attempts = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            attempts.append(1)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            pass

        def sendmail(self, *a):
            if len(attempts) < 2:
                raise smtplib.SMTPException("temporary failure")

    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    target = tmp_path / "x.md"
    target.write_text("内容", encoding="utf-8")

    result = mailer.send_or_archive(_settings(**_SMTP_READY), "主题", "正文", target)

    assert result["delivered"] is True
    assert result["attempts"] == 2


def test_send_gives_up_after_max_retries_and_reports_archive(monkeypatch, tmp_path):
    """重试耗尽必须如实报告失败并给出归档路径，不能假装成功。"""
    attempts = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            attempts.append(1)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            pass

        def sendmail(self, *a):
            raise smtplib.SMTPException("permanent failure")

    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    target = tmp_path / "x.md"
    target.write_text("内容", encoding="utf-8")

    result = mailer.send_or_archive(_settings(**_SMTP_READY), "主题", "正文", target)

    assert result["delivered"] is False
    assert result["attempts"] == 1 + 3, "首次 + max_retries(3) 次重试"
    assert "仍失败" in result["error"]
    assert str(target) in result["error"]


def test_attachment_uses_rfc2231_filename(monkeypatch, tmp_path):
    """中文附件名必须用 RFC 2231 元组形式，否则收件端乱码。"""
    captured = {}

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            pass

        def sendmail(self, frm, to, msg):
            captured["msg"] = msg

    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTP)
    target = tmp_path / "中文报告.md"
    target.write_text("内容", encoding="utf-8")

    mailer.send_or_archive(_settings(**_SMTP_READY), "主题", "正文", target)

    assert "filename*=utf-8''" in captured["msg"].lower().replace('"', "'")
