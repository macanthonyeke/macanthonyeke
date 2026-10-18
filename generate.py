#!/usr/bin/env python3
"""Generate the self-contained terminal dashboard profile SVGs.

The publication renderer intentionally uses only the Python standard library.
It consumes the approved offline particle map and the validated GitHub data
snapshot; it never fetches data or substitutes synthetic statistics.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree


CARD_WIDTH = 1000
CARD_HEIGHT = 1130
README_WIDTH = 840
README_HEIGHT = round(CARD_HEIGHT * README_WIDTH / CARD_WIDTH)
DEFAULT_DOTS = Path("assets/dots.json")
DEFAULT_STATS = Path("assets/github-stats.json")
DEFAULT_OUTPUT_DIR = Path("assets")
DEFAULT_PREVIEW_DIR = Path("assets/previews")
USERNAME = "macanthonyeke"
TIMEZONE = "Africa/Lagos"
FONT_FAMILY = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"

ROLE = "Smart Contract Engineer | DeFi Protocol Builder"
STATUS_TITLE = "Building Tranche Protocol"
STATUS_DETAIL = "milestone-based escrow and settlement infrastructure."

TOOL_GROUPS = (
    ("EVERYDAY TOOLS", ("VS Code", "Git", "GitHub", "Foundry", "Claude Code", "Codex", "OpenZeppelin")),
    ("FRONTEND", ("Next.js", "React", "TypeScript", "Tailwind CSS", "wagmi", "viem")),
    ("BACKEND / SMART CONTRACTS", ("Solidity", "Foundry", "OpenZeppelin", "EVM", "ERC-20", "EIP-712", "ERC-1271")),
    ("DATABASE / INDEXING", ("Goldsky", "GraphQL", "Subgraphs")),
    ("CLOUD / INFRASTRUCTURE", ("Vercel", "GitHub", "Circle developer infrastructure")),
)

PROJECTS = (
    (
        "Tranche Protocol",
        ("milestone-based escrow and settlement infrastructure;", "under active development."),
    ),
    (
        "StakeLab",
        ("emission-per-second staking vault with accRewardPerShare", "and rewardDebt accounting."),
    ),
    (
        "YieldCore",
        ("staking vault with position management, time-based rewards,", "claims, and withdrawals."),
    ),
    (
        "Approval Guardian",
        ("ERC-20 approval and permission-management security project.",),
    ),
)

TRACK_RECORD = (
    ("Three iterations of staking", "vault architecture."),
    ("Solidity smart contract design", "and Foundry testing."),
    ("Active development of", "Tranche Protocol."),
    ("DeFi security and protocol", "architecture focus."),
)

CONTACT = (
    ("WEBSITE", "https://trancheprotocol.xyz"),
    ("X", "https://x.com/macanthonyeke"),
    ("GITHUB", "https://github.com/macanthonyeke"),
    ("EMAIL", "macanthonyeke@gmail.com"),
)


@dataclass(frozen=True)
class Theme:
    """Colors used by one terminal-card variant."""

    name: str
    background: str
    panel: str
    border: str
    foreground: str
    muted: str
    purple: str
    green: str
    red: str
    yellow: str


DARK_THEME = Theme(
    name="dark",
    background="#1b1a21",
    panel="#24222c",
    border="#3b3749",
    foreground="#eeeaf5",
    muted="#9b94aa",
    purple="#b18cff",
    green="#8bd5a6",
    red="#e58c9a",
    yellow="#e4c782",
)

LIGHT_THEME = Theme(
    name="light",
    background="#f5f2f8",
    panel="#fffdfd",
    border="#d9d2e3",
    foreground="#2b2435",
    muted="#6d6478",
    purple="#7047b8",
    green="#2c7a52",
    red="#ad4358",
    yellow="#8d6818",
)

THEMES = {theme.name: theme for theme in (DARK_THEME, LIGHT_THEME)}


@dataclass(frozen=True)
class ProfileStats:
    total_contributions: int
    current_streak: int
    public_repositories: int
    total_stars: int
    updated: date
    period_start: date
    period_end: date


def xml_text(value: object) -> str:
    """Escape text or an attribute value for safe insertion into SVG XML."""

    return escape(str(value), quote=True)


def _svg_number(value: object) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("SVG coordinates must be finite numbers")
    formatted = format(number, ".3f").rstrip("0").rstrip(".")
    return formatted or "0"


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def load_stats(path: Path = DEFAULT_STATS) -> ProfileStats:
    """Load validated, contiguous statistics without querying GitHub."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("statistics snapshot must contain an object")
    if payload.get("username") != USERNAME or payload.get("timezone") != TIMEZONE:
        raise ValueError("statistics snapshot belongs to an unexpected profile")
    statistics = payload.get("statistics")
    period = payload.get("period")
    contributions = payload.get("contributions")
    if not isinstance(statistics, Mapping) or not isinstance(period, Mapping):
        raise ValueError("statistics snapshot metadata is incomplete")
    if not isinstance(contributions, list):
        raise ValueError("statistics snapshot calendar is missing")

    try:
        period_start = date.fromisoformat(str(period["from"]))
        period_end = date.fromisoformat(str(period["to"]))
        generated = str(payload["generated_at"]).replace("Z", "+00:00")
        updated = datetime.fromisoformat(generated).date()
    except (KeyError, TypeError, ValueError):
        raise ValueError("statistics snapshot dates are invalid") from None

    expected_days = (period_end - period_start).days + 1
    if expected_days != 365 or period.get("days") != expected_days:
        raise ValueError("statistics snapshot must cover exactly 365 days")
    if len(contributions) != expected_days:
        raise ValueError("statistics snapshot calendar coverage is incomplete")

    count_total = 0
    for index, contribution in enumerate(contributions):
        if not isinstance(contribution, Mapping):
            raise ValueError("contribution calendar entries must be objects")
        expected = period_start + timedelta(days=index)
        try:
            actual = date.fromisoformat(str(contribution["date"]))
        except (KeyError, ValueError):
            raise ValueError("contribution calendar contains an invalid date") from None
        if actual != expected:
            raise ValueError("contribution calendar dates must be contiguous")
        count_total += _nonnegative_int(contribution.get("count"), "daily count")

    total_contributions = _nonnegative_int(statistics.get("total_contributions"), "total contributions")
    if count_total != total_contributions:
        raise ValueError("daily contribution counts do not match the total")
    return ProfileStats(
        total_contributions=total_contributions,
        current_streak=_nonnegative_int(statistics.get("current_streak"), "current streak"),
        public_repositories=_nonnegative_int(statistics.get("public_repositories"), "public repositories"),
        total_stars=_nonnegative_int(statistics.get("total_stars"), "total stars"),
        updated=updated,
        period_start=period_start,
        period_end=period_end,
    )


