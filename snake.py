#!/usr/bin/env python3
"""Generate a deterministic animated contribution snake from validated data.

The generator uses only the Python standard library. The contribution grid is
data: every date, count, and GitHub contribution level comes directly from the
normalized ``assets/github-stats.json`` snapshot. The snake and temporary cell
dimming are decorative and never alter those values.

Animation model:

* 10 tapered body segments trail one larger head.
* The snake moves at 96 SVG units/second on one shared CSS keyframe route.
* It traverses seven serpentine calendar rows, reversing at grid boundaries.
* After the final row it returns through a bottom/left perimeter lane, making
  the route closed and the loop continuous.
* Every real calendar cell uses one shared consume/regenerate keyframe with a
  deterministic delay matching the head's arrival time. Blank slots in
  incomplete first or last weeks are not rendered or consumed.
* Reduced motion disables cell and snake animation, restores every original
  contribution cell, and displays a short static snake.
"""

from __future__ import annotations

import argparse
import binascii
import json
import math
import struct
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from xml.etree import ElementTree


DEFAULT_STATS = Path("assets/github-stats.json")
DEFAULT_OUTPUT_DIR = Path("assets")
DEFAULT_PREVIEW_DIR = Path("assets/previews")
USERNAME = "macanthonyeke"
TIMEZONE = "Africa/Lagos"

WIDTH = 760
HEIGHT = 194
GRID_X = 43.0
GRID_Y = 58.0
CELL_SIZE = 10.0
CELL_GAP = 3.0
CELL_STEP = CELL_SIZE + CELL_GAP
SNAKE_SPEED = 96.0
BODY_SEGMENTS = 10
SEGMENT_LAG_SECONDS = 0.06
BODY_RADIUS_BASE = 4.35
BODY_RADIUS_TAPER = 0.14
BODY_WAVE = 0.65
REGEN_FRACTION = 0.08
ANIMATION_PREVIEW_FPS = 8
ANIMATION_PREVIEW_SECONDS = 6
ANIMATION_PREVIEW_START_PHASE = 0.34

LEVEL_NAMES = (
    "NONE",
    "FIRST_QUARTILE",
    "SECOND_QUARTILE",
    "THIRD_QUARTILE",
    "FOURTH_QUARTILE",
)
LEVEL_INDEX = {name: index for index, name in enumerate(LEVEL_NAMES)}


@dataclass(frozen=True)
class Contribution:
    day: date
    count: int
    level: str
    source_color: str


@dataclass(frozen=True)
class Snapshot:
    generated_at: str
    period_start: date
    period_end: date
    total_contributions: int
    contributions: tuple[Contribution, ...]


@dataclass(frozen=True)
class CalendarCell:
    contribution: Contribution
    week: int
    weekday: int


@dataclass(frozen=True)
class CalendarLayout:
    cells: tuple[CalendarCell, ...]
    first_sunday: date
    last_saturday: date
    week_count: int


@dataclass(frozen=True)
class Route:
    points: tuple[tuple[float, float], ...]
    cumulative: tuple[float, ...]
    length: float
    duration: float


@dataclass(frozen=True)
class SnakeTheme:
    name: str
    background: str
    panel: str
    border: str
    foreground: str
    muted: str
    accent: str
    levels: tuple[str, str, str, str, str]
    snake: str
    snake_highlight: str
    eye: str


DARK_THEME = SnakeTheme(
    name="dark",
    background="#1b1a21",
    panel="#24222c",
    border="#3b3749",
    foreground="#eeeaf5",
    muted="#9b94aa",
    accent="#b18cff",
    levels=("#2d2935", "#4c3b60", "#674987", "#895fb5", "#ac83eb"),
    snake="#d7c4ff",
    snake_highlight="#f1eaff",
    eye="#332641",
)

LIGHT_THEME = SnakeTheme(
    name="light",
    background="#f5f2f8",
    panel="#fffdfd",
    border="#d9d2e3",
    foreground="#2b2435",
    muted="#6d6478",
    accent="#7047b8",
    levels=("#ebe6ef", "#d9c8e8", "#bc9ed8", "#946cc0", "#7047a9"),
    snake="#59318e",
    snake_highlight="#8b61bd",
    eye="#fffdfd",
)

