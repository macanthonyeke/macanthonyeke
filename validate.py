#!/usr/bin/env python3
"""Validate a staged profile publication set without network access."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
from typing import Mapping
from xml.etree import ElementTree

import generate
import snake


SVG_NS = "{http://www.w3.org/2000/svg}"
FORBIDDEN_TEXT = (
    "<script",
    "javascript:",
    "xlink:href",
    "<foreignObject",
    "<image",
    "@import",
    "url(http",
    "url(https",
    "Bearer ",
    "ghp_",
    "github_pat_",
)


class ReadmeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pictures: list[list[tuple[str, dict[str, str]]]] = []
        self.links: list[tuple[str, str]] = []
        self._picture: list[tuple[str, dict[str, str]]] | None = None
        self._link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag == "picture":
            if self._picture is not None:
                raise ValueError("README picture elements must not be nested")
            self._picture = []
        elif tag in {"source", "img"} and self._picture is not None:
            self._picture.append((tag, attributes))
        elif tag == "a":
            self._link = attributes.get("href", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "picture":
            if self._picture is None:
                raise ValueError("README contains an unmatched picture element")
            self.pictures.append(self._picture)
            self._picture = None
        elif tag == "a":
            self._link = None

    def handle_data(self, data: str) -> None:
        if self._link is not None:
            label = data.strip()
            if label:
                self.links.append((label, self._link))


def validate_readme(path: Path) -> None:
    markup = path.read_text(encoding="utf-8")
    parser = ReadmeParser()
    parser.feed(markup)
    parser.close()
    if parser._picture is not None:
        raise ValueError("README contains an unclosed picture element")

    expected_pictures = (
        (
            "assets/dark.svg",
            "assets/light.svg",
            "assets/light.svg",
            "MacAnthony Eke terminal-style engineering profile dashboard",
        ),
        (
            "assets/snake-dark.svg",
            "assets/snake-light.svg",
            "assets/snake-light.svg",
            "Animated GitHub contribution snake",
        ),
    )
    if len(parser.pictures) != len(expected_pictures):
        raise ValueError("README must contain exactly two picture elements")
    for elements, expected in zip(parser.pictures, expected_pictures):
        sources = [attrs for tag, attrs in elements if tag == "source"]
        images = [attrs for tag, attrs in elements if tag == "img"]
        if len(sources) != 2 or len(images) != 1:
            raise ValueError("each README picture must contain two sources and one image")
        by_media = {item.get("media"): item.get("srcset") for item in sources}
        if by_media.get("(prefers-color-scheme: dark)") != expected[0]:
            raise ValueError("README dark-mode source is incorrect")
        if by_media.get("(prefers-color-scheme: light)") != expected[1]:
            raise ValueError("README light-mode source is incorrect")
        if images[0].get("src") != expected[2] or images[0].get("alt") != expected[3]:
            raise ValueError("README fallback image or alt text is incorrect")

    expected_links = [
        ("Website", "https://trancheprotocol.xyz"),
        ("X", "https://x.com/macanthonyeke"),
        ("GitHub", "https://github.com/macanthonyeke"),
        ("Email", "mailto:macanthonyeke@gmail.com"),
    ]
    if parser.links != expected_links:
        raise ValueError("README contact links are incorrect or out of order")
    if "## " in markup or "Junior Smart Contract Engineer" in markup:
        raise ValueError("README contains legacy text-heavy profile content")


def _validate_svg(path: Path) -> ElementTree.Element:
    raw = path.read_text(encoding="utf-8")
    if not 1_000 < len(raw.encode("utf-8")) < 1_000_000:
        raise ValueError(f"SVG output has an unreasonable size: {path}")
    for marker in FORBIDDEN_TEXT:
        if marker in raw:
            raise ValueError(f"SVG contains forbidden content {marker!r}: {path}")
    without_namespace = raw.replace('xmlns="http://www.w3.org/2000/svg"', "")
    if "http://" in without_namespace:
        raise ValueError(f"SVG contains an external HTTP resource: {path}")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise ValueError(f"SVG is not valid XML: {path}") from exc
    if root.tag != f"{SVG_NS}svg":
        raise ValueError(f"output is not an SVG document: {path}")
    for element in root.iter():
        local_name = element.tag.rsplit("}", 1)[-1]
        if local_name in {"script", "image", "foreignObject"}:
            raise ValueError(f"SVG contains a forbidden element: {path}")
        for name in element.attrib:
            if name == "href" or name.endswith("}href"):
                raise ValueError(f"SVG contains an external reference: {path}")
    return root


def validate_dashboard(path: Path, stats: generate.ProfileStats, theme: str) -> None:
    root = _validate_svg(path)
    if root.attrib.get("viewBox") != f"0 0 {generate.CARD_WIDTH} {generate.CARD_HEIGHT}":
        raise ValueError(f"dashboard dimensions are incorrect: {path}")
    expected = {
        "total_contributions": str(stats.total_contributions),
        "current_streak": f"{stats.current_streak} days",
        "public_repositories": str(stats.public_repositories),
        "total_stars": str(stats.total_stars),
    }
    actual = {
        element.attrib["data-stat"]: element.attrib["data-value"]
        for element in root.iter(f"{SVG_NS}g")
        if "data-stat" in element.attrib
    }
    if actual != expected:
        raise ValueError(f"dashboard statistics do not match the snapshot: {path}")
    particles = [
        element
        for element in root.iter(f"{SVG_NS}circle")
        if element.attrib.get("class") == "portrait-particle"
    ]
    if len(particles) != 1350:
        raise ValueError(f"dashboard does not contain the approved portrait: {path}")
    expected_background = generate.THEMES[theme].background
    if expected_background not in path.read_text(encoding="utf-8"):
        raise ValueError(f"dashboard theme palette is incorrect: {path}")


def validate_snake(path: Path, snapshot: snake.Snapshot) -> None:
    root = _validate_svg(path)
    cells = [
        element
        for element in root.iter(f"{SVG_NS}rect")
        if "data-date" in element.attrib
    ]
    expected = [
        (item.day.isoformat(), str(item.count)) for item in snapshot.contributions
    ]
    actual = [(item.attrib["data-date"], item.attrib["data-count"]) for item in cells]
    if actual != expected:
        raise ValueError(f"snake calendar does not match the snapshot: {path}")
    raw = path.read_text(encoding="utf-8")
    if "prefers-reduced-motion: reduce" not in raw or "@keyframes snake-travel" not in raw:
        raise ValueError(f"snake animation behavior is incomplete: {path}")


def validate_publication(
    *,
    readme: Path,
    stats_path: Path,
    dots_path: Path,
    dashboard_dark: Path,
    dashboard_light: Path,
    snake_dark: Path,
    snake_light: Path,
) -> None:
    validate_readme(readme)
    dots = generate.load_dots(dots_path)
    if len(dots) != 1350:
        raise ValueError("publication must use the approved 1350-particle map")
    stats = generate.load_stats(stats_path)
    snake_snapshot = snake.load_snapshot(stats_path)
    validate_dashboard(dashboard_dark, stats, "dark")
    validate_dashboard(dashboard_light, stats, "light")
    validate_snake(snake_dark, snake_snapshot)
    validate_snake(snake_light, snake_snapshot)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--dots", type=Path, required=True)
    parser.add_argument("--dashboard-dark", type=Path, required=True)
    parser.add_argument("--dashboard-light", type=Path, required=True)
    parser.add_argument("--snake-dark", type=Path, required=True)
    parser.add_argument("--snake-light", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    validate_publication(
        readme=args.readme,
        stats_path=args.stats,
        dots_path=args.dots,
        dashboard_dark=args.dashboard_dark,
        dashboard_light=args.dashboard_light,
        snake_dark=args.snake_dark,
        snake_light=args.snake_light,
    )
    print("validated profile publication set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
