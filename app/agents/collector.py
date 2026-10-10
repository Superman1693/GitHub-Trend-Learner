"""TrendCollectorAgent（agent/TrendCollectorAgent.md）：只采集，不解读。

- 链接校验：合法正则 + 深链接截取（/tree/…、/issues/… 等先取 owner/repo 前缀）。
- 404 语义：未授权状态下无法区分「不存在」与「私有」，不得断言（Req2.4、约束 C3）。
- 组装 RepoMeta（design.md §5.2）；核心文件筛选与上下文裁剪在此完成（§5.6、§8.3）。
- collect_from_info 支持调用方传入已取到的仓库元信息与 head_sha，避免重复请求（§8.1 只抓取一次）。
"""
from __future__ import annotations

import re
from datetime import datetime

from ..contracts import RepoMeta
from ..github_client import GitHubClient
from .. import log
from ..selection import aggregate_tree, select_core_files, trim_readme

URL_RE = re.compile(r"^https?://(www\.)?github\.com/([\w.-]+)/([\w.-]+)/?$")
DEEP_URL_RE = re.compile(
    r"^https?://(www\.)?github\.com/([\w.-]+)/([\w.-]+)"
    r"(/(tree|blob|issues|pull|releases|actions|projects|wiki|discussions|commits)?/?)*"
    r"[?#]?.*$"
)
NAME_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

# DeployAgent §2 输入契约要求的「依赖文件、启动脚本、配置项」清单
MANIFEST_NAMES = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    "package.json", "package-lock.json", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "Dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "environment.yml", ".env.example",
}
DEPLOY_HINTS_MAX = 6
DEPLOY_HINT_LINES = 100


class InvalidURL(Exception):
    """输入不是合法 GitHub 仓库定位（Req2.3）。"""


def resolve_full_name(user_input: str) -> str:
    """把用户输入解析为 owner/repo；支持完整 URL、深链接、裸 owner/repo（容忍尾部斜杠）。"""
    text = user_input.strip().rstrip("/")
    m = URL_RE.match(text)
    if m:
        return f"{m.group(2)}/{m.group(3)}"
    if re.match(r"^https?://(www\.)?github\.com/", text):
        m = DEEP_URL_RE.match(text)
        if m:
            return f"{m.group(2)}/{m.group(3)}"
        raise InvalidURL(text)
    if NAME_RE.match(text):
        return text
    raise InvalidURL(text)


def collect(client: GitHubClient, user_input: str, source: str = "search_api") -> RepoMeta:
    """采集单个仓库：解析输入 → 元信息 → RepoMeta。"""
    full_name = resolve_full_name(user_input)
    repo_info = client.get_repo(full_name)
    return collect_from_info(client, repo_info, source=source)


def collect_from_info(client: GitHubClient, repo_info: dict,
                      source: str = "search_api", head_sha: str | None = None) -> RepoMeta:
    """从 get_repo 产出组装 RepoMeta。

    head_sha 由调用方传入可省一次 API 请求（design.md §8.1 只抓取一次、§8.2 缓存键）。
    """
    full_name = repo_info["full_name"]
    log.console(f"  [采集] {full_name}")
    ref = repo_info.get("default_branch") or "main"
    if head_sha is None:
        head_sha = _head_sha(client, full_name, ref)

    license_name = None
    lic = repo_info.get("license") or {}
    if lic.get("spdx_id") and lic["spdx_id"] != "NOASSERTION":
        license_name = lic["spdx_id"]

    readme_raw = client.get_readme(full_name)
    readme, readme_trimmed = trim_readme(readme_raw)
    tree, tree_truncated = client.get_tree(full_name, ref)

    core_files, file_reason = select_core_files(
        tree,
        readme,
        fetch_file=lambda path: client.get_file(full_name, path, ref),
    )
    deploy_hints = _collect_deploy_hints(client, full_name, tree, ref)

    degrade_reasons = []
    if not readme_raw.strip():
        # 无 README 是常见情况（尤其个人小仓库），必须作为降级原因显式告知，
        # 而不是让上层误判为「仓库不存在/私有」（v1.8 修复）
        degrade_reasons.append("仓库未提供 README，分析依据仅为目录树与核心文件")
    if tree_truncated:
        degrade_reasons.append("仓库目录树过大被 GitHub 截断")
    if file_reason:
        degrade_reasons.append(file_reason)
    tree_shown, aggregated = aggregate_tree(tree)
    if aggregated:
        degrade_reasons.append("目录树超过 500 条已按目录聚合")
    reasons_text = "；".join(degrade_reasons)
    if readme_trimmed:
        reasons_text = (reasons_text + "；" if reasons_text else "") + "README 超长已按章节摘要"

    return RepoMeta(
        full_name=full_name,
        html_url=repo_info["html_url"],
        description=repo_info.get("description"),
        stars=repo_info.get("stargazers_count", 0),
        forks=repo_info.get("forks_count", 0),
        language=repo_info.get("language"),
        license=license_name,
        topics=repo_info.get("topics", []),
        default_branch=ref,
        head_sha=head_sha,
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        source=source,
        readme=readme,
        tree=tree_shown,
        core_files=core_files,
        degraded=bool(degrade_reasons) or readme_trimmed,
        degrade_reason=reasons_text,
        deploy_hints=deploy_hints,
    )


def _collect_deploy_hints(client: GitHubClient, full_name: str, tree_paths: list[str],
                          ref: str, max_files: int = DEPLOY_HINTS_MAX,
                          max_lines: int = DEPLOY_HINT_LINES) -> list[dict]:
    """采集依赖文件/启动脚本/配置项（DeployAgent §2 输入），单文件截断 100 行。"""
    hints: list[dict] = []
    for path in tree_paths:
        if len(hints) >= max_files:
            break
        if path.rsplit("/", 1)[-1] not in MANIFEST_NAMES:
            continue
        try:
            content = client.get_file(full_name, path, ref)
        except Exception:
            continue
        lines = content.splitlines()
        if len(lines) > max_lines:
            content = "\n".join(lines[:max_lines]) + f"\n…（截断，原 {len(lines)} 行）"
        hints.append({"path": path, "content": content})
    return hints


def _head_sha(client: GitHubClient, full_name: str, ref: str) -> str:
    """取分支头提交 sha（缓存键用，design.md §8.2）。"""
    return client.get_branch_sha(full_name, ref)
