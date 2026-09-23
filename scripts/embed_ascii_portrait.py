#!/usr/bin/env python3
"""Replace gh-ascii's generated portrait with the profile's fixed portrait."""

from __future__ import annotations

import base64
import re
from pathlib import Path

PORTRAIT_ROWS = re.compile(r'^  <text x="28".*?</text>\r?\n?', re.MULTILINE)


def embed(svg: str, png: bytes) -> str:
    stripped, count = PORTRAIT_ROWS.subn("", svg)
    if count == 0:
        raise ValueError("No gh-ascii portrait rows found")

    marker = "  <text "
    position = stripped.find(marker)
    if position < 0:
        raise ValueError("No stats text found after removing the portrait")

    encoded = base64.b64encode(png).decode("ascii")
    image = (
        '  <image x="12" y="66" width="270" height="264" '
        'preserveAspectRatio="xMidYMid meet" '
        f'href="data:image/png;base64,{encoded}"/>\n'
    )
    return stripped[:position] + image + stripped[position:]


def update(svg_path: Path, portrait_path: Path) -> None:
    svg = svg_path.read_text(encoding="utf-8")
    updated = embed(svg, portrait_path.read_bytes())
    svg_path.write_text(updated, encoding="utf-8", newline="\n")


def self_test() -> None:
    fixture = '<svg>\n  <text x="28">a</text>\n  <text x="28">b</text>\n  <text x="294">stats</text>\n</svg>\n'
    result = embed(fixture, b"png")
    assert 'x="28"' not in result
    assert 'x="294"' in result
    assert result.count("<image ") == 1
    assert base64.b64encode(b"png").decode("ascii") in result


if __name__ == "__main__":
    self_test()
    assets = Path("assets")
    update(assets / "ascii-light.svg", assets / "ascii-portrait-light.png")
    update(assets / "ascii-dark.svg", assets / "ascii-portrait-dark.png")
