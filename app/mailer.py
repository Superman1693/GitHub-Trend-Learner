"""邮件投递（design.md §12）：SMTP 发送（重试 ≤3）+ outputs/YYYY-MM-DD/ 归档兜底（Req1.9）。

SMTP 未配置时降级为「仅归档 + 控制台提示手动取用」，保证内容不丢失。
"""
from __future__ import annotations

import smtplib
import time
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from . import log
from .config import Settings
from .fsutil import atomic_write_text


def archive(outputs_dir: Path, date_str: str, filename: str, content: str) -> Path:
    path = Path(outputs_dir) / date_str / filename
    atomic_write_text(path, content)
    return path


def send_or_archive(settings: Settings, subject: str, body_markdown: str,
                    attachment_path: Path) -> dict:
    """发送邮件；失败重试 ≤3 次，仍失败保留归档并返回状态（design.md §12.3）。"""
    result = {"delivered": False, "attempts": 0, "archive": str(attachment_path), "error": ""}

    if not settings.smtp_ready:
        result["error"] = "SMTP 未配置（SMTP_HOST/MAIL_FROM/MAIL_TO），已降级为仅归档"
        log.console(f"  [邮件] {result['error']}：{attachment_path}")
        return result

    msg = MIMEMultipart()
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = settings.mail_from
    msg["To"] = ", ".join(settings.mail_to)
    msg.attach(MIMEText(body_markdown, "plain", "utf-8"))
    data = Path(attachment_path).read_bytes()
    attach = MIMEApplication(data)
    # RFC 2231 元组形式，正确处理中文附件名
    attach.add_header("Content-Disposition", "attachment",
                      filename=("utf-8", "", Path(attachment_path).name))
    msg.attach(attach)

    last_err: Exception | None = None
    # 首次发送 + 重试 ≤3（Req1.9：重试不超过 3 次）
    for attempt in range(1, 2 + settings.max_retries):
        result["attempts"] = attempt
        try:
            if settings.smtp_port == 465:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
                server.starttls()
            with server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password or "")
                server.sendmail(settings.mail_from, settings.mail_to, msg.as_string())
            result["delivered"] = True
            log.console(f"  [邮件] 已投递给 {len(settings.mail_to)} 位收件人（第 {attempt} 次尝试）")
            return result
        except Exception as exc:
            last_err = exc
            log.console(f"  [邮件] 第 {attempt} 次发送失败：{exc}")
            time.sleep(min(2 ** attempt, 10))
    result["error"] = f"发送重试后仍失败：{last_err}；内容已归档 {attachment_path}"
    return result