THEMES = (DARK_THEME, LIGHT_THEME)


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be an ISO date") from None


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def load_snapshot(path: Path = DEFAULT_STATS) -> Snapshot:
    """Load and strictly validate the normalized GraphQL calendar snapshot."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("statistics snapshot must contain a JSON object")
    if payload.get("username") != USERNAME or payload.get("timezone") != TIMEZONE:
        raise ValueError("statistics snapshot belongs to an unexpected profile")
    period = payload.get("period")
    statistics = payload.get("statistics")
    raw_days = payload.get("contributions")
    if not isinstance(period, Mapping) or not isinstance(statistics, Mapping):
        raise ValueError("statistics snapshot metadata is incomplete")
    if not isinstance(raw_days, list):
        raise ValueError("statistics snapshot has no contribution calendar")

    period_start = _parse_date(period.get("from"), "period start")
    period_end = _parse_date(period.get("to"), "period end")
    expected_days = (period_end - period_start).days + 1
    if expected_days <= 0 or period.get("days") != expected_days:
        raise ValueError("statistics snapshot period is inconsistent")
    if len(raw_days) != expected_days:
        raise ValueError("statistics snapshot contribution coverage is incomplete")

    contributions: list[Contribution] = []
    for index, raw_day in enumerate(raw_days):
        if not isinstance(raw_day, Mapping):
            raise ValueError("contribution day must be an object")
        contribution_day = _parse_date(raw_day.get("date"), "contribution date")
        expected_date = period_start + timedelta(days=index)
        if contribution_day != expected_date:
            raise ValueError(
                f"contribution calendar is not contiguous at {expected_date.isoformat()}"
            )
        count = _nonnegative_int(raw_day.get("count"), "contribution count")
        level = raw_day.get("level")
        color = raw_day.get("color")
        if level not in LEVEL_INDEX or not isinstance(color, str):
            raise ValueError("contribution display metadata is invalid")
        if (count == 0) != (level == "NONE"):
            raise ValueError("contribution count and GitHub level disagree")
        contributions.append(
            Contribution(contribution_day, count, str(level), color)
        )

    total = _nonnegative_int(
        statistics.get("total_contributions"), "total contributions"
    )
    if sum(item.count for item in contributions) != total:
        raise ValueError("daily contribution counts do not match snapshot total")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        raise ValueError("statistics snapshot generation time is missing")
    return Snapshot(
        generated_at=generated_at,
        period_start=period_start,
        period_end=period_end,
        total_contributions=total,
        contributions=tuple(contributions),
    )


def sunday_weekday(value: date) -> int:
    """Return GitHub's Sunday=0 through Saturday=6 weekday index."""

    return (value.weekday() + 1) % 7


def layout_calendar(contributions: Sequence[Contribution]) -> CalendarLayout:
    """Place contiguous dates into standard week columns and weekday rows."""

    if not contributions:
        raise ValueError("calendar must contain at least one contribution day")
    for previous, current in zip(contributions, contributions[1:]):
        if current.day - previous.day != timedelta(days=1):
            raise ValueError("calendar dates must be contiguous")
    first_day = contributions[0].day
    last_day = contributions[-1].day
    first_sunday = first_day - timedelta(days=sunday_weekday(first_day))
    last_saturday = last_day + timedelta(days=6 - sunday_weekday(last_day))
    week_count = ((last_saturday - first_sunday).days + 1) // 7
    cells = tuple(
        CalendarCell(
            contribution=item,
            week=(item.day - first_sunday).days // 7,
            weekday=sunday_weekday(item.day),
        )
        for item in contributions
    )
    return CalendarLayout(cells, first_sunday, last_saturday, week_count)


def _append_point(points: list[tuple[float, float]], point: tuple[float, float]) -> None:
    if not points or points[-1] != point:
        points.append(point)


