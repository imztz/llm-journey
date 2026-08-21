#!/usr/bin/env python3
"""README 动态片段自动更新。

由 .github/workflows/update-readme.yml 每日调用,也可本地手动运行:
    python scripts/update_readme.py

更新三处(由 README 中的 HTML 注释标记划定,标记外的内容绝不触碰):
  AUTO:STATUS    Status 徽章 —— 按 scripts/status.json 的阶段日期表推断;
                 override_status 非 null 时优先使用(手动覆盖)
  AUTO:DAY       尾部 Day X of N 计数器 —— (今天 - start) + 1
  AUTO:PROGRESS  进度徽章 —— GitHub REST API 统计 commits 数、填充 Actions
                 徽章的真实仓库地址(需要 GITHUB_REPOSITORY 环境变量;
                 本地无 token 时自动跳过,只更新前两项)

日期一律按北京时间计算(Actions runner 是 UTC)。
"""

import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
README_PATH = os.path.join(REPO_ROOT, "README.md")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "status.json")

BEIJING = timezone(timedelta(hours=8))
WORKFLOW_FILE = "update-readme"


def today_cn() -> date:
    return datetime.now(BEIJING).date()


def d(iso: str) -> date:
    return date.fromisoformat(iso)


def replace_block(text: str, marker: str, content: str):
    """把 <!-- AUTO:{marker}:START --> ... <!-- AUTO:{marker}:END --> 之间
    (含标记行)替换为新内容。找不到标记时原样返回并提示。"""
    start = f"<!-- AUTO:{marker}:START -->"
    end = f"<!-- AUTO:{marker}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        print(f"[warn] README 中未找到 {marker} 标记,跳过该项")
        return text, False
    new = f"{start}\n{content}\n{end}"
    return pattern.sub(lambda _: new, text), True


def current_phase(cfg: dict, today: date):
    """返回 (状态文本, 徽章颜色)。override 优先;否则按日期表推断。"""
    if cfg.get("override_status"):
        return str(cfg["override_status"]), "orange"

    if today > d(cfg["end"]):
        return "Journey Complete 🎉", "brightgreen"
    if today < d(cfg["start"]):
        return "Not Started", "lightgrey"

    fallback = None
    for ph in cfg["phases"]:
        if d(ph["from"]) <= today <= d(ph["to"]):
            return ph["name"], ph.get("color", "blue")
        if d(ph["from"]) <= today:
            fallback = ph  # 落在两个阶段的缝隙里时,沿用上一个阶段
    if fallback:
        return fallback["name"], fallback.get("color", "blue")
    return cfg["phases"][0]["name"], cfg["phases"][0].get("color", "blue")


def count_commits(slug: str, token: str | None):
    """通过 Link header 分页技巧统计默认分支总 commit 数。失败返回 None。"""
    url = f"https://api.github.com/repos/{slug}/commits?per_page=1"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            link = resp.headers.get("Link", "")
    except Exception as exc:  # 网络问题不该让整个更新失败
        print(f"[warn] commits 统计失败({exc}),进度徽章保持原样")
        return None
    m = re.search(r'[?&]page=(\d+)>; rel="last"', link)
    return int(m.group(1)) if m else 1


def main() -> int:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(README_PATH, encoding="utf-8") as f:
        readme = f.read()

    original = readme
    today = today_cn()
    start, end = d(cfg["start"]), d(cfg["end"])

    # --- Day X of N ---
    day = (today - start).days + 1
    total = (end - start).days
    day = max(1, min(day, total))
    day_line = f"**{start:%Y.%m} → {end:%Y.%m} · Day {day} of {total}**"
    readme, _ = replace_block(readme, "DAY", day_line)
    print(f"[day]   {day_line}")

    # --- Status 徽章 ---
    status, color = current_phase(cfg, today)
    badge = (
        f"[![Status](https://img.shields.io/badge/Status-{quote(status)}"
        f"-{color}?style=flat-square)]()"
    )
    readme, _ = replace_block(readme, "STATUS", badge)
    print(f"[status] {status} ({color})")

    # --- 进度徽章(仅在 Actions 环境或有仓库信息时) ---
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        commits = count_commits(slug, os.environ.get("GH_TOKEN"))
        lines = [
            f"[![README Automation](https://github.com/{slug}/actions/workflows/"
            f"{WORKFLOW_FILE}.yml/badge.svg)]"
            f"(https://github.com/{slug}/actions/workflows/{WORKFLOW_FILE}.yml)",
        ]
        if commits is not None:
            lines.append(
                f"[![Commits](https://img.shields.io/badge/Commits-{commits}"
                f"-1e88e5?style=flat-square)](https://github.com/{slug}/commits)"
            )
        readme, _ = replace_block(readme, "PROGRESS", "\n".join(lines))
        print(f"[prog]  repo={slug} commits={commits}")
    else:
        print("[prog]  本地运行(无 GITHUB_REPOSITORY),进度徽章保持原样")

    if readme != original:
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write(readme)
        print("README 已更新")
    else:
        print("README 无变化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
