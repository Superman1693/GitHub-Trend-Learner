"""核心文件筛选（design.md §5.6）与上下文裁剪（§8.3）。"""
from app.selection import (aggregate_tree, select_core_files, trim_readme,
                           MAX_FILE_LINES)

TREE = [
    "README.md",
    "src/main.py",
    "src/utils/helper.py",
    "lib/engine.py",
    "tests/test_main.py",
    "docs/guide.md",
    "assets/logo.png",
    "setup.py",
    "random_notes.txt",
]
README = "用法见 `src/main.py`，入口文件。"


def test_scoring_prefers_core_dirs_and_keywords():
    files, _ = select_core_files(TREE, README, fetch_file=lambda p: "print('x')\n")
    picked = [f["path"] for f in files]
    assert "src/main.py" in picked
    assert "lib/engine.py" in picked
    assert "tests/test_main.py" not in picked
    assert "docs/guide.md" not in picked
    assert "assets/logo.png" not in picked
    assert picked[0] == "src/main.py"  # README 提及 + main 关键词 + src 目录，应排第一


def test_file_truncation_300_lines():
    big = "\n".join(f"line{i}" for i in range(500))
    files, _ = select_core_files(["src/main.py"], README, fetch_file=lambda p: big)
    content = files[0]["content"]
    assert content.count("\n") == MAX_FILE_LINES  # 300 行 + 1 行截断说明


def test_max_files_limit():
    tree = [f"src/mod{i}.py" for i in range(30)]
    files, _ = select_core_files(tree, README, fetch_file=lambda p: "x")
    assert len(files) <= 10  # global.md §8.2


def test_trim_readme_long():
    readme = "# Title\n\n" + ("段落内容。\n\n" * 3000)
    trimmed, flag = trim_readme(readme)
    assert flag is True
    assert len(trimmed) < len(readme)
    short, flag2 = trim_readme("短 README")
    assert flag2 is False and short == "短 README"


def test_trim_readme_keeps_intro_paragraph():
    intro = "这是一个导语段：项目是干什么的，放在所有标题之前，必须保留。"
    readme = intro + "\n\n# 安装\n\n" + ("很长的安装说明。\n\n" * 3000)
    trimmed, _ = trim_readme(readme)
    assert intro in trimmed          # 导语段不丢
    assert "# 安装" in trimmed       # 标题保留


def test_trim_readme_keeps_first_section_paragraph():
    readme = "# 标题\n\n第一段要点。\n第二段会被省略。\n\n# 另一章\n\n另一段。\n" + ("填充。\n\n" * 6000)
    trimmed, _ = trim_readme(readme)
    assert "第一段要点。" in trimmed
    assert "第二段会被省略" not in trimmed  # 每个标题下只保留首段（§8.3）
    assert "另一段。" in trimmed


def test_aggregate_tree():
    paths = [f"pkg{i}/file{j}.py" for i in range(30) for j in range(20)]  # 600 条
    agg, flag = aggregate_tree(paths)
    assert flag is True
    assert len(agg) < 100
    assert any("已聚合" in p for p in agg)
