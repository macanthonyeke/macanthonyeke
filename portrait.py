#!/usr/bin/env python3
"""Build a deterministic particle map from the local Snoozies NFT.

Pillow and NumPy are imported lazily and are used only by the offline image
processing path.  The resulting ``assets/dots.json`` contains all target and
scatter coordinates, colors, sizes, and source metadata needed by the
standard-library SVG generator.  No network access is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_SOURCE = Path("assets/source/snoozies-nft.jpg")
ALTERNATE_SOURCE = Path("assets/source/Snoozies_nft.jpg")
DEFAULT_DOTS_OUTPUT = Path("assets/dots.json")
DEFAULT_PARTICLE_COUNT = 2400
DEFAULT_CANVAS_SIZE = 420
DEFAULT_PREVIEW_DIR = Path("assets/previews")
README_PORTRAIT_SIZE = 231
INSPECTION_PREVIEW_SIZE = 840
DEFAULT_VARIANTS_DIR = Path("assets/variants")


@dataclass(frozen=True)
class PortraitVariant:
    """Sampling and sizing controls for one comparison candidate."""

    key: str
    label: str
    count: int
    crop_inset: float
    feature_fraction: float
    edge_fraction: float
    detail_fraction: float
    radius_base: float
    radius_detail: float
    radius_feature: float
    opacity_base: float
    opacity_detail: float


VARIANT_A = PortraitVariant(
    key="variant-a",
    label="Variant A — dense optimized particles",
    count=2400,
    crop_inset=0.10,
    feature_fraction=0.18,
    edge_fraction=0.28,
    detail_fraction=0.18,
    radius_base=1.12,
    radius_detail=0.92,
    radius_feature=0.62,
    opacity_base=0.74,
    opacity_detail=0.26,
)

VARIANT_B = PortraitVariant(
    key="variant-b",
    label="Variant B — fewer, larger particles",
    count=1350,
    crop_inset=0.10,
    feature_fraction=0.27,
    edge_fraction=0.30,
    detail_fraction=0.16,
    radius_base=1.52,
    radius_detail=1.20,
    radius_feature=0.92,
    opacity_base=0.80,
    opacity_detail=0.20,
)

PORTRAIT_VARIANTS = (VARIANT_A, VARIANT_B)
PORTRAIT_VARIANTS_BY_KEY = {variant.key: variant for variant in PORTRAIT_VARIANTS}


@dataclass(frozen=True)
class Particle:
    """One particle in target and scattered coordinate space."""

    x: float
    y: float
    radius: float
    opacity: float
    color: str
    scatter_x: float
    scatter_y: float

    def as_dict(self) -> dict[str, object]:
        return {
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "r": round(self.radius, 3),
            "opacity": round(self.opacity, 3),
            "color": self.color,
            "scatter_x": round(self.scatter_x, 3),
            "scatter_y": round(self.scatter_y, 3),
        }


def _processing_dependencies():
    """Import only the permitted offline image-processing dependencies."""

    try:
        import numpy as np  # type: ignore
        from PIL import Image, ImageOps  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "portrait processing requires Pillow and NumPy; install them in "
            "the local processing environment"
        ) from exc
    return Image, ImageOps, np


def resolve_source_path(image_path: Path = DEFAULT_SOURCE) -> Path:
    """Resolve the requested source, tolerating the supplied case variation."""

    if image_path.exists():
        return image_path
    if image_path.name == DEFAULT_SOURCE.name and ALTERNATE_SOURCE.exists():
        return ALTERNATE_SOURCE
    raise FileNotFoundError(f"Snoozies source image not found: {image_path}")


def sha256_file(image_path: Path) -> str:
    digest = hashlib.sha256()
    with image_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed_for_image(image_path: Path) -> int:
    """Derive a stable random seed from source bytes, not filesystem casing."""

    return int.from_bytes(bytes.fromhex(sha256_file(image_path))[:8], "big")


def seed_for_path(image_path: Path) -> int:
    """Backward-compatible deterministic seed helper."""

    if image_path.exists():
        return seed_for_image(image_path)
    digest = hashlib.sha256(str(image_path).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _foreground_scores(pixels, np):
    """Return artwork mask and detail scores without face detection.

    The JPEG has a near-uniform pink background.  Background color distance
    isolates the illustrated character; local luminance gradients and
    darkness then prioritize outlines, eyes, flowers, scarf edges, and other
    high-contrast artwork details.  No human-face detector or facial landmark
    model is used.
    """

    height, width, _ = pixels.shape
    rgb = pixels.astype(np.float32)
    border_size = max(4, min(height, width) // 32)
    border = np.concatenate(
        (
            rgb[:border_size, :border_size].reshape(-1, 3),
            rgb[:border_size, -border_size:].reshape(-1, 3),
            rgb[-border_size:, :border_size].reshape(-1, 3),
            rgb[-border_size:, -border_size:].reshape(-1, 3),
        ),
        axis=0,
    )
    background = np.median(border, axis=0)
    color_distance = np.sqrt(((rgb - background) ** 2).sum(axis=2))

    luminance = (
        0.2126 * rgb[:, :, 0]
        + 0.7152 * rgb[:, :, 1]
        + 0.0722 * rgb[:, :, 2]
    ) / 255.0
    horizontal = np.zeros_like(luminance)
    vertical = np.zeros_like(luminance)
    horizontal[:, 1:] = np.abs(luminance[:, 1:] - luminance[:, :-1])
    vertical[1:, :] = np.abs(luminance[1:, :] - luminance[:-1, :])
    edge_strength = np.clip((horizontal + vertical) * 2.6, 0.0, 1.0)
    darkness = np.clip((0.92 - luminance) / 0.92, 0.0, 1.0)
    chroma = (rgb.max(axis=2) - rgb.min(axis=2)) / 255.0

    # A generous threshold keeps the dark outline and pastel character while
    # excluding the flat pink canvas around the artwork.
    foreground = color_distance > 24.0
    base = foreground.astype(np.float32)
    overall = base * (0.46 + 0.28 * edge_strength + 0.16 * darkness + 0.10 * chroma)
    detail = base * (0.20 + 0.52 * edge_strength + 0.20 * darkness + 0.08 * chroma)
    return foreground, edge_strength, darkness, overall, detail


def _nft_feature_scores(pixels, foreground, edge_strength, darkness, np):
    """Score Snoozies facial marks using an artwork-specific region of interest.

    This is deliberately not face detection. The fixed region corresponds to
    the eyes, eyebrows, mouth, and inner face boundary in this one supplied
    illustration after its deterministic crop.
    """

    height, width, _ = pixels.shape
    y_grid, x_grid = np.ogrid[:height, :width]
    region = (
        (x_grid >= width * 0.30)
        & (x_grid <= width * 0.84)
        & (y_grid >= height * 0.34)
        & (y_grid <= height * 0.67)
    )
    rgb = pixels.astype(np.float32) / 255.0
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    neutral_detail = np.clip((0.22 - chroma) / 0.22, 0.0, 1.0)
    score = (
        0.46 * edge_strength
        + 0.42 * darkness
        + 0.12 * neutral_detail
    )
    return foreground.astype(np.float32) * region.astype(np.float32) * score


def _weighted_choice(rng, np, candidates, weights, count):
    if count <= 0 or len(candidates) == 0:
        return np.array([], dtype=np.int64)
    count = min(int(count), len(candidates))
    weights = np.asarray(weights, dtype=np.float64)
    weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)
    if weights.sum() <= 0:
        probabilities = None
    else:
        probabilities = weights / weights.sum()
    return rng.choice(candidates, size=count, replace=False, p=probabilities)


def _clamped_scatter(rng, np, x: float, y: float, canvas_size: int) -> tuple[float, float]:
    angle = float(rng.uniform(0.0, math.tau))
    distance = float(rng.uniform(44.0, 132.0))
    offset_x = math.cos(angle) * distance
    offset_y = math.sin(angle) * distance

    # Keep the scattered state inside the framed VISUAL.MAP panel so particles
    # cannot cover adjacent terminal text.
    min_x = 10.0 - x
    max_x = canvas_size - 10.0 - x
    min_y = 10.0 - y
    max_y = canvas_size - 10.0 - y
    return (
        round(max(min_x, min(max_x, offset_x)), 3),
        round(max(min_y, min(max_y, offset_y)), 3),
    )


def _bounded_scatter(rng, x: float, y: float, canvas_size: int) -> tuple[float, float]:
    """Scatter within the panel without accumulating dots on its boundary."""

    angle = float(rng.uniform(0.0, math.tau))
    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    if x < 10.0 and direction_x < 0.0:
        direction_x = -direction_x
    elif x > canvas_size - 10.0 and direction_x > 0.0:
        direction_x = -direction_x
    if y < 10.0 and direction_y < 0.0:
        direction_y = -direction_y
    elif y > canvas_size - 10.0 and direction_y > 0.0:
        direction_y = -direction_y
    limits: list[float] = [132.0]
    if abs(direction_x) > 1e-9:
        edge_x = canvas_size - 10.0 if direction_x > 0 else 10.0
        limits.append((edge_x - x) / direction_x)
    if abs(direction_y) > 1e-9:
        edge_y = canvas_size - 10.0 if direction_y > 0 else 10.0
        limits.append((edge_y - y) / direction_y)
    upper_distance = max(4.0, min(limits))
    lower_distance = min(44.0, upper_distance * 0.58)
    distance = float(rng.uniform(lower_distance, upper_distance))
    return (
        round(direction_x * distance, 3),
        round(direction_y * distance, 3),
    )


def sample_particles(
    image_path: Path,
    *,
    count: int = DEFAULT_PARTICLE_COUNT,
    canvas_size: int = DEFAULT_CANVAS_SIZE,
    seed: int | None = None,
    variant: PortraitVariant | None = None,
) -> tuple[Particle, ...]:
    """Sample a recognizable, deterministic artwork particle field."""

    if variant is not None:
        count = variant.count
    if not 1200 <= count <= 3000:
        raise ValueError("particle count must be between 1200 and 3000")
    if canvas_size <= 0:
        raise ValueError("canvas_size must be positive")

    Image, ImageOps, np = _processing_dependencies()
    source_path = resolve_source_path(image_path)
    with Image.open(source_path) as source:
        source_rgb = source.convert("RGB")
        crop_inset = variant.crop_inset if variant is not None else 0.0
        if crop_inset:
            if not 0.0 <= crop_inset < 0.4:
                raise ValueError("crop inset must be between 0 and 0.4")
            width, height = source_rgb.size
            source_rgb = source_rgb.crop(
                (
                    round(width * crop_inset),
                    round(height * crop_inset),
                    round(width * (1.0 - crop_inset)),
                    round(height * (1.0 - crop_inset)),
                )
            )
        image = ImageOps.fit(
            source_rgb,
            (canvas_size, canvas_size),
            method=Image.Resampling.LANCZOS,
        )

    pixels = np.asarray(image)
    foreground, edge_strength, darkness, overall, detail = _foreground_scores(pixels, np)
    feature_scores = _nft_feature_scores(
        pixels, foreground, edge_strength, darkness, np
    )
    candidate_mask = foreground.ravel()
    candidate_indices = np.flatnonzero(candidate_mask)
    if len(candidate_indices) < count:
        raise ValueError("source artwork has fewer visible pixels than requested particles")

    actual_seed = seed if seed is not None else seed_for_image(source_path)
    rng = np.random.default_rng(actual_seed)
    selected = np.zeros(canvas_size * canvas_size, dtype=bool)

    edge_flat = edge_strength.ravel()
    detail_flat = detail.ravel()
    overall_flat = overall.ravel()
    feature_flat = feature_scores.ravel()
    feature_fraction = variant.feature_fraction if variant is not None else 0.0
    if feature_fraction:
        visible_feature_scores = feature_flat[candidate_indices]
        positive_features = candidate_indices[visible_feature_scores > 0]
        feature_threshold = float(np.quantile(feature_flat[positive_features], 0.62))
        feature_candidates = positive_features[
            feature_flat[positive_features] >= feature_threshold
        ]
        feature_count = min(int(count * feature_fraction), len(feature_candidates))
        chosen_features = _weighted_choice(
            rng,
            np,
            feature_candidates,
            feature_flat[feature_candidates] + 0.18,
            feature_count,
        )
        selected[chosen_features] = True

    foreground_edges = edge_flat[candidate_indices]
    edge_threshold = float(np.quantile(foreground_edges, 0.68))
    edge_candidates = candidate_indices[foreground_edges >= edge_threshold]
    edge_candidates = edge_candidates[~selected[edge_candidates]]
    edge_fraction = variant.edge_fraction if variant is not None else 0.28
    edge_count = min(int(count * edge_fraction), len(edge_candidates))
    chosen_edge = _weighted_choice(
        rng,
        np,
        edge_candidates,
        edge_flat[edge_candidates] + 0.15,
        edge_count,
    )
    selected[chosen_edge] = True

    detail_candidates = candidate_indices[~selected[candidate_indices]]
    detail_scores = detail_flat[detail_candidates]
    detail_threshold = float(np.quantile(detail_scores, 0.62))
    detail_candidates = detail_candidates[detail_scores >= detail_threshold]
    detail_fraction = variant.detail_fraction if variant is not None else 0.20
    detail_count = min(int(count * detail_fraction), len(detail_candidates))
    chosen_detail = _weighted_choice(
        rng,
        np,
        detail_candidates,
        detail_flat[detail_candidates] + 0.15,
        detail_count,
    )
    selected[chosen_detail] = True

    remaining = candidate_indices[~selected[candidate_indices]]
    chosen_remaining = _weighted_choice(
        rng,
        np,
        remaining,
        overall_flat[remaining] + 0.08,
        count - int(selected.sum()),
    )
    selected[chosen_remaining] = True

    selected_indices = np.flatnonzero(selected)
    selected_indices = sorted(
        selected_indices.tolist(),
        key=lambda index: (index // canvas_size, index % canvas_size),
    )
    scatter_rng = np.random.default_rng(actual_seed ^ 0x5A17C0DE)
    particles: list[Particle] = []

    for index in selected_indices:
        y, x = divmod(index, canvas_size)
        red, green, blue = (int(channel) for channel in pixels[y, x])
        edge_value = float(edge_strength[y, x])
        dark_value = float(darkness[y, x])
        feature_value = min(1.0, float(feature_scores[y, x]))
        detail_value = min(1.0, 0.52 * edge_value + 0.48 * dark_value)
        if variant is None:
            radius = 1.05 + 0.78 * (0.42 * edge_value + 0.58 * dark_value)
            opacity = 0.67 + 0.33 * min(
                1.0, 0.55 * edge_value + 0.45 * dark_value
            )
        else:
            radius = (
                variant.radius_base
                + variant.radius_detail * detail_value
                + variant.radius_feature * feature_value
            )
            opacity = min(
                1.0,
                variant.opacity_base
                + variant.opacity_detail * max(detail_value, feature_value),
            )
        if variant is None:
            scatter_x, scatter_y = _clamped_scatter(
                scatter_rng, np, x, y, canvas_size
            )
        else:
            scatter_x, scatter_y = _bounded_scatter(
                scatter_rng, x, y, canvas_size
            )
        particles.append(
            Particle(
                x=float(x),
                y=float(y),
                radius=radius,
                opacity=opacity,
                color=f"#{red:02x}{green:02x}{blue:02x}",
                scatter_x=scatter_x,
                scatter_y=scatter_y,
            )
        )

    if len(particles) != count:
        raise RuntimeError(f"expected {count} particles, selected {len(particles)}")
    return tuple(particles)


def dots_payload(
    image_path: Path,
    particles: Iterable[Particle],
    *,
    canvas_size: int,
    seed: int,
    variant: PortraitVariant | None = None,
) -> dict[str, object]:
    source_path = resolve_source_path(image_path)
    Image, _, _ = _processing_dependencies()
    with Image.open(source_path) as source:
        source_size = list(source.size)
    particle_list = [particle.as_dict() for particle in particles]
    payload: dict[str, object] = {
        "version": 1,
        "algorithm": (
            "background-distance-nft-features-v2"
            if variant is not None
            else "background-distance-edge-detail-v1"
        ),
        "source": {
            "path": (Path("assets/source") / source_path.name).as_posix(),
            "sha256": sha256_file(source_path),
            "size": source_size,
        },
        "seed": seed,
        "canvas": {"width": canvas_size, "height": canvas_size},
        "particle_count": len(particle_list),
        "particles": particle_list,
    }
    if variant is not None:
        payload["variant"] = {
            "key": variant.key,
            "label": variant.label,
            "crop_inset": variant.crop_inset,
            "feature_fraction": variant.feature_fraction,
            "edge_fraction": variant.edge_fraction,
            "detail_fraction": variant.detail_fraction,
        }
    return payload


def write_dots_json(
    image_path: Path = DEFAULT_SOURCE,
    output_path: Path = DEFAULT_DOTS_OUTPUT,
    *,
    count: int = DEFAULT_PARTICLE_COUNT,
    canvas_size: int = DEFAULT_CANVAS_SIZE,
    seed: int | None = None,
    variant: PortraitVariant | None = None,
) -> tuple[Path, int]:
    """Generate and persist the deterministic particle data."""

    source_path = resolve_source_path(image_path)
    actual_seed = seed if seed is not None else seed_for_image(source_path)
    particles = sample_particles(
        source_path,
        count=count,
        canvas_size=canvas_size,
        seed=actual_seed,
        variant=variant,
    )
    payload = dots_payload(
        source_path,
        particles,
        canvas_size=canvas_size,
        seed=actual_seed,
        variant=variant,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return output_path, len(particles)


def particles_to_svg(
    particles: Iterable[Particle],
    *,
    width: int = DEFAULT_CANVAS_SIZE,
    height: int = DEFAULT_CANVAS_SIZE,
    background: str = "#1b1a21",
    title: str = "Snoozies particle portrait",
) -> str:
    """Serialize an animated standalone portrait for offline inspection."""

    particle_markup = []
    for particle in particles:
        particle_markup.append(
            "    <circle class=\"portrait-particle\" "
            f'cx="{particle.x:.3f}" cy="{particle.y:.3f}" '
            f'r="{particle.radius:.3f}" fill="{escape(particle.color, quote=True)}" '
            f'fill-opacity="{particle.opacity:.3f}" '
            f'style="--scatter-x:{particle.scatter_x:.3f}px;--scatter-y:{particle.scatter_y:.3f}px" />'
        )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title, quote=True)}">
  <title>{escape(title)}</title>
  <style>
    @keyframes portrait-particle-cycle {{
      0%, 14% {{ transform: translate(var(--scatter-x), var(--scatter-y)); opacity: 0.18; }}
      38%, 72% {{ transform: translate(0, 0); opacity: 1; }}
      88%, 100% {{ transform: translate(var(--scatter-x), var(--scatter-y)); opacity: 0.18; }}
    }}
    .portrait-particle {{
      animation: portrait-particle-cycle 10s cubic-bezier(0.42, 0, 0.58, 1) infinite;
      transform-box: fill-box;
      transform-origin: center;
    }}
    @media (prefers-reduced-motion: reduce) {{
      .portrait-particle {{ animation: none !important; opacity: 1 !important; transform: none !important; }}
    }}
  </style>
  <rect width="{width}" height="{height}" fill="{escape(background, quote=True)}" />
{chr(10).join(particle_markup)}
</svg>
'''


def _composite_rgb(
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
    opacity: float,
) -> tuple[int, int, int]:
    alpha = max(0.0, min(1.0, opacity))
    return tuple(
        round(front * alpha + back * (1.0 - alpha))
        for front, back in zip(foreground, background)
    )


def _preview_rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


def _render_particle_preview(
    particles: Iterable[Mapping[str, Any]],
    *,
    theme,
    state: str,
    output_size: int,
    output_path: Path,
) -> None:
    """Rasterize a static animation state for local visual inspection."""

    Image, _, _ = _processing_dependencies()
    from PIL import ImageDraw  # type: ignore

    from generate import particle_style_for_theme

    if state not in {"assembled", "scattered"}:
        raise ValueError("preview state must be assembled or scattered")

    # Four-times supersampling makes sub-pixel README-sized dots inspectable
    # without changing their geometry in the generated SVG.
    oversample = 2 if output_size >= INSPECTION_PREVIEW_SIZE else 4
    raster_size = output_size * oversample
    scale = raster_size / DEFAULT_CANVAS_SIZE
    panel_rgb = _preview_rgb(theme.panel)
    background_rgb = _preview_rgb(theme.background)
    map_rgb = _composite_rgb(background_rgb, panel_rgb, 0.45)
    image = Image.new("RGB", (raster_size, raster_size), map_rgb)
    draw = ImageDraw.Draw(image)
    state_opacity = 1.0 if state == "assembled" else (0.23 if theme.name == "dark" else 0.18)

    for particle in particles:
        color, radius, opacity = particle_style_for_theme(particle, theme)
        x = float(particle["x"])
        y = float(particle["y"])
        if state == "scattered":
            x += float(particle["scatter_x"])
            y += float(particle["scatter_y"])
        fill = _composite_rgb(
            _preview_rgb(color), map_rgb, opacity * state_opacity
        )
        scaled_radius = max(0.5, radius * scale)
        center_x = x * scale
        center_y = y * scale
        draw.ellipse(
            (
                center_x - scaled_radius,
                center_y - scaled_radius,
                center_x + scaled_radius,
                center_y + scaled_radius,
            ),
            fill=fill,
        )

    if oversample > 1:
        image = image.resize(
            (output_size, output_size), resample=Image.Resampling.LANCZOS
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)


def render_validation_previews(
    dots_path: Path = DEFAULT_DOTS_OUTPUT,
    output_dir: Path = DEFAULT_PREVIEW_DIR,
) -> tuple[Path, ...]:
    """Write assembled, scattered, and actual-size light/dark PNG previews."""

    from generate import DARK_THEME, LIGHT_THEME

    payload = json.loads(dots_path.read_text(encoding="utf-8"))
    particles = payload.get("particles")
    if not isinstance(particles, list):
        raise ValueError("dots.json does not contain a particle list")

    written: list[Path] = []
    for theme in (DARK_THEME, LIGHT_THEME):
        for state in ("assembled", "scattered"):
            path = output_dir / f"portrait-{state}-{theme.name}.png"
            _render_particle_preview(
                particles,
                theme=theme,
                state=state,
                output_size=INSPECTION_PREVIEW_SIZE,
                output_path=path,
            )
            written.append(path)
        actual_path = output_dir / f"portrait-readme-{theme.name}.png"
        _render_particle_preview(
            particles,
            theme=theme,
            state="assembled",
            output_size=README_PORTRAIT_SIZE,
            output_path=actual_path,
        )
        written.append(actual_path)
    return tuple(written)


def render_variant_previews(
    dots_path: Path,
    output_dir: Path,
) -> tuple[Path, ...]:
    """Write the six assembled/scattered comparison previews for one variant."""

    from generate import DARK_THEME, LIGHT_THEME

    payload = json.loads(dots_path.read_text(encoding="utf-8"))
    particles = payload.get("particles")
    if not isinstance(particles, list):
        raise ValueError("dots.json does not contain a particle list")

    written: list[Path] = []
    for theme in (DARK_THEME, LIGHT_THEME):
        large_path = output_dir / f"assembled-{theme.name}-large.png"
        _render_particle_preview(
            particles,
            theme=theme,
            state="assembled",
            output_size=INSPECTION_PREVIEW_SIZE,
            output_path=large_path,
        )
        written.append(large_path)
        for state in ("assembled", "scattered"):
            readme_path = output_dir / f"{state}-{theme.name}-readme.png"
            _render_particle_preview(
                particles,
                theme=theme,
                state=state,
                output_size=README_PORTRAIT_SIZE,
                output_path=readme_path,
            )
            written.append(readme_path)
    return tuple(written)


def write_comparison_sheet(
    source_path: Path,
    variants_dir: Path,
) -> Path:
    """Place the original and four README-size candidates side by side."""

    Image, ImageOps, _ = _processing_dependencies()
    from PIL import ImageDraw  # type: ignore

    source_path = resolve_source_path(source_path)
    tile_size = README_PORTRAIT_SIZE
    margin = 18
    caption_height = 34
    labels_and_paths = (
        ("Original artwork", source_path),
        ("Variant A / dark", variants_dir / "variant-a/previews/assembled-dark-readme.png"),
        ("Variant A / light", variants_dir / "variant-a/previews/assembled-light-readme.png"),
        ("Variant B / dark", variants_dir / "variant-b/previews/assembled-dark-readme.png"),
        ("Variant B / light", variants_dir / "variant-b/previews/assembled-light-readme.png"),
    )
    width = margin + len(labels_and_paths) * (tile_size + margin)
    height = margin + caption_height + tile_size + margin
    sheet = Image.new("RGB", (width, height), "#16141c")
    draw = ImageDraw.Draw(sheet)

    for index, (label, path) in enumerate(labels_and_paths):
        x = margin + index * (tile_size + margin)
        draw.text((x, margin + 8), label, fill="#eeeaf5")
        with Image.open(path) as item:
            tile = ImageOps.fit(
                item.convert("RGB"),
                (tile_size, tile_size),
                method=Image.Resampling.LANCZOS,
            )
        sheet.paste(tile, (x, margin + caption_height))

    destination = variants_dir / "portrait-comparison.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG", optimize=True)
    return destination


def generate_variant_comparison(
    image_path: Path = DEFAULT_SOURCE,
    output_dir: Path = DEFAULT_VARIANTS_DIR,
) -> tuple[Path, ...]:
    """Generate data, SVGs, static previews, and the A/B comparison sheet."""

    from generate import load_dots, write_previews

    source_path = resolve_source_path(image_path)
    written: list[Path] = []
    for variant in PORTRAIT_VARIANTS:
        variant_dir = output_dir / variant.key
        dots_path = variant_dir / "dots.json"
        write_dots_json(
            source_path,
            dots_path,
            canvas_size=DEFAULT_CANVAS_SIZE,
            variant=variant,
        )
        written.append(dots_path)
        particles = load_dots(dots_path)
        written.extend(write_previews(variant_dir, particles=particles))
        written.extend(render_variant_previews(dots_path, variant_dir / "previews"))

    written.append(write_comparison_sheet(source_path, output_dir))
    return tuple(written)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_DOTS_OUTPUT)
    parser.add_argument("--count", type=int, default=DEFAULT_PARTICLE_COUNT)
    parser.add_argument("--canvas-size", type=int, default=DEFAULT_CANVAS_SIZE)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--variant",
        choices=tuple(PORTRAIT_VARIANTS_BY_KEY),
        default=None,
        help="optional approved comparison profile to use for canonical output",
    )
    parser.add_argument(
        "--preview-dir",
        type=Path,
        default=None,
        help="optional directory for local assembled/scattered PNG previews",
    )
    parser.add_argument(
        "--compare-variants",
        type=Path,
        default=None,
        help="generate the complete Variant A/B comparison under this directory",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.compare_variants is not None:
        for path in generate_variant_comparison(args.input, args.compare_variants):
            print(path)
        return 0
    output, count = write_dots_json(
        args.input,
        args.output,
        count=args.count,
        canvas_size=args.canvas_size,
        seed=args.seed,
        variant=(
            PORTRAIT_VARIANTS_BY_KEY[args.variant]
            if args.variant is not None
            else None
        ),
    )
    print(f"{output} ({count} particles)")
    if args.preview_dir is not None:
        for preview in render_validation_previews(output, args.preview_dir):
            print(preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
