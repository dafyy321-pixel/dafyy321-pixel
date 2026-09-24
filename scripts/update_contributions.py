#!/usr/bin/env python3
"""Update the generated open-source section in a GitHub profile README."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

START = "<!-- OSS_CONTRIBUTIONS:START -->"
END = "<!-- OSS_CONTRIBUTIONS:END -->"
MAX_REPOS = 5
MAX_PRS_PER_REPO = 3

# Pixelarticons by Gerrit Halfmann, MIT licensed. See assets/PIXELARTICONS-LICENSE.txt.
SVG_ICONS = {
    "fix": (
        "M2 5h2v4H2zm20 0h-2v4h2zM4 9h2v2H4zm16 0h-2v2h2zM2 13h4v2H2zm20 0h-4v2h4zM4 17h2v2H4zm16 0h-2v2h2zM2 19h2v2H2zm20 0h-2v2h2zM6 11h12v2H6z",
        "M6 7h2v12H6zm10 0h2v12h-2zM8 19h8v2H8zM8 5h8v2H8zM11 15h2v6h-2zM8 1h2v6H8zm6 0h2v6h-2z",
    ),
    "feat": (
        "M11 1h2v4h-2zm0 22h2v-4h-2zM9 5h2v4H9zm0 14h2v-4H9zm4-14h2v4h-2zm0 14h2v-4h-2zM5 9h4v2H5zm14 0h-4v2h4zM1 11h4v2H1zm22 0h-4v2h4zM5 13h4v2H5zm14 0h-4v2h4zm0-12h2v6h-2z",
        "M17 3h6v2h-6zM3 17h2v2H3zm-2 2h2v2H1zm2 2h2v2H3zm2-2h2v2H5z",
    ),
    "docs": (
        "M2 3h9v2H2zM0 19h11v2H0zM13 3h9v2h-9zm0 16h11v2H13zM11 5h2v18h-2zM0 5h2v14H0zm22 0h2v14h-2zm-7 2h5v2h-5zm0 4h5v2h-5zm0 4h2v2h-2z",
    ),
    "test": (
        "M11 18H9v-4h2v4Zm-4-1H5v-2h2v2Zm12-2v2h-2v-2h2ZM5 15H3v-2h2v2Zm16 0h-2v-2h2v2Zm-8-1h-2v-4h2v4ZM3 13H1v-2h2v2Zm20 0h-2v-2h2v2ZM5 11H3V9h2v2Zm16 0h-2V9h2v2Zm-6-1h-2V6h2v4ZM7 9H5V7h2v2Zm12 0h-2V7h2v2Z",
    ),
    "tool": (
        "M9 22H7v-2h2v2Zm12-6h2v6h-6v-6h2v-6h2v6Zm-2 2v2h2v-2h-2ZM7 20H5v-8h2v8Zm4 0H9v-8h2v8Zm-6-8H3v-2h2v2Zm8 0h-2v-2h2v2ZM3 10H1V4h2v6Zm12 0h-2V4h2v6Zm4 0h-2V4h2v6Zm4 0h-2V4h2v6ZM7 6h2V2h4v2h-2v4H5V4H3V2h4v4Zm14-2h-2V2h2v2Z",
    ),
    "other": (
        "M4 2h4v2H4zm0 6h4v2H4zM2 4h2v4H2zm6 0h2v4H8zm8 10h4v2h-4zm0 6h4v2h-4zm-2-4h2v4h-2zm6 0h2v4h-2zM5 12h2v10H5zm7 0h2v2h-2zm-2-2h2v2h-2z",
    ),
}

KIND_LABELS = {
    "fix": "FIX",
    "feat": "FEAT",
    "docs": "DOCS",
    "test": "TEST",
    "tool": "TOOL",
    "other": "PR",
}


def fetch_merged_prs(username: str, token: str) -> list[dict]:
    query = f"is:pr is:merged author:{username} -user:{username} archived:false"
    url = (
        "https://api.github.com/search/issues"
        f"?q={quote(query)}&sort=updated&order=desc&per_page=100"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return [
        item
        for item in payload["items"]
        if repo_name(item).split("/", 1)[0].lower() != username.lower()
    ]


def repo_name(item: dict) -> str:
    path = urlparse(item["repository_url"]).path.strip("/")
    return path.removeprefix("repos/")


def contribution_kind(title: str) -> str:
    lowered = title.lower().lstrip()
    kinds = (
        (("fix", "bug"), "fix"),
        (("feat", "add", "implement"), "feat"),
        (("doc",), "docs"),
        (("test",), "test"),
        (("ci", "build", "chore", "refactor", "perf"), "tool"),
    )
    return next((kind for prefixes, kind in kinds if lowered.startswith(prefixes)), "other")


def visible_prs(prs: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in prs:
        groups[repo_name(item)].append(item)
    return [
        item
        for items in list(groups.values())[:MAX_REPOS]
        for item in items[:MAX_PRS_PER_REPO]
    ]


def truncate(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1].rstrip()}…"


def render_svg(prs: list[dict], language: str = "en") -> str:
    rows = visible_prs(prs)
    project_count = len({repo_name(item) for item in prs})
    row_height = 62
    header_height = 70
    height = header_height + max(len(rows), 1) * row_height + 18
    if language == "zh":
        count_label = f"已合并 {len(prs)} 个 PR / {project_count} 个项目"
        empty_label = "还没有已合并的外部 PR"
        alt = "自动更新的开源贡献记录"
    else:
        count_label = f"{len(prs)} MERGED PRS / {project_count} PROJECTS"
        empty_label = "NO MERGED EXTERNAL PRS YET"
        alt = "Automatically updated open-source contributions"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}" viewBox="0 0 1000 {height}" role="img" aria-label="{alt}">',
        "  <!-- Pixel icons: Pixelarticons by Gerrit Halfmann, MIT license. -->",
        "  <rect width=\"1000\" height=\"100%\" fill=\"#ffffff\"/>",
        "  <path d=\"M36 56H964\" stroke=\"#dfe7e4\"/>",
        f'  <text x="36" y="36" fill="#26322f" font-family="Inter, Segoe UI, Arial, Microsoft YaHei, sans-serif" font-size="14" font-weight="700">{html.escape(count_label)}</text>',
        "  <text x=\"964\" y=\"36\" text-anchor=\"end\" fill=\"#16866e\" font-family=\"Consolas, monospace\" font-size=\"12\" font-weight=\"700\">AUTO-SYNC</text>",
    ]

    if not rows:
        parts.append(
            f'  <text x="36" y="104" fill="#66736f" font-family="Consolas, monospace" font-size="13">{empty_label}</text>'
        )
    else:
        first_center = header_height + row_height // 2
        last_center = first_center + (len(rows) - 1) * row_height
        if len(rows) > 1:
            parts.append(
                f'  <path d="M66 {first_center}V{last_center}" stroke="#b9c9c4" stroke-width="2"/>'
            )

        for index, item in enumerate(rows):
            center = first_center + index * row_height
            top = center - 18
            kind = contribution_kind(item["title"])
            number = item["number"]
            merged_at = (
                item.get("pull_request", {}).get("merged_at")
                or item.get("closed_at")
                or ""
            )[:10]
            repo = html.escape(truncate(repo_name(item), 42))
            title = html.escape(truncate(item["title"], 76), quote=False)
            label = KIND_LABELS[kind]
            parts.extend(
                [
                    f'  <rect x="48" y="{top}" width="36" height="36" rx="3" fill="#ffffff" stroke="#bdc9c5"/>',
                    f'  <g transform="translate(54 {top + 6})" fill="#26322f">',
                    *(f'    <path d="{path}"/>' for path in SVG_ICONS[kind]),
                    "  </g>",
                    f'  <text x="104" y="{center - 4}" fill="#202a29" font-family="Inter, Segoe UI, Arial, Microsoft YaHei, sans-serif" font-size="15" font-weight="700">{repo} <tspan fill="#6c7975" font-weight="400">/ #{number}</tspan></text>',
                    f'  <text x="104" y="{center + 18}" fill="#52625d" font-family="Inter, Segoe UI, Arial, Microsoft YaHei, sans-serif" font-size="13">{title}</text>',
                    f'  <text x="964" y="{center + 5}" text-anchor="end" fill="#16866e" font-family="Consolas, monospace" font-size="12" font-weight="700">[ {label} ]  {merged_at}</text>',
                ]
            )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render(prs: list[dict], username: str, language: str = "en") -> str:
    query = quote(f"is:pr author:{username} is:merged")
    url = f"https://github.com/pulls?q={query}"
    if language == "zh":
        asset = "contributions-zh.svg"
        alt = "自动更新的开源贡献记录"
        all_label = "查看全部已合并的 Pull Requests →"
    else:
        asset = "contributions.svg"
        alt = "Automatically updated open-source contributions"
        all_label = "View all merged pull requests →"
    return (
        '<p align="center">\n'
        f'  <a href="{url}"><img src="./assets/{asset}" width="100%" alt="{alt}"></a>\n'
        "</p>\n\n"
        f"[{all_label}]({url})"
    )


def replace_section(readme: str, generated: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one start marker and one end marker")
    before, remainder = readme.split(START, 1)
    _, after = remainder.split(END, 1)
    return f"{before}{START}\n{generated.rstrip()}\n{END}{after}"


def write_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def self_test() -> None:
    fixture = {
        "repository_url": "https://api.github.com/repos/example/project",
        "title": "fix: handle empty input",
        "number": 42,
        "html_url": "https://github.com/example/project/pull/42",
        "pull_request": {"merged_at": "2026-09-23T12:00:00Z"},
    }
    svg = render_svg([fixture])
    ET.fromstring(svg)
    assert "example/project" in svg and "#42" in svg and "[ FIX ]" in svg
    assert "🐛" not in svg
    assert {
        contribution_kind("fix: handle empty input"),
        contribution_kind("feat: add export"),
        contribution_kind("docs: clarify setup"),
        contribution_kind("test: cover retries"),
        contribution_kind("refactor: simplify parser"),
        contribution_kind("update dependencies"),
    } == {"fix", "feat", "docs", "test", "tool", "other"}
    generated = render([fixture], "dafyy321-pixel")
    assert "assets/contributions.svg" in generated
    assert "assets/contributions-zh.svg" in render([fixture], "dafyy321-pixel", "zh")
    replaced = replace_section(f"before\n{START}\nold\n{END}\nafter\n", generated)
    assert "old" not in replaced and replaced.count(START) == replaced.count(END) == 1
    print("self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", default="README.md")
    parser.add_argument("--zh-readme", default="README.zh-CN.md")
    parser.add_argument("--assets-dir", default="assets")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    username = os.environ.get("PROFILE_USER", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not username:
        print("PROFILE_USER is required", file=sys.stderr)
        return 2

    prs = fetch_merged_prs(username, token)
    assets_dir = Path(args.assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    write_if_changed(assets_dir / "contributions.svg", render_svg(prs))
    write_if_changed(assets_dir / "contributions-zh.svg", render_svg(prs, "zh"))

    for readme_path, language in (
        (Path(args.readme), "en"),
        (Path(args.zh_readme), "zh"),
    ):
        current = readme_path.read_text(encoding="utf-8")
        updated = replace_section(current, render(prs, username, language))
        write_if_changed(readme_path, updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