def build_route(layout: CalendarLayout) -> Route:
    """Build one closed serpentine route with a non-teleporting return lane."""

    if layout.week_count <= 0:
        raise ValueError("calendar layout has no weeks")
    x_first = GRID_X + CELL_SIZE / 2
    x_last = x_first + (layout.week_count - 1) * CELL_STEP
    y_first = GRID_Y + CELL_SIZE / 2
    y_last = y_first + 6 * CELL_STEP
    points: list[tuple[float, float]] = [(x_first, y_first)]
    for weekday in range(7):
        row_y = y_first + weekday * CELL_STEP
        row_end_x = x_last if weekday % 2 == 0 else x_first
        _append_point(points, (row_end_x, row_y))
        if weekday < 6:
            _append_point(points, (row_end_x, row_y + CELL_STEP))

    lane = CELL_STEP * 1.4
    right_lane = x_last + lane
    bottom_lane = y_last + lane
    left_lane = x_first - lane
    _append_point(points, (right_lane, y_last))
    _append_point(points, (right_lane, bottom_lane))
    _append_point(points, (left_lane, bottom_lane))
    _append_point(points, (left_lane, y_first))
    _append_point(points, (x_first, y_first))

    cumulative = [0.0]
    for start, end in zip(points, points[1:]):
        distance = math.hypot(end[0] - start[0], end[1] - start[1])
        cumulative.append(cumulative[-1] + distance)
    length = cumulative[-1]
    if length <= 0:
        raise ValueError("snake route has no length")
    return Route(
        points=tuple(points),
        cumulative=tuple(cumulative),
        length=length,
        duration=length / SNAKE_SPEED,
    )


def cell_arrival_distance(cell: CalendarCell, layout: CalendarLayout) -> float:
    """Return distance from route start to one calendar cell center."""

    row_width = (layout.week_count - 1) * CELL_STEP
    completed_rows = cell.weekday * (row_width + CELL_STEP)
    horizontal = (
        cell.week * CELL_STEP
        if cell.weekday % 2 == 0
        else (layout.week_count - 1 - cell.week) * CELL_STEP
    )
    return completed_rows + horizontal


def cell_animation_delay(
    cell: CalendarCell, layout: CalendarLayout, route: Route
) -> float:
    """Align a cell's shared CSS cycle with the head's own arrival time."""

    arrival = cell_arrival_distance(cell, layout) / SNAKE_SPEED
    return arrival - route.duration


def cell_cycle_phase(
    elapsed_seconds: float,
    arrival_seconds: float,
    route: Route,
) -> float:
    """Return a cell's 0..1 consume/regenerate phase, including loop wrap."""

    return ((elapsed_seconds - arrival_seconds) % route.duration) / route.duration


def cell_opacity_at_elapsed(
    elapsed_seconds: float,
    arrival_seconds: float,
    route: Route,
) -> float:
    """Mirror the SVG consume/regenerate opacity keyframes for one cell."""

    phase = cell_cycle_phase(elapsed_seconds, arrival_seconds, route)
    if phase <= 0.0035:
        return 1.0
    if phase <= 0.012:
        return 1.0 - 0.9 * ((phase - 0.0035) / (0.012 - 0.0035))
    if phase <= 0.032:
        return 0.1
    if phase <= REGEN_FRACTION:
        return 0.1 + 0.9 * ((phase - 0.032) / (REGEN_FRACTION - 0.032))
    return 1.0


def body_radius(index: int) -> float:
    if not 1 <= index <= BODY_SEGMENTS:
        raise ValueError("body segment index is out of range")
    return BODY_RADIUS_BASE - index * BODY_RADIUS_TAPER


def body_wave(index: int) -> float:
    if not 1 <= index <= BODY_SEGMENTS:
        raise ValueError("body segment index is out of range")
    return BODY_WAVE if index % 2 == 0 else -BODY_WAVE


def snake_segment_distance(route: Route, elapsed_seconds: float, index: int) -> float:
    """Return the route distance for the head (0) or one trailing segment."""

    if not 0 <= index <= BODY_SEGMENTS:
        raise ValueError("snake segment index is out of range")
    return (
        elapsed_seconds * SNAKE_SPEED
        - index * SEGMENT_LAG_SECONDS * SNAKE_SPEED
    ) % route.length


def snake_render_bounds(route: Route) -> tuple[float, float, float, float]:
    """Conservative bounds for the head, face, and undulating body."""

    head_extent = 6.0
    body_extent = max(
        body_radius(index) + abs(body_wave(index))
        for index in range(1, BODY_SEGMENTS + 1)
    )
    extent = max(head_extent, body_extent)
    x_values = [point[0] for point in route.points]
    y_values = [point[1] for point in route.points]
    return (
        min(x_values) - extent,
        min(y_values) - extent,
        max(x_values) + extent,
        max(y_values) + extent,
    )


