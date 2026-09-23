#!/usr/bin/env python3
"""Update the generated open-source section in a GitHub profile README."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

START = "<!-- OSS_CONTRIBUTIONS:START -->"
END = "<!-- OSS_CONTRIBUTIONS:END -->"
MAX_REPOS = 5
MAX_PRS_PER_REPO = 3


def fetch_merged_prs(username: str, token: str) -> list[dict]:
    query = f"is:pr is:merged author:{username} -user:{username} archived:false"
    url = (
        "https://api.github.com/search/issues"
        f"?q={quote(query)}&sort=updated&order=desc&per_page=100"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "github-profile-readme-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return [item for item in payload["items"] if repo_name(item).split("/", 1)[0].lower() != username.lower()]


def repo_name(item: dict) -> str:
    path = urlparse(item["repository_url"]).path.strip("/")
    return path.removeprefix("repos/")


def contribution_kind(title: str) -> str:
    lowered = title.lower().lstrip()
    kinds = (
        (("fix", "bug"), "🐛"),
        (("feat", "add", "implement"), "🧩"),
        (("doc",), "📚"),
        (("test",), "🧪"),
        (("ci", "build", "chore", "refactor", "perf"), "⚙️"),
    )
    return next((icon for prefixes, icon in kinds if lowered.startswith(prefixes)), "🔧")


def render(prs: list[dict], username: str, language: str = "en") -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in prs:
        groups[repo_name(item)].append(item)

    if language == "zh":
        lines = [f"**已合并 {len(prs)} 个 PR · 涉及 {len(groups)} 个项目**", ""]
        empty_text = "_还没有已合并的外部 PR。_"
        merged_label = "个已合并"
        all_label = "查看全部已合并的 Pull Requests →"
    else:
        lines = [f"**{len(prs)} merged PRs · {len(groups)} projects**", ""]
        empty_text = "_No merged external pull requests found yet — the next quest is loading._"
        merged_label = "merged"
        all_label = "View all merged pull requests →"

    if not prs:
        lines.extend([empty_text, ""])
    else:
        for repo, items in list(groups.items())[:MAX_REPOS]:
            repo_url = f"https://github.com/{repo}"
            lines.extend([f"### [{repo}]({repo_url}) · {len(items)} {merged_label}", ""])
            for item in items[:MAX_PRS_PER_REPO]:
                title = html.escape(" ".join(item["title"].split()), quote=False)
                number = item["number"]
                merged_at = (item.get("pull_request", {}).get("merged_at") or item.get("closed_at") or "")[:10]
                lines.append(
                    f"- {contribution_kind(title)} {title} — [#{number}]({item['html_url']}) · {merged_at}"
                )
            lines.append("")

    query = quote(f"is:pr author:{username} is:merged")
    lines.append(f"[{all_label}](https://github.com/pulls?q={query})")
    return "\n".join(lines)


def replace_section(readme: str, generated: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one start marker and one end marker")
    before, remainder = readme.split(START, 1)
    _, after = remainder.split(END, 1)
    return f"{before}{START}\n{generated.rstrip()}\n{END}{after}"


def self_test() -> None:
    fixture = {
        "repository_url": "https://api.github.com/repos/example/project",
        "title": "fix: handle empty input",
        "number": 42,
        "html_url": "https://github.com/example/project/pull/42",
        "pull_request": {"merged_at": "2026-09-23T12:00:00Z"},
    }
    generated = render([fixture], "dafyy321-pixel")
    assert "🐛" in generated and "#42" in generated and "2026-09-23" in generated
    assert "已合并 1 个 PR" in render([fixture], "dafyy321-pixel", "zh")
    replaced = replace_section(f"before\n{START}\nold\n{END}\nafter\n", generated)
    assert "old" not in replaced and replaced.count(START) == replaced.count(END) == 1
    print("self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", default="README.md")
    parser.add_argument("--zh-readme", default="README.zh-CN.md")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    username = os.environ.get("PROFILE_USER", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not username or not token:
        print("PROFILE_USER and GITHUB_TOKEN are required", file=sys.stderr)
        return 2

    prs = fetch_merged_prs(username, token)
    for readme_path, language in ((Path(args.readme), "en"), (Path(args.zh_readme), "zh")):
        current = readme_path.read_text(encoding="utf-8")
        updated = replace_section(current, render(prs, username, language))
        if updated != current:
            temporary = readme_path.with_suffix(readme_path.suffix + ".tmp")
            temporary.write_text(updated, encoding="utf-8", newline="\n")
            temporary.replace(readme_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
