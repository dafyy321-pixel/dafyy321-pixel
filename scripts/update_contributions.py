#!/usr/bin/env python3
"""Update the generated open-source section in a GitHub profile README."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

START = "<!-- OSS_CONTRIBUTIONS:START -->"
END = "<!-- OSS_CONTRIBUTIONS:END -->"
PAGE_SIZE = 10

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
STAR_ICON = "M5 20H8V22H3V16H5V20ZM21 22H16V20H19V16H21V22ZM10 20H8V18H10V20ZM16 20H14V18H16V20ZM14 18H10V16H14V18ZM7 16H5V13H7V16ZM19 16H17V13H19V16ZM5 13H3V11H5V13ZM21 13H19V11H21V13ZM9 9H3V11H1V7H9V9ZM23 11H21V9H15V7H23V11ZM11 7H9V3H11V7ZM15 7H13V3H15V7ZM13 3H11V1H13V3Z"

# Only these README badges are considered project honors. Technical metadata
# badges (languages, licenses, CI, releases, downloads, and so on) are ignored.
HONOR_BADGE_MAX = 3
HONOR_BADGE_ATTR = re.compile(r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", re.IGNORECASE | re.DOTALL)
HONOR_BADGE_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
HONOR_BADGE_MARKDOWN = re.compile(r"!\[([^]]*)\]\((\S+?)(?:\s+['\"][^)]*['\"])?\)")

KIND_LABELS = {
    "fix": "FIX",
    "feat": "FEAT",
    "docs": "DOCS",
    "test": "TEST",
    "tool": "TOOL",
    "other": "PR",
}


def fetch_merged_prs(username: str, token: str) -> list[dict]:
    query = f"is:pr is:merged author:{username} -user:{username}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    items = []
    for page in range(1, 11):  # GitHub Search exposes at most 1,000 results.
        url = (
            "https://api.github.com/search/issues"
            f"?q={quote(query)}&sort=updated&order=desc&per_page=100&page={page}"
        )
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            payload = json.load(response)
        items.extend(payload["items"])
        if len(items) >= payload["total_count"] or not payload["items"]:
            break
    prs = [
        item
        for item in items
        if repo_name(item).split("/", 1)[0].lower() != username.lower()
    ]
    return sorted(
        prs,
        key=lambda item: item.get("pull_request", {}).get("merged_at") or item.get("closed_at") or "",
        reverse=True,
    )


def fetch_repo_stars(prs: list[dict], token: str) -> dict[str, int]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    stars = {}
    for item in prs:
        repo = repo_name(item)
        if repo not in stars:
            request = Request(item["repository_url"], headers=headers)
            with urlopen(request, timeout=30) as response:
                stars[repo] = json.load(response)["stargazers_count"]
    return stars


def fetch_repo_readme(repo: str, token: str) -> str:
    """Fetch a repository README as plain text, returning empty text on failure."""
    headers = {
        "Accept": "application/vnd.github.raw",
        "User-Agent": "github-profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/repos/{repo}/readme", headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:
        return ""


def honor_badge_kind(label: str, source: str) -> str | None:
    """Return a small category for supported honor/trend badges only."""
    haystack = f"{label} {source}".lower().replace("&amp;", "&")
    if "api.star-history.com/badge" in haystack and "type=trending" in haystack:
        return "trending"
    if "api.star-history.com/badge" in haystack and "type=rank" in haystack:
        return "rank"
    if "repository of the day" in haystack:
        return "trending"
    if "global rank" in haystack or "star history rank" in haystack:
        return "rank"
    # Trendshift's badge is a second common source for the same GitHub
    # Trending / Repository of the Day honor shown in the reference image.
    if "trendshift.io/api/badge" in haystack and "trend" in haystack:
        return "trending"
    return None


def parse_honor_badges(readme: str) -> list[dict]:
    """Extract supported badge image URLs from README HTML/Markdown."""
    candidates: list[dict] = []
    seen: set[str] = set()
    for match in HONOR_BADGE_IMG.finditer(readme):
        attrs = {name.lower(): value for name, _, value in HONOR_BADGE_ATTR.findall(match.group(0))}
        source = attrs.get("src", "").replace("&amp;", "&")
        if source.startswith("//"):
            source = f"https:{source}"
        label = attrs.get("alt", "")
        kind = honor_badge_kind(label, source)
        if kind and source and source not in seen:
            seen.add(source)
            candidates.append({"kind": kind, "label": label, "source": source})
    for match in HONOR_BADGE_MARKDOWN.finditer(readme):
        label, source = match.groups()
        source = source.replace("&amp;", "&")
        if source.startswith("//"):
            source = f"https:{source}"
        kind = honor_badge_kind(label, source)
        if kind and source and source not in seen:
            seen.add(source)
            candidates.append({"kind": kind, "label": label, "source": source})
    return candidates[:HONOR_BADGE_MAX]


def fetch_badge_image(source: str) -> str:
    """Download a badge and return a data URI so the generated SVG is self-contained."""
    try:
        request = Request(source, headers={"User-Agent": "github-profile-readme-updater"})
        with urlopen(request, timeout=20) as response:
            content = response.read()
            content_type = response.headers.get_content_type() or "image/svg+xml"
        if not content_type.startswith("image/"):
            content_type = "image/svg+xml"
        return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"
    except Exception:
        return ""


def fetch_repo_honor_badges(prs: list[dict], token: str) -> dict[str, list[dict]]:
    """Fetch supported honor badges for each listed project."""
    badges: dict[str, list[dict]] = {}
    for item in prs:
        repo = repo_name(item)
        if repo in badges:
            continue
        parsed = parse_honor_badges(fetch_repo_readme(repo, token))
        loaded = []
        for badge in parsed:
            image = fetch_badge_image(badge["source"])
            if image:
                loaded.append({**badge, "image": image})
        badges[repo] = loaded
    return badges


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


def truncate(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1].rstrip()}…"


def format_stars(count: int) -> str:
    if count < 1000:
        return str(count)
    value, suffix = (count / 1_000_000, "m") if count >= 1_000_000 else (count / 1000, "k")
    return f"{value:.1f}".rstrip("0").rstrip(".") + suffix


def render_svg(
    prs: list[dict],
    stars: dict[str, int],
    badges: dict[str, list[dict]] | None = None,
    language: str = "en",
    page: int = 1,
) -> str:
    badges = badges or {}
    rows = prs[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    page_count = max(1, (len(prs) + PAGE_SIZE - 1) // PAGE_SIZE)
    project_count = len({repo_name(item) for item in prs})
    row_height = 62
    header_height = 70
    height = header_height + max(len(rows), 1) * row_height + 18
    if language == "zh":
        count_label = f"已合并 {len(prs)} 个 PR / {project_count} 个项目 · 第 {page}/{page_count} 页"
        empty_label = "还没有已合并的外部 PR"
        alt = "自动更新的开源贡献记录"
    else:
        count_label = f"{len(prs)} MERGED PRS / {project_count} PROJECTS · PAGE {page}/{page_count}"
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
            star_count = format_stars(stars[repo_name(item)])
            title = html.escape(truncate(item["title"], 76), quote=False)
            label = KIND_LABELS[kind]
            repo_badges = badges.get(repo_name(item), [])[:HONOR_BADGE_MAX]
            badge_count = len(repo_badges)
            # Keep the badge group clear of the right-aligned Star count. A
            # single badge gets more room for readable text; three badges fit
            # compactly across the center gap.
            badge_width, badge_height = {
                1: (144, 32),
                2: (124, 29),
                3: (108, 26),
            }.get(badge_count, (0, 0))
            badge_gap = 8
            badge_right = 708
            badge_start = badge_right - badge_count * badge_width - max(badge_count - 1, 0) * badge_gap
            parts.extend(
                [
                    f'  <rect x="48" y="{top}" width="36" height="36" rx="3" fill="#ffffff" stroke="#bdc9c5"/>',
                    f'  <g transform="translate(54 {top + 6})" fill="#26322f">',
                    *(f'    <path d="{path}"/>' for path in SVG_ICONS[kind]),
                    "  </g>",
                    f'  <text x="104" y="{center - 4}" fill="#202a29" font-family="Inter, Segoe UI, Arial, Microsoft YaHei, sans-serif" font-size="15" font-weight="700">{repo} <tspan fill="#6c7975" font-weight="400">/ #{number}</tspan></text>',
                    *(
                        f'  <image x="{badge_start + badge_index * (badge_width + badge_gap)}" y="{center - badge_height // 2}" width="{badge_width}" height="{badge_height}" preserveAspectRatio="xMidYMid meet" href="{badge["image"]}"><title>{html.escape(badge.get("label", "Project honor badge"))}</title></image>'
                        for badge_index, badge in enumerate(repo_badges)
                    ),
                    f'  <text x="762" y="{center + 6}" text-anchor="end" fill="#26322f" font-family="Consolas, monospace" font-size="16" font-weight="700">{star_count}</text>',
                    f'  <path d="{STAR_ICON}" transform="translate(770 {center - 12})" fill="#26322f"/>',
                    f'  <text x="104" y="{center + 18}" fill="#52625d" font-family="Inter, Segoe UI, Arial, Microsoft YaHei, sans-serif" font-size="13">{title}</text>',
                    f'  <text x="964" y="{center + 5}" text-anchor="end" fill="#16866e" font-family="Consolas, monospace" font-size="12" font-weight="700">[ {label} ]  {merged_at}</text>',
                ]
            )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def pager_icon(label: str, active: bool = False, disabled: bool = False) -> str:
    color = "#b9c9c4" if disabled else "#ffffff" if active else (
        "#16866e" if label in ("←", "→") else "#26322f"
    )
    background = '<rect width="34" height="34" rx="3" fill="#26322f"/>' if active else ""
    size = 17 if label in ("←", "→") else 12
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="34" height="34" viewBox="0 0 34 34">\n'
        f'  {background}\n'
        f'  <text x="17" y="22" text-anchor="middle" fill="{color}" font-family="Consolas, monospace" font-size="{size}" font-weight="700">{label}</text>\n'
        '</svg>\n'
    )


def page_document(language: str, page: int) -> str:
    return asset_name(language, page).removesuffix(".svg") + ".md"


def render(prs: list[dict], username: str, language: str = "en", page: int = 1, archive: bool = False) -> str:
    query = quote(f"is:pr author:{username} is:merged")
    url = f"https://github.com/pulls?q={query}"
    if language == "zh":
        alt = "自动更新的开源贡献记录"
        all_label = "查看全部已合并的 Pull Requests →"
        profile = "README.zh-CN.md#开源贡献"
    else:
        alt = "Automatically updated open-source contributions"
        all_label = "View all merged pull requests →"
        profile = "README.md#open-source-quest-log"
    pages = max(1, (len(prs) + PAGE_SIZE - 1) // PAGE_SIZE)
    prefix = "./" if archive else "./assets/"
    image = (
        '<p align="center">\n'
        f'  <a href="{url}"><img src="{prefix}{asset_name(language, page)}" width="100%" alt="{alt}"></a>\n'
        '</p>'
    )
    if pages == 1:
        return image + f"\n\n[{all_label}]({url})"

    def href(target: int) -> str:
        if target == 1:
            return f"../{profile}" if archive else f"./{profile}"
        return f"{prefix}{page_document(language, target)}"

    def control(target: int, icon: str, title: str) -> str:
        image_tag = f'<img src="{prefix}{icon}" width="34" height="34" alt="{title}">'
        return f'<a href="{href(target)}">{image_tag}</a>'

    start = (page - 1) * PAGE_SIZE + 1
    end = min(page * PAGE_SIZE, len(prs))
    range_label = f"SHOWING {start:02d}–{end:02d} OF {len(prs)}" if language == "en" else f"显示 {start}–{end} / 共 {len(prs)} 条"
    controls = []
    if page > 1:
        controls.append(control(page - 1, "pager-prev.svg", "上一页" if language == "zh" else "Previous page"))
    numbered = sorted({1, pages, *(n for n in range(page - 1, page + 2) if 1 <= n <= pages)})
    for index, number in enumerate(numbered):
        if index and number - numbered[index - 1] > 1:
            controls.append("…")
        controls.append(control(number,
                                f"pager-{number:02d}{'-active' if number == page else ''}.svg",
                                f"第 {number} 页" if language == "zh" else f"Page {number}"))
    if page < pages:
        controls.append(control(page + 1, "pager-next.svg", "下一页" if language == "zh" else "Next page"))
    pager = (
        '<hr>\n'
        '<p align="right">\n'
        f'  <code>{range_label}</code>&nbsp;&nbsp; ' + " ".join(controls) + '\n'
        '</p>'
    )
    return image + "\n\n" + pager + f"\n\n[{all_label}]({url})"


def asset_name(language: str, page: int) -> str:
    suffix = "-zh" if language == "zh" else ""
    page_suffix = f"-page-{page}" if page > 1 else ""
    return f"contributions{suffix}{page_suffix}.svg"


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
    fixture_badge = {
        "kind": "trending",
        "label": "GitHub Trending Repository of the Day",
        "source": "https://api.star-history.com/badge?repo=example/project&type=trending",
        "image": "data:image/svg+xml;base64,PHN2Zy8+",
    }
    svg = render_svg([fixture], {"example/project": 1234}, {"example/project": [fixture_badge]})
    ET.fromstring(svg)
    assert "example/project" in svg and "#42" in svg and "[ FIX ]" in svg
    assert 'font-size="16" font-weight="700">1.2k</text>' in svg and STAR_ICON in svg
    assert 'data:image/svg+xml;base64,PHN2Zy8+' in svg
    parsed = parse_honor_badges(
        '<img alt="GitHub Trending Repository of the Day" src="https://api.star-history.com/badge?repo=x/y&amp;type=trending">'
        '<img alt="Python" src="https://img.shields.io/badge/Python">'
        '<img alt="Star History Rank" src="https://api.star-history.com/badge?repo=x/y&amp;type=rank">'
    )
    assert [badge["kind"] for badge in parsed] == ["trending", "rank"]
    assert [format_stars(count) for count in (0, 999, 1000, 1234, 1_000_000)] == ["0", "999", "1k", "1.2k", "1m"]
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
    paged_prs = [{**fixture, "number": number} for number in range(11, 0, -1)]
    page_one = render_svg(paged_prs, {"example/project": 1234}, page=1)
    page_two = render_svg(paged_prs, {"example/project": 1234}, page=2)
    assert page_one.count('font-weight="700">example/project') == 10
    assert page_two.count('font-weight="700">example/project') == 1
    assert "/ #11" in page_one and "/ #1" in page_two and "/ #11" not in page_two
    paged_readme = render(paged_prs, "dafyy321-pixel")
    assert "<details" not in paged_readme
    assert 'assets/contributions.svg' in paged_readme
    assert 'href="./assets/contributions-page-2.md"' in paged_readme
    assert 'href="./README.md#open-source-quest-log"><img src="./assets/pager-01-active.svg"' in paged_readme
    assert "pager-prev-disabled.svg" not in paged_readme
    assert "SHOWING 01–10 OF 11" in paged_readme
    archived = render(paged_prs, "dafyy321-pixel", page=2, archive=True)
    assert 'src="./contributions-page-2.svg"' in archived
    assert 'href="../README.md#open-source-quest-log"' in archived
    assert 'href="./contributions-page-2.md"><img src="./pager-02-active.svg"' in archived
    assert "pager-next-disabled.svg" not in archived
    assert "SHOWING 11–11 OF 11" in archived
    ET.fromstring(pager_icon("02", active=True))
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
    stars = fetch_repo_stars(prs, token)
    badges = fetch_repo_honor_badges(prs, token)
    assets_dir = Path(args.assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    pages = max(1, (len(prs) + PAGE_SIZE - 1) // PAGE_SIZE)
    for language in ("en", "zh"):
        for page in range(1, pages + 1):
            write_if_changed(
                assets_dir / asset_name(language, page),
                render_svg(prs, stars, badges, language, page),
            )
            if page > 1:
                heading = "开源贡献" if language == "zh" else "Open-source quest log"
                write_if_changed(
                    assets_dir / page_document(language, page),
                    f"# {heading}\n\n{render(prs, username, language, page, archive=True)}\n",
                )
    if pages > 1:
        for page in range(1, pages + 1):
            number = f"{page:02d}"
            write_if_changed(assets_dir / f"pager-{number}.svg", pager_icon(number))
            write_if_changed(assets_dir / f"pager-{number}-active.svg", pager_icon(number, active=True))
        for direction, arrow in (("prev", "←"), ("next", "→")):
            write_if_changed(assets_dir / f"pager-{direction}.svg", pager_icon(arrow))
            write_if_changed(assets_dir / f"pager-{direction}-disabled.svg", pager_icon(arrow, disabled=True))

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
