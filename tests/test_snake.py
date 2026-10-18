import json
import math
import struct
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree

import snake


def contribution_range(start, count, active=None):
    active = active or {}
    items = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        value = active.get(day, 0)
        items.append(
            snake.Contribution(
                day=day,
                count=value,
                level="FIRST_QUARTILE" if value else "NONE",
                source_color="#9be9a8" if value else "#ebedf0",
            )
        )
    return tuple(items)


class ContributionSnakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = snake.load_snapshot(Path("assets/github-stats.json"))

    def test_calendar_dates_and_counts_match_normalized_snapshot(self):
        raw = json.loads(Path("assets/github-stats.json").read_text())
        self.assertEqual(len(self.snapshot.contributions), 365)
        self.assertEqual(
            [item.day.isoformat() for item in self.snapshot.contributions],
            [item["date"] for item in raw["contributions"]],
        )
        self.assertEqual(
            [item.count for item in self.snapshot.contributions],
            [item["count"] for item in raw["contributions"]],
        )
        self.assertEqual(
            sum(item.count for item in self.snapshot.contributions), 245
        )

    def test_weekday_alignment_uses_sunday_as_first_row(self):
        contributions = contribution_range(date(2026, 10, 18), 7)
        layout = snake.layout_calendar(contributions)
        self.assertEqual([cell.weekday for cell in layout.cells], list(range(7)))
        self.assertTrue(all(cell.week == 0 for cell in layout.cells))

    def test_leap_day_is_preserved_and_aligned(self):
        contributions = contribution_range(date(2024, 2, 27), 5)
        layout = snake.layout_calendar(contributions)
        leap_cell = next(
            cell
            for cell in layout.cells
            if cell.contribution.day == date(2024, 2, 29)
        )
        self.assertEqual(leap_cell.weekday, 4)  # Thursday with Sunday=0.
        self.assertEqual(leap_cell.contribution.day.isoformat(), "2024-02-29")

    def test_incomplete_first_and_last_weeks_keep_blank_slots(self):
        contributions = contribution_range(date(2024, 1, 3), 7)
        layout = snake.layout_calendar(contributions)
        self.assertEqual(layout.week_count, 2)
        self.assertEqual((layout.cells[0].week, layout.cells[0].weekday), (0, 3))
        self.assertEqual((layout.cells[-1].week, layout.cells[-1].weekday), (1, 2))
        occupied = {(cell.week, cell.weekday) for cell in layout.cells}
        self.assertNotIn((0, 0), occupied)
        self.assertNotIn((1, 6), occupied)

    def test_zero_contribution_days_remain_real_cells(self):
        svg = snake.build_svg(self.snapshot, snake.DARK_THEME)
        root = ElementTree.fromstring(svg)
        cells = [
            element
            for element in root.iter()
            if element.attrib.get("data-date") is not None
        ]
        self.assertEqual(len(cells), 365)
        zero_cells = [cell for cell in cells if cell.attrib["data-count"] == "0"]
        self.assertTrue(zero_cells)
        self.assertTrue(all("level-0" in cell.attrib["class"] for cell in zero_cells))

    def test_svg_is_valid_and_deterministic(self):
        first = snake.build_svg(self.snapshot, snake.DARK_THEME)
        second = snake.build_svg(self.snapshot, snake.DARK_THEME)
        root = ElementTree.fromstring(first)
        self.assertEqual(first, second)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(first.count("@keyframes snake-travel"), 1)
        self.assertEqual(first.count("@keyframes cell-consume"), 1)
        self.assertEqual(first.count('class="snake-mover snake-body"'), 10)

    def test_route_is_deterministic_closed_and_within_boundaries(self):
        layout = snake.layout_calendar(self.snapshot.contributions)
        first = snake.build_route(layout)
        second = snake.build_route(layout)
        self.assertEqual(first, second)
        self.assertEqual(first.points[0], first.points[-1])
        self.assertGreater(first.length, 0)
        self.assertTrue(all(0 <= x <= snake.WIDTH for x, _ in first.points))
        self.assertTrue(all(0 <= y <= snake.HEIGHT for _, y in first.points))
        # Row zero moves right; row one reverses left after a vertical turn.
        self.assertGreater(first.points[1][0], first.points[0][0])
        self.assertEqual(first.points[1][0], first.points[2][0])
        self.assertLess(first.points[3][0], first.points[2][0])

    def test_head_and_body_render_bounds_stay_inside_viewport(self):
        layout = snake.layout_calendar(self.snapshot.contributions)
        route = snake.build_route(layout)
        left, top, right, bottom = snake.snake_render_bounds(route)
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(right, snake.WIDTH)
        self.assertLessEqual(bottom, snake.HEIGHT)

        # Sample the entire loop, including every boundary and return-lane turn.
        for step in range(2001):
            elapsed = route.duration * step / 2000
            for index in range(snake.BODY_SEGMENTS + 1):
                distance = snake.snake_segment_distance(route, elapsed, index)
                x, y = snake.point_at_distance(route, distance)
                radius = 6.0 if index == 0 else snake.body_radius(index)
                wave = 0.0 if index == 0 else snake.body_wave(index)
                self.assertGreaterEqual(x - radius, 0)
                self.assertLessEqual(x + radius, snake.WIDTH)
                self.assertGreaterEqual(y + wave - radius, 0)
                self.assertLessEqual(y + wave + radius, snake.HEIGHT)

    def test_body_segments_overlap_for_connected_appearance(self):
        center_spacing = snake.SEGMENT_LAG_SECONDS * snake.SNAKE_SPEED
        head_to_first = math.hypot(center_spacing, snake.body_wave(1))
        self.assertLessEqual(head_to_first, 6.0 + snake.body_radius(1))
        for index in range(1, snake.BODY_SEGMENTS):
            wave_delta = snake.body_wave(index + 1) - snake.body_wave(index)
            distance = math.hypot(center_spacing, wave_delta)
            radii = snake.body_radius(index) + snake.body_radius(index + 1)
            self.assertLessEqual(distance, radii)

    def test_cell_regeneration_wraps_relative_to_late_consumption(self):
        layout = snake.layout_calendar(self.snapshot.contributions)
        route = snake.build_route(layout)
        arrival = route.duration * 0.98

        self.assertAlmostEqual(snake.cell_cycle_phase(arrival, arrival, route), 0.0)
        # At loop reset, this late cell is only 2% into its own cycle and eaten.
        self.assertAlmostEqual(
            snake.cell_cycle_phase(route.duration, arrival, route), 0.02
        )
        self.assertAlmostEqual(
            snake.cell_opacity_at_elapsed(route.duration, arrival, route), 0.1
        )
        # It fully regenerates 8% of a loop after its own arrival, across wrap.
        regenerated_at = arrival + route.duration * snake.REGEN_FRACTION
        self.assertAlmostEqual(
            snake.cell_opacity_at_elapsed(regenerated_at, arrival, route), 1.0
        )

    def test_all_snake_parts_cross_loop_boundary_continuously(self):
        layout = snake.layout_calendar(self.snapshot.contributions)
        route = snake.build_route(layout)
        epsilon = 0.001
        for index in range(snake.BODY_SEGMENTS + 1):
            before = snake.point_at_distance(
                route,
                snake.snake_segment_distance(route, route.duration - epsilon, index),
            )
            after = snake.point_at_distance(
                route,
                snake.snake_segment_distance(route, route.duration + epsilon, index),
            )
            self.assertLess(math.dist(before, after), 0.25)

    def test_cell_arrivals_follow_serpentine_boundary_reversal(self):
        layout = snake.layout_calendar(self.snapshot.contributions)
        row_zero = [cell for cell in layout.cells if cell.weekday == 0]
        row_one = [cell for cell in layout.cells if cell.weekday == 1]
        row_zero_distances = [snake.cell_arrival_distance(cell, layout) for cell in row_zero]
        row_one_distances = [snake.cell_arrival_distance(cell, layout) for cell in row_one]
        self.assertEqual(row_zero_distances, sorted(row_zero_distances))
        self.assertEqual(row_one_distances, sorted(row_one_distances, reverse=True))

    def test_reduced_motion_restores_cells_and_static_snake(self):
        svg = snake.build_svg(self.snapshot, snake.LIGHT_THEME)
        self.assertIn("prefers-reduced-motion: reduce", svg)
        self.assertIn("animation: none !important", svg)
        self.assertIn("opacity: 1 !important", svg)
        self.assertIn(".static-snake { display: none; }", svg)
        self.assertIn(".static-snake { display: inline !important; }", svg)

    def test_svg_has_no_javascript_external_resources_or_tokens(self):
        for theme in snake.THEMES:
            svg = snake.build_svg(self.snapshot, theme)
            forbidden = (
                "<script",
                "javascript:",
                "href=",
                "xlink:href",
                "<image",
                "@import",
                "url(",
                "Bearer ",
                "ghp_",
                "github_pat_",
            )
            for marker in forbidden:
                self.assertNotIn(marker, svg)
            self.assertNotIn(
                "http://", svg.replace("http://www.w3.org/2000/svg", "")
            )
            self.assertNotIn("https://", svg)

    def test_generated_files_are_reasonably_sized(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = snake.write_svgs(self.snapshot, Path(directory))
            self.assertEqual(len(paths), 2)
            for path in paths:
                self.assertLess(path.stat().st_size, 100_000)
                self.assertGreater(path.stat().st_size, 20_000)

    def test_animated_preview_has_timed_frames_and_is_deterministic(self):
        def chunk_types(payload):
            offset = 8
            chunks = []
            while offset < len(payload):
                length = struct.unpack(">I", payload[offset : offset + 4])[0]
                kind = payload[offset + 4 : offset + 8]
                data = payload[offset + 8 : offset + 8 + length]
                chunks.append((kind, data))
                offset += 12 + length
            return chunks

        frames = (
            snake.render_phase(self.snapshot, snake.DARK_THEME, 0.34),
            snake.render_phase(self.snapshot, snake.DARK_THEME, 0.35),
            snake.render_phase(self.snapshot, snake.DARK_THEME, 0.36),
        )
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.png"
            second = Path(directory) / "second.png"
            snake.write_apng(frames, first, 8)
            snake.write_apng(frames, second, 8)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            chunks = chunk_types(first.read_bytes())
            animation_control = next(data for kind, data in chunks if kind == b"acTL")
            frame_count, play_count = struct.unpack(">II", animation_control)
            self.assertEqual((frame_count, play_count), (3, 1))
            self.assertEqual(sum(kind == b"fcTL" for kind, _ in chunks), 3)
            self.assertEqual(sum(kind == b"fdAT" for kind, _ in chunks), 2)
            self.assertLess(first.stat().st_size, 2_000_000)


if __name__ == "__main__":
    unittest.main()