def load_dots(path: Path = DEFAULT_DOTS) -> tuple[Mapping[str, Any], ...]:
    """Load and validate the approved offline particle map."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    particles = payload.get("particles")
    if not isinstance(particles, list) or not 1200 <= len(particles) <= 3000:
        raise ValueError("dots.json must contain between 1200 and 3000 particles")
    if payload.get("particle_count") != len(particles):
        raise ValueError("dots.json particle_count does not match particles")
    return tuple(particles)


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("each particle must contain a six-digit hex color")
    return tuple(int(color[index : index + 2], 16) / 255.0 for index in (1, 3, 5))


def _rgb_to_hex(red: float, green: float, blue: float) -> str:
    return "#" + "".join(
        f"{round(max(0.0, min(1.0, channel)) * 255):02x}"
        for channel in (red, green, blue)
    )


def particle_style_for_theme(particle: Mapping[str, Any], theme: Theme) -> tuple[str, float, float]:
    """Apply the approved theme treatment without changing particle data."""

    color = particle.get("color")
    if not isinstance(color, str):
        raise ValueError("each particle must contain a six-digit hex color")
    red, green, blue = _hex_to_rgb(color)
    radius = float(particle["r"])
    opacity = float(particle["opacity"])
    if not all(math.isfinite(value) for value in (radius, opacity)):
        raise ValueError("particle radius and opacity must be finite")
    if theme.name != "dark":
        return color, radius, opacity

    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    opacity_detail = max(0.0, min(1.0, (opacity - 0.67) / 0.33))
    radius_detail = max(0.0, min(1.0, (radius - 1.05) / 0.78))
    source_darkness = max(0.0, min(1.0, (0.92 - luminance) / 0.92))
    derived_emphasis = max(opacity_detail, radius_detail, 0.88 * source_darkness)
    raw_emphasis = float(particle.get("emphasis", derived_emphasis))
    if not math.isfinite(raw_emphasis):
        raise ValueError("particle emphasis must be finite")
    emphasis = max(0.0, min(1.0, raw_emphasis))
    source_chroma = max(red, green, blue) - min(red, green, blue)
    in_face_detail_region = (
        0.30 <= float(particle.get("x", -1.0)) / 420.0 <= 0.84
        and 0.34 <= float(particle.get("y", -1.0)) / 420.0 <= 0.67
    )
    derived_feature = (
        min(1.0, 0.45 + 0.55 * emphasis)
        if in_face_detail_region and source_darkness >= 0.42 and source_chroma <= 0.16
        else 0.0
    )
    raw_feature = float(particle.get("feature", derived_feature))
    if not math.isfinite(raw_feature):
        raise ValueError("particle feature emphasis must be finite")
    feature = max(0.0, min(1.0, raw_feature))
    if luminance < 0.52:
        hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
        target_lightness = 0.40 + 0.13 * emphasis
        if saturation < 0.08:
            hue = 0.75
            saturation = 0.04 + 0.04 * emphasis
            target_lightness = 0.55 + 0.11 * max(emphasis, feature)
        lightness = max(lightness, target_lightness)
        red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
        color = _rgb_to_hex(red, green, blue)
        radius *= 1.0 + 0.08 * emphasis + 0.13 * feature
        opacity = min(1.0, opacity + 0.10 * emphasis + 0.08 * feature)
    return color, radius, opacity


def _portrait_css(theme: Theme) -> str:
    """Keep the approved shared 10-second portrait animation unchanged."""

    scattered_opacity = "0.23" if theme.name == "dark" else "0.18"
    return f"""
    @keyframes portrait-particle-cycle {{
      0%, 14% {{ transform: translate(var(--scatter-x), var(--scatter-y)); opacity: {scattered_opacity}; }}
      38%, 72% {{ transform: translate(0, 0); opacity: 1; }}
      88%, 100% {{ transform: translate(var(--scatter-x), var(--scatter-y)); opacity: {scattered_opacity}; }}
    }}
    .portrait-particle {{
      animation: portrait-particle-cycle 10s cubic-bezier(0.42, 0, 0.58, 1) infinite;
      transform-box: fill-box;
      transform-origin: center;
    }}
