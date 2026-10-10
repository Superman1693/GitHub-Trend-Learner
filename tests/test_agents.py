"""采集器组装逻辑（FakeClient，离线）。"""
from app.agents.collector import collect_from_info, resolve_full_name

REPO_INFO = {
    "full_name": "acme/widget",
    "html_url": "https://github.com/acme/widget",
    "description": "A widget",
    "stargazers_count": 42,
    "forks_count": 3,
    "language": "Python",
    "license": {"spdx_id": "MIT"},
    "topics": ["cli"],
    "default_branch": "main",
}

FILES = {
    "requirements.txt": "requests>=2.28\n",
    "package.json": "{\n  \"name\": \"widget\"\n}\n",
    "src/main.py": "print('main')\n" * 5,
}


class FakeClient:
    def get_readme(self, full_name):
        return "# Widget\n\n用法见 `src/main.py`。"

    def get_tree(self, full_name, branch):
        return ["src/main.py", "requirements.txt", "package.json", "README.md"], False

    def get_file(self, full_name, path, ref):
        return FILES[path]


def test_collect_from_info_builds_repometa():
    meta = collect_from_info(FakeClient(), REPO_INFO, source="trending_page",
                             head_sha="abc123")
    assert meta.full_name == "acme/widget"
    assert meta.license == "MIT"
    assert meta.head_sha == "abc123"          # 调用方传入，不额外请求
    assert meta.source == "trending_page"
    assert meta.degraded is False


def test_collect_deploy_hints():
    """DeployAgent §2：依赖文件/配置项必须进入 RepoMeta.deploy_hints（第三轮缺陷 #3 回归）。"""
    meta = collect_from_info(FakeClient(), REPO_INFO, head_sha="abc123")
    hint_paths = {h["path"] for h in meta.deploy_hints}
    assert "requirements.txt" in hint_paths
    assert "package.json" in hint_paths


def test_core_files_excludes_manifests():
    """requirements.txt/package.json 是依赖清单，不进入 M4 源码分析（§5.6）。"""
    meta = collect_from_info(FakeClient(), REPO_INFO, head_sha="abc123")
    core_paths = [f["path"] for f in meta.core_files]
    assert core_paths == ["src/main.py"]


def test_resolve_trailing_slash():
    """尾部斜杠容错（第三轮缺陷 #9 回归）。"""
    assert resolve_full_name("psf/requests/") == "psf/requests"
    assert resolve_full_name("https://github.com/psf/requests/") == "psf/requests"