def point_at_distance(route: Route, distance: float) -> tuple[float, float]:
    """Interpolate a point on the closed route for static preview rendering."""

    target = distance % route.length
    for index, (start_distance, end_distance) in enumerate(
        zip(route.cumulative, route.cumulative[1:])
    ):
        if target <= end_distance or index == len(route.points) - 2:
            span = end_distance - start_distance
            ratio = 0.0 if span == 0 else (target - start_distance) / span
            start = route.points[index]
            end = route.points[index + 1]
            return (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
    return route.points[0]


def _format_number(value: float) -> str:
    return format(value, ".3f").rstrip("0").rstrip(".") or "0"


def _route_keyframes(route: Route) -> str:
    frames = []
    for point, distance in zip(route.points, route.cumulative):
        percentage = 100.0 * distance / route.length
        frames.append(
            f"      {_format_number(percentage)}% "
            f"{{ transform: translate({_format_number(point[0])}px, "
            f"{_format_number(point[1])}px); }}"
        )
    return "\n".join(frames)


def _month_labels(layout: CalendarLayout) -> tuple[tuple[str, int], ...]:
    labels: list[tuple[str, int]] = []
    seen: set[tuple[int, int]] = set()
    for cell in layout.cells:
        key = (cell.contribution.day.year, cell.contribution.day.month)
        if key in seen:
            continue
        seen.add(key)
        labels.append((cell.contribution.day.strftime("%b"), cell.week))
    return tuple(labels)


def _cell_markup(
    layout: CalendarLayout,
    route: Route,
) -> str:
    markup: list[str] = []
    for cell in layout.cells:
        contribution = cell.contribution
        x = GRID_X + cell.week * CELL_STEP
        y = GRID_Y + cell.weekday * CELL_STEP
        delay = cell_animation_delay(cell, layout, route)
        level = LEVEL_INDEX[contribution.level]
        markup.append(
            f'    <rect class="contribution-cell level-{level}" '
            f'x="{_format_number(x)}" y="{_format_number(y)}" '
            f'width="{_format_number(CELL_SIZE)}" height="{_format_number(CELL_SIZE)}" '
            f'rx="2" data-date="{contribution.day.isoformat()}" '
            f'data-count="{contribution.count}" '
            f'style="animation-delay:{_format_number(delay)}s" />'
        )
    return "\n".join(markup)


def _snake_markup(route: Route, theme: SnakeTheme) -> str:
    pieces: list[str] = []
    for index in range(BODY_SEGMENTS, 0, -1):
        radius = body_radius(index)
        delay = -(route.duration - index * SEGMENT_LAG_SECONDS)
        wave = body_wave(index)
        pieces.append(
            f'    <circle class="snake-mover snake-body" cx="0" cy="{_format_number(wave)}" '
            f'r="{_format_number(radius)}" '
            f'style="animation-delay:{_format_number(delay)}s" />'
        )
    pieces.append(
        f'''    <g class="snake-mover snake-head" style="animation-delay:0s">
      <circle cx="0" cy="0" r="6" fill="{theme.snake}" />
      <ellipse cx="0" cy="-1" rx="4.1" ry="2.8" fill="{theme.snake_highlight}" fill-opacity="0.38" />
      <circle cx="-2" cy="-1.5" r="1.15" fill="{theme.eye}" />
      <circle cx="2" cy="-1.5" r="1.15" fill="{theme.eye}" />
      <path d="M -2 1 Q 0 2.6 2 1" fill="none" stroke="{theme.eye}" stroke-width="0.8" stroke-linecap="round" />
    </g>'''
    )
    static_x = GRID_X + 7 * CELL_STEP
    static_y = GRID_Y + CELL_SIZE / 2
    static_segments = "\n".join(
        f'      <circle cx="{_format_number(-index * SEGMENT_LAG_SECONDS * SNAKE_SPEED)}" cy="{_format_number(body_wave(index))}" r="{_format_number(body_radius(index))}" />'
        for index in range(BODY_SEGMENTS, 0, -1)
    )
    pieces.append(
        f'''    <g class="static-snake" transform="translate({_format_number(static_x)} {_format_number(static_y)})" fill="{theme.snake}">
{static_segments}
      <circle cx="0" cy="0" r="6" />
      <circle cx="-2" cy="-1.5" r="1.15" fill="{theme.eye}" />
      <circle cx="2" cy="-1.5" r="1.15" fill="{theme.eye}" />
      <path d="M -2 1 Q 0 2.6 2 1" fill="none" stroke="{theme.eye}" stroke-width="0.8" stroke-linecap="round" />
    </g>'''
    )
    return "\n".join(pieces)


def build_svg(snapshot: Snapshot, theme: SnakeTheme) -> str:
    """Build one self-contained animated SVG from genuine contribution data."""

    layout = layout_calendar(snapshot.contributions)
    route = build_route(layout)
    duration = _format_number(route.duration)
    level_css = "\n".join(
        f"    .level-{index} {{ fill: {color}; }}"
        for index, color in enumerate(theme.levels)
    )
    month_markup = "\n".join(
        f'  <text x="{_format_number(GRID_X + week * CELL_STEP)}" y="51" '
        f'class="month">{escape(label)}</text>'
        for label, week in _month_labels(layout)
    )
    range_text = f"{snapshot.period_start.isoformat()} → {snapshot.period_end.isoformat()}"
    description = (
        f"GitHub contribution calendar with {len(snapshot.contributions)} genuine daily values. "
        f"A decorative {BODY_SEGMENTS + 1}-part snake moves at {SNAKE_SPEED:g} SVG units per second "
        f"for a {_format_number(route.duration)} second loop. Cells temporarily dim after the head "
        "passes and regenerate to their original contribution level."
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}"
     viewBox="0 0 {WIDTH} {HEIGHT}" role="img"
     aria-label="Animated GitHub contribution snake for {USERNAME}">
  <title>{USERNAME} contribution snake</title>
  <desc>{escape(description)}</desc>
  <style>
    @keyframes snake-travel {{
{_route_keyframes(route)}
    }}
    @keyframes cell-consume {{
      0%, 0.35% {{ opacity: 1; transform: scale(1); }}
      1.2%, 3.2% {{ opacity: 0.10; transform: scale(0.28); }}
      8%, 100% {{ opacity: 1; transform: scale(1); }}
    }}
    .contribution-cell {{
      animation: cell-consume {duration}s linear infinite;
      transform-box: fill-box;
      transform-origin: center;
    }}
{level_css}
    .snake-mover {{
      animation-name: snake-travel;
      animation-duration: {duration}s;
      animation-timing-function: linear;
      animation-iteration-count: infinite;
      will-change: transform;
    }}
    .snake-body {{ fill: {theme.snake}; }}
    .static-snake {{ display: none; }}
    .label, .month {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    .month {{ fill: {theme.muted}; font-size: 9px; }}
    @media (prefers-reduced-motion: reduce) {{
      .contribution-cell {{ animation: none !important; opacity: 1 !important; transform: none !important; }}
      .snake-mover {{ display: none !important; animation: none !important; }}
      .static-snake {{ display: inline !important; }}
    }}
  </style>

  <rect width="{WIDTH}" height="{HEIGHT}" rx="16" fill="{theme.background}" />
  <rect x="10" y="10" width="{WIDTH - 20}" height="{HEIGHT - 20}" rx="12"
        fill="{theme.panel}" stroke="{theme.border}" stroke-width="1.5" />
  <circle cx="27" cy="27" r="4" fill="#e58c9a" />
  <circle cx="41" cy="27" r="4" fill="#e4c782" />
  <circle cx="55" cy="27" r="4" fill="#8bd5a6" />
  <text class="label" x="70" y="31" fill="{theme.accent}" font-size="12" font-weight="700">CONTRIBUTION.SNAKE</text>
  <text class="label" x="742" y="31" text-anchor="end" fill="{theme.muted}" font-size="10">{snapshot.total_contributions} CONTRIBUTIONS // {escape(range_text)}</text>
{month_markup}
  <text class="label" x="35" y="75" text-anchor="end" fill="{theme.muted}" font-size="8">Mon</text>
  <text class="label" x="35" y="101" text-anchor="end" fill="{theme.muted}" font-size="8">Wed</text>
  <text class="label" x="35" y="127" text-anchor="end" fill="{theme.muted}" font-size="8">Fri</text>
  <g aria-label="365 daily GitHub contribution cells">
{_cell_markup(layout, route)}
  </g>
  <g aria-hidden="true">
{_snake_markup(route, theme)}
  </g>
</svg>
'''


def write_svgs(
    snapshot: Snapshot,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for theme in THEMES:
        path = output_dir / f"snake-{theme.name}.svg"
        svg = build_svg(snapshot, theme)
        ElementTree.fromstring(svg)
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    return tuple(written)


def _rgb(color: str) -> tuple[int, int, int]:
    if len(color) != 7 or not color.startswith("#"):
        raise ValueError(f"invalid preview color: {color}")
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


def _blend(
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
    opacity: float,
) -> tuple[int, int, int]:
    return tuple(
        round(front * opacity + back * (1.0 - opacity))
        for front, back in zip(foreground, background)
    )


class Raster:
    """Tiny standard-library RGB raster used only for inspection previews."""

    def __init__(self, width: int, height: int, color: tuple[int, int, int]):
        self.width = width
        self.height = height
        self.pixels = bytearray(color * (width * height))

    def rectangle(
        self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]
    ) -> None:
        for row in range(max(0, y), min(self.height, y + height)):
            start = max(0, x)
            end = min(self.width, x + width)
            for column in range(start, end):
                offset = (row * self.width + column) * 3
                self.pixels[offset : offset + 3] = bytes(color)

    def circle(self, x: float, y: float, radius: float, color: tuple[int, int, int]) -> None:
        left = max(0, math.floor(x - radius))
        right = min(self.width - 1, math.ceil(x + radius))
        top = max(0, math.floor(y - radius))
        bottom = min(self.height - 1, math.ceil(y + radius))
        squared = radius * radius
        for row in range(top, bottom + 1):
            for column in range(left, right + 1):
                if (column + 0.5 - x) ** 2 + (row + 0.5 - y) ** 2 <= squared:
                    offset = (row * self.width + column) * 3
                    self.pixels[offset : offset + 3] = bytes(color)

    def paste(self, other: "Raster", x: int, y: int) -> None:
        for row in range(other.height):
            destination = ((y + row) * self.width + x) * 3
            source = row * other.width * 3
            self.pixels[destination : destination + other.width * 3] = other.pixels[
                source : source + other.width * 3
            ]

    def save_png(self, path: Path) -> None:
        rows = _png_rows(self)
        png = (
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0),
            )
            + _png_chunk(b"IDAT", zlib.compress(rows, 9))
            + _png_chunk(b"IEND", b"")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def _png_rows(frame: Raster) -> bytes:
    return b"".join(
        b"\x00"
        + bytes(
            frame.pixels[
                row * frame.width * 3 : (row + 1) * frame.width * 3
            ]
        )
        for row in range(frame.height)
    )


def write_apng(
    frames: Sequence[Raster], path: Path, fps: int, play_count: int = 1
) -> None:
    """Write deterministic RGB APNG frames with standard-library tooling.

    Inspection excerpts play once so their short clip boundary cannot be
    mistaken for the seamless boundary of the full SVG animation.
    """

    if not frames:
        raise ValueError("animated preview requires at least one frame")
    if fps <= 0:
        raise ValueError("animated preview frame rate must be positive")
    if play_count < 0:
        raise ValueError("animated preview play count cannot be negative")
    width, height = frames[0].width, frames[0].height
    if any(frame.width != width or frame.height != height for frame in frames):
        raise ValueError("animated preview frames must have identical dimensions")

    chunks = [
        _png_chunk(
            b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        ),
        _png_chunk(b"acTL", struct.pack(">II", len(frames), play_count)),
    ]
    sequence = 0
    for index, frame in enumerate(frames):
        control = struct.pack(
            ">IIIIIHHBB",
            sequence,
            width,
            height,
            0,
            0,
            1,
            fps,
            0,
            0,
        )
        chunks.append(_png_chunk(b"fcTL", control))
        sequence += 1
        compressed = zlib.compress(_png_rows(frame), 9)
        if index == 0:
            chunks.append(_png_chunk(b"IDAT", compressed))
        else:
            chunks.append(
                _png_chunk(b"fdAT", struct.pack(">I", sequence) + compressed)
            )
            sequence += 1
    chunks.append(_png_chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"".join(chunks))


def render_phase(snapshot: Snapshot, theme: SnakeTheme, phase: float) -> Raster:
    """Render one representative frame without external image dependencies."""

    layout = layout_calendar(snapshot.contributions)
    route = build_route(layout)
    canvas = Raster(WIDTH, HEIGHT, _rgb(theme.background))
    canvas.rectangle(10, 10, WIDTH - 20, HEIGHT - 20, _rgb(theme.panel))
    elapsed_seconds = (phase % 1.0) * route.duration
    panel = _rgb(theme.panel)
    for cell in layout.cells:
        color = _rgb(theme.levels[LEVEL_INDEX[cell.contribution.level]])
        arrival = cell_arrival_distance(cell, layout) / SNAKE_SPEED
        opacity = cell_opacity_at_elapsed(elapsed_seconds, arrival, route)
        if opacity < 1.0:
            color = _blend(color, panel, opacity)
        x = round(GRID_X + cell.week * CELL_STEP)
        y = round(GRID_Y + cell.weekday * CELL_STEP)
        canvas.rectangle(x, y, round(CELL_SIZE), round(CELL_SIZE), color)

    snake_color = _rgb(theme.snake)
    for index in range(BODY_SEGMENTS, 0, -1):
        distance = snake_segment_distance(
            route, phase * route.duration, index
        )
        x, y = point_at_distance(route, distance)
        y += body_wave(index)
        canvas.circle(x, y, body_radius(index), snake_color)
    head_x, head_y = point_at_distance(
        route, snake_segment_distance(route, phase * route.duration, 0)
    )
    canvas.circle(head_x, head_y, 6.0, snake_color)
    canvas.circle(head_x - 2, head_y - 1.5, 1.15, _rgb(theme.eye))
    canvas.circle(head_x + 2, head_y - 1.5, 1.15, _rgb(theme.eye))
    return canvas


def write_previews(
    snapshot: Snapshot,
    output_dir: Path = DEFAULT_PREVIEW_DIR,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for theme in THEMES:
        path = output_dir / f"snake-{theme.name}-static.png"
        render_phase(snapshot, theme, 0.36).save_png(path)
        written.append(path)

    phases = (0.04, 0.29, 0.54, 0.79)
    contact = Raster(WIDTH * 2, HEIGHT * 2, _rgb(DARK_THEME.background))
    for index, phase in enumerate(phases):
        frame = render_phase(snapshot, DARK_THEME, phase)
        contact.paste(frame, (index % 2) * WIDTH, (index // 2) * HEIGHT)
    contact_path = output_dir / "snake-dark-phases.png"
    contact.save_png(contact_path)
    written.append(contact_path)

    route = build_route(layout_calendar(snapshot.contributions))
    frame_count = ANIMATION_PREVIEW_FPS * ANIMATION_PREVIEW_SECONDS
    animation_frames = tuple(
        render_phase(
            snapshot,
            DARK_THEME,
            ANIMATION_PREVIEW_START_PHASE
            + index / ANIMATION_PREVIEW_FPS / route.duration,
        )
        for index in range(frame_count)
    )
    animation_path = output_dir / "snake-dark-animation.png"
    write_apng(animation_frames, animation_path, ANIMATION_PREVIEW_FPS)
    written.append(animation_path)
    return tuple(written)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--preview-dir", type=Path, default=DEFAULT_PREVIEW_DIR)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    snapshot = load_snapshot(args.stats)
    for path in write_svgs(snapshot, args.output_dir):
        print(path)
    for path in write_previews(snapshot, args.preview_dir):
        print(path)
    layout = layout_calendar(snapshot.contributions)
    route = build_route(layout)
    print(
        f"calendar={len(snapshot.contributions)} days/{layout.week_count} weeks "
        f"snake={BODY_SEGMENTS + 1} parts duration={route.duration:.3f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