"""


def _estimate_text_width(value: str, size: float) -> float:
    """Conservative width estimate for the declared monospace fallback stack."""

    return len(value) * size * 0.64


def _text(
    value: str,
    x: float,
    y: float,
    size: float,
    fill: str,
    *,
    max_x: float,
    min_x: float = 0,
    weight: int | None = None,
    anchor: str = "start",
    css_class: str = "",
) -> str:
    width = _estimate_text_width(value, size)
    if anchor == "end":
        left, right = x - width, x
    elif anchor == "middle":
        left, right = x - width / 2, x + width / 2
    else:
        left, right = x, x + width
    top, bottom = y - size, y + size * 0.25
    if left < min_x - 0.01 or right > max_x + 0.01:
        raise ValueError(f"text does not fit its horizontal region: {value!r}")
    if top < 0 or bottom > CARD_HEIGHT:
        raise ValueError(f"text does not fit the SVG height: {value!r}")
    attributes = [
        f'x="{_svg_number(x)}"',
        f'y="{_svg_number(y)}"',
        f'fill="{fill}"',
        f'font-size="{_svg_number(size)}"',
        f'text-anchor="{anchor}"',
        f'data-layout-left="{_svg_number(left)}"',
        f'data-layout-right="{_svg_number(right)}"',
        f'data-layout-top="{_svg_number(top)}"',
        f'data-layout-bottom="{_svg_number(bottom)}"',
    ]
    attributes.append(f'class="mono{(" " + css_class) if css_class else ""}"')
    if weight is not None:
        attributes.append(f'font-weight="{weight}"')
    return f"<text {' '.join(attributes)}>{xml_text(value)}</text>"


def _rect(
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    *,
    stroke: str | None = None,
    stroke_width: float = 1,
    radius: float = 8,
    css_class: str = "",
) -> str:
    if x < 0 or y < 0 or x + width > CARD_WIDTH or y + height > CARD_HEIGHT:
        raise ValueError("rectangle exceeds dashboard bounds")
    attrs = [
        f'x="{_svg_number(x)}"',
        f'y="{_svg_number(y)}"',
        f'width="{_svg_number(width)}"',
        f'height="{_svg_number(height)}"',
        f'rx="{_svg_number(radius)}"',
        f'fill="{fill}"',
    ]
    if stroke is not None:
        attrs.extend((f'stroke="{stroke}"', f'stroke-width="{_svg_number(stroke_width)}"'))
    if css_class:
        attrs.append(f'class="{css_class}"')
    return f"<rect {' '.join(attrs)} />"


def _reveal(markup: str, delay: float) -> str:
    return f'<g class="reveal" style="--delay:{_svg_number(delay)}s">\n{markup}\n</g>'


def _section_header(theme: Theme, label: str, x: float, y: float, width: float) -> str:
    label_markup = _text(label, x, y, 12.5, theme.purple, max_x=x + width, min_x=x, weight=700)
    line_x = x + min(width - 8, _estimate_text_width(label, 12.5) + 14)
    line = _rect(line_x, y - 5, x + width - line_x, 1, theme.border, radius=0)
    return f"{label_markup}\n{line}"


def _portrait_markup(theme: Theme, particles: Sequence[Mapping[str, Any]]) -> str:
    circles: list[str] = []
    for particle in particles:
        color, radius, opacity = particle_style_for_theme(particle, theme)
        circles.append(
            '      <circle class="portrait-particle" '
            f'cx="{_svg_number(particle["x"])}" cy="{_svg_number(particle["y"])}" '
            f'r="{_svg_number(radius)}" fill="{color}" fill-opacity="{_svg_number(opacity)}" '
            f'style="--scatter-x:{_svg_number(particle["scatter_x"])}px;'
            f'--scatter-y:{_svg_number(particle["scatter_y"])}px" />'
        )
    clip_id = f"portrait-clip-{theme.name}"
    return "\n".join(
        (
            '<g aria-label="Animated 1350-particle Snoozies portrait">',
            f'  <defs><clipPath id="{clip_id}"><rect x="50" y="170" width="280" height="280" rx="9" /></clipPath></defs>',
            f'  {_rect(40, 125, 300, 350, theme.background, stroke=theme.border, stroke_width=1.5, radius=12)}',
            "  " + _text("VISUAL.MAP", 56, 153, 13, theme.purple, max_x=220, min_x=40, weight=700),
            "  " + _text(f"{len(particles)} DOTS // 10S", 324, 153, 10.5, theme.muted, max_x=330, min_x=190, anchor="end"),
            f'  {_rect(50, 170, 280, 280, theme.panel, stroke=theme.border, radius=9)}',
            f'  <g clip-path="url(#{clip_id})">',
            f'    <rect x="50" y="170" width="280" height="280" fill="{theme.background}" fill-opacity="0.45" />',
            '    <g transform="translate(50 170) scale(0.666667)" shape-rendering="geometricPrecision">',
            *circles,
            "    </g>",
            "  </g>",
            "</g>",
        )
    )


def _stats_markup(theme: Theme, stats: ProfileStats) -> str:
    markup = [
        _section_header(theme, "GITHUB.STATS", 40, 506, 300),
        _text(f"UPDATED {stats.updated.isoformat()}", 340, 506, 9.5, theme.muted, max_x=340, min_x=180, anchor="end"),
    ]
    values = (
        ("total_contributions", str(stats.total_contributions), ("365-DAY", "CONTRIBUTIONS")),
        ("current_streak", f"{stats.current_streak} days", ("CURRENT STREAK",)),
        ("public_repositories", str(stats.public_repositories), ("PUBLIC REPOS",)),
        ("total_stars", str(stats.total_stars), ("TOTAL STARS",)),
    )
    for index, (key, value, labels) in enumerate(values):
        column, row = index % 2, index // 2
        x = 40 + column * 155
        y = 522 + row * 94
        tile = [_rect(x, y, 145, 82, theme.background, stroke=theme.border, radius=10)]
        tile.append(_text(value, x + 14, y + 36, 24, theme.foreground, max_x=x + 136, min_x=x + 8, weight=700))
        label_y = y + (57 if len(labels) == 2 else 63)
        for label_index, label in enumerate(labels):
            tile.append(
                _text(
                    label,
                    x + 14,
                    label_y + label_index * 13,
                    9.8,
                    theme.muted,
                    max_x=x + 138,
                    min_x=x + 8,
                )
            )
        markup.append(
            f'<g data-stat="{key}" data-value="{xml_text(value)}">\n'
            + "\n".join(tile)
            + "\n</g>"
        )
    return "\n".join(markup)


def _track_markup(theme: Theme) -> str:
    markup = [
        _rect(40, 727, 300, 253, theme.background, stroke=theme.border, radius=12),
        _section_header(theme, "TRACK.RECORD", 56, 755, 268),
    ]
    for index, lines in enumerate(TRACK_RECORD):
        y = 791 + index * 47
        markup.append(f'<circle cx="58" cy="{y - 4}" r="3" fill="{theme.purple}" />')
        markup.append(_text(lines[0], 72, y, 12.5, theme.foreground, max_x=325, min_x=68))
        markup.append(_text(lines[1], 72, y + 18, 12.5, theme.muted, max_x=325, min_x=68))
    return "\n".join(markup)


def _identity_markup(theme: Theme) -> str:
    return "\n".join(
        (
            _rect(366, 125, 594, 171, theme.background, stroke=theme.border, radius=12),
            _section_header(theme, "ENGINEERING.IDENTITY", 382, 153, 562),
            _text("ROLE", 382, 182, 10.5, theme.muted, max_x=450, min_x=380, weight=700),
            _text(ROLE, 382, 206, 15.5, theme.foreground, max_x=944, min_x=380, weight=700),
            _text("STATUS", 382, 235, 10.5, theme.muted, max_x=450, min_x=380, weight=700),
            _text(STATUS_TITLE, 382, 262, 19, theme.purple, max_x=944, min_x=380, weight=700),
            _text(f"— {STATUS_DETAIL}", 382, 283, 13.5, theme.foreground, max_x=944, min_x=380),
        )
    )


def _pill_width(label: str) -> float:
    return _estimate_text_width(label, 12.25) + 20


def _pill_markup(theme: Theme, label: str, x: float, y: float) -> str:
    width = _pill_width(label)
    if x + width > 950.01:
        raise ValueError(f"technology pill overflows its row: {label}")
    return "\n".join(
        (
            _rect(x, y, width, 25, theme.background, stroke=theme.border, radius=12.5),
            _text(label, x + 10, y + 17, 12.25, theme.foreground, max_x=x + width - 8, min_x=x + 8),
        )
    )


def _tools_markup(theme: Theme) -> str:
    markup = [_section_header(theme, "TOOLCHAIN", 366, 324, 594)]
    for row, (label, tools) in enumerate(TOOL_GROUPS):
        label_y = 349 + row * 53
        pill_y = label_y + 9
        markup.append(_text(label, 374, label_y, 10.5, theme.muted, max_x=950, min_x=370, weight=700))
        x = 374.0
        for tool in tools:
            markup.append(_pill_markup(theme, tool, x, pill_y))
            x += _pill_width(tool) + 6
    return "\n".join(markup)


def _projects_markup(theme: Theme) -> str:
    markup = [_section_header(theme, "FEATURED.PROJECTS", 366, 625, 594)]
    for index, (title, lines) in enumerate(PROJECTS):
        y = 642 + index * 78
        border = theme.purple if index == 0 else theme.border
        markup.append(_rect(374, y, 578, 70, theme.background, stroke=border, stroke_width=1.5 if index == 0 else 1, radius=9))
        markup.append(_text(title, 390, y + 23, 14, theme.purple if index == 0 else theme.foreground, max_x=930, min_x=386, weight=700))
        if index == 0:
            markup.append(_text("ACTIVE DEVELOPMENT", 938, y + 22, 9.5, theme.green, max_x=938, min_x=780, anchor="end", weight=700))
        for line_index, line in enumerate(lines):
            markup.append(_text(line, 390, y + 44 + line_index * 16, 12, theme.muted, max_x=938, min_x=386))
    return "\n".join(markup)


def _contact_markup(theme: Theme) -> str:
    markup = [_section_header(theme, "CONTACT", 366, 975, 594)]
    for index, (label, value) in enumerate(CONTACT):
        y = 1000 + index * 22
        leaders = "." * max(3, 12 - len(label))
        markup.append(_text(f"{label} {leaders} {value}", 374, y, 12.5, theme.foreground if index == 3 else theme.muted, max_x=950, min_x=370))
    return "\n".join(markup)


def build_svg(
    theme: Theme,
    *,
    particles: Sequence[Mapping[str, Any]] | None = None,
    stats: ProfileStats | None = None,
    title: str = "macanthonyeke / engineering profile",
    width: int = CARD_WIDTH,
    height: int = CARD_HEIGHT,
) -> str:
    """Build one deterministic, self-contained terminal dashboard SVG."""

    if width <= 0 or height <= 0:
        raise ValueError("SVG dimensions must be positive")
    particles = load_dots() if particles is None else particles
    stats = load_stats() if stats is None else stats
    if len(particles) != 1350:
        raise ValueError("the canonical dashboard requires the approved 1350-particle map")

    prompt = "macanthonyeke@github:~$ ready"
    prompt_width = _estimate_text_width(prompt, 13.5)
    description = (
        f"Terminal engineering profile for {USERNAME}. {ROLE}. "
        f"{STATUS_TITLE} — {STATUS_DETAIL} Updated {stats.updated.isoformat()}."
    )
    portrait = _reveal(_portrait_markup(theme, particles), 0.16)
    statistics = _reveal(_stats_markup(theme, stats), 0.32)
    identity = _reveal(_identity_markup(theme), 0.20)
    tools = _reveal(_tools_markup(theme), 0.40)
    projects = _reveal(_projects_markup(theme), 0.58)
    track = _reveal(_track_markup(theme), 0.72)
    contact = _reveal(_contact_markup(theme), 0.86)
    footer = _reveal(
        "\n".join(
            (
                _text(prompt, 40, 1100, 13.5, theme.purple, max_x=330, min_x=40, weight=700),
                f'<rect class="cursor" x="{_svg_number(40 + prompt_width + 8)}" y="1086" width="9" height="18" rx="1" fill="{theme.purple}" />',
            )
        ),
        1.02,
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" role="img"
     aria-label="Terminal engineering profile for {USERNAME}">
  <title>{xml_text(title)}</title>
  <desc>{xml_text(description)}</desc>
  <style>
    .mono {{ font-family: {FONT_FAMILY}; }}
    @keyframes cursor-blink {{
      0%, 49% {{ opacity: 1; }}
      50%, 100% {{ opacity: 0; }}
    }}
    .cursor {{ animation: cursor-blink 0.9s steps(1, end) infinite; }}
    @keyframes reveal-content {{
      from {{ opacity: 0; transform: translateY(5px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .reveal {{ animation: reveal-content 0.55s ease-out var(--delay) both; }}
{_portrait_css(theme)}
    @media (prefers-reduced-motion: reduce) {{
      .reveal, .portrait-particle, .cursor {{
        animation: none !important;
        opacity: 1 !important;
        transform: none !important;
      }}
    }}
  </style>

  {_rect(0, 0, CARD_WIDTH, CARD_HEIGHT, theme.background, radius=18)}
  {_rect(16, 16, CARD_WIDTH - 32, CARD_HEIGHT - 32, theme.panel, stroke=theme.border, stroke_width=2, radius=14)}
  <circle cx="40" cy="40" r="5" fill="{theme.red}" />
  <circle cx="58" cy="40" r="5" fill="{theme.yellow}" />
  <circle cx="76" cy="40" r="5" fill="{theme.green}" />
  {_text("terminal // profile.dashboard", 100, 45, 13, theme.muted, max_x=600, min_x=98)}
  {_text("SVG // OFFLINE SNAPSHOT", 960, 45, 10.5, theme.muted, max_x=960, min_x=720, anchor="end")}
  {_reveal(_text("macanthonyeke@github:~$ whoami", 40, 91, 15, theme.purple, max_x=500, min_x=40, weight=700), 0.04)}
  {_rect(40, 108, 920, 1, theme.border, radius=0)}

  {portrait}
  {statistics}
  {track}
  {identity}
  {tools}
  {projects}
  {contact}
  {footer}
</svg>
'''


def build_themes(
    themes: Iterable[Theme] = THEMES.values(),
    *,
    particles: Sequence[Mapping[str, Any]] | None = None,
    stats: ProfileStats | None = None,
) -> dict[str, str]:
    particles = load_dots() if particles is None else particles
    stats = load_stats() if stats is None else stats
    return {theme.name: build_svg(theme, particles=particles, stats=stats) for theme in themes}


def write_svgs(svgs: Mapping[str, str], output_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for theme_name, svg in svgs.items():
        ElementTree.fromstring(svg)
        path = output_dir / f"{theme_name}.svg"
        path.write_text(svg, encoding="utf-8")
        written.append(path)
    return tuple(written)


def _resize_svg(svg: str, width: int, height: int) -> str:
    if width == CARD_WIDTH and height == CARD_HEIGHT:
        ElementTree.fromstring(svg)
        return svg
    resized = re.sub(
        r'<svg xmlns="http://www.w3.org/2000/svg" width="\d+" height="\d+"',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"',
        svg,
        count=1,
    )
    if resized == svg:
        raise ValueError("unable to resize SVG preview")
    ElementTree.fromstring(resized)
    return resized


def write_previews(svgs: Mapping[str, str], preview_dir: Path = DEFAULT_PREVIEW_DIR) -> tuple[Path, ...]:
    """Write full-size and realistic README-width vector previews."""

    preview_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for theme_name, svg in svgs.items():
        for label, width, height in (
            ("full", CARD_WIDTH, CARD_HEIGHT),
            ("readme", README_WIDTH, README_HEIGHT),
        ):
            path = preview_dir / f"dashboard-{theme_name}-{label}.svg"
            path.write_text(_resize_svg(svg, width, height), encoding="utf-8")
            written.append(path)
    return tuple(written)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--preview-dir", type=Path, default=DEFAULT_PREVIEW_DIR)
    parser.add_argument("--dots", type=Path, default=DEFAULT_DOTS)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--theme", choices=("light", "dark", "both"), default="both")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    themes = THEMES.values() if args.theme == "both" else (THEMES[args.theme],)
    particles = load_dots(args.dots)
    stats = load_stats(args.stats)
    svgs = build_themes(themes, particles=particles, stats=stats)
    for path in write_svgs(svgs, args.output_dir):
        print(path)
    for path in write_previews(svgs, args.preview_dir):
        print(path)
    print(
        f"dashboard={CARD_WIDTH}x{CARD_HEIGHT} readme={README_WIDTH}x{README_HEIGHT} "
        f"particles={len(particles)} updated={stats.updated.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
