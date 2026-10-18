import ast
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

import generate


SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


def visible_text(root):
    return [
        " ".join("".join(element.itertext()).split())
        for element in root.iter(f"{SVG_NAMESPACE}text")
    ]


class GenerateSvgTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.particles = generate.load_dots()
        cls.stats = generate.load_stats()
        cls.dark = generate.build_svg(
            generate.DARK_THEME, particles=cls.particles, stats=cls.stats
        )
        cls.light = generate.build_svg(
            generate.LIGHT_THEME, particles=cls.particles, stats=cls.stats
        )

    def test_both_themes_are_valid_and_have_dimension_parity(self):
        roots = [ElementTree.fromstring(svg) for svg in (self.dark, self.light)]
        for root in roots:
            self.assertEqual(root.tag, f"{SVG_NAMESPACE}svg")
            self.assertEqual(root.attrib["width"], str(generate.CARD_WIDTH))
            self.assertEqual(root.attrib["height"], str(generate.CARD_HEIGHT))
            self.assertEqual(
                root.attrib["viewBox"],
                f"0 0 {generate.CARD_WIDTH} {generate.CARD_HEIGHT}",
            )
        self.assertEqual(visible_text(roots[0]), visible_text(roots[1]))
        self.assertNotEqual(self.dark, self.light)

    def test_all_finalized_content_is_visible(self):
        root = ElementTree.fromstring(self.dark)
        text = visible_text(root)
        joined = "\n".join(text)
        expected = (
            "macanthonyeke@github:~$ whoami",
            generate.ROLE,
            generate.STATUS_TITLE,
            f"— {generate.STATUS_DETAIL}",
            "VISUAL.MAP",
            "GITHUB.STATS",
            "FEATURED.PROJECTS",
            "TRACK.RECORD",
            "CONTACT",
        )
        for value in expected:
            self.assertIn(value, text)
        for label, tools in generate.TOOL_GROUPS:
            self.assertIn(label, text)
            for tool in tools:
                self.assertIn(tool, text)
        for title, lines in generate.PROJECTS:
            self.assertIn(title, text)
            for line in lines:
                self.assertIn(line, text)
        for lines in generate.TRACK_RECORD:
            for line in lines:
                self.assertIn(line, text)
        for label, value in generate.CONTACT:
            self.assertIn(value, joined)
        self.assertNotIn("LinkedIn", joined)

    def test_statistics_match_validated_snapshot(self):
        root = ElementTree.fromstring(self.dark)
        expected = {
            "total_contributions": "245",
            "current_streak": "0 days",
            "public_repositories": "7",
            "total_stars": "1",
        }
        actual = {
            element.attrib["data-stat"]: element.attrib["data-value"]
            for element in root.iter(f"{SVG_NAMESPACE}g")
            if "data-stat" in element.attrib
        }
        self.assertEqual(actual, expected)
        self.assertIn("UPDATED 2026-10-18", visible_text(root))
        self.assertEqual(self.stats.period_start.isoformat(), "2025-10-19")
        self.assertEqual(self.stats.period_end.isoformat(), "2026-10-18")

    def test_stats_loader_rejects_tampered_totals(self):
        payload = json.loads(generate.DEFAULT_STATS.read_text(encoding="utf-8"))
        payload["statistics"]["total_contributions"] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "do not match"):
                generate.load_stats(path)

    def test_generation_is_deterministic(self):
        repeated = generate.build_svg(
            generate.DARK_THEME, particles=self.particles, stats=self.stats
        )
        self.assertEqual(self.dark, repeated)

    def test_dynamic_title_is_xml_escaped(self):
        value = 'unsafe <tag> & "quotes"'
        svg = generate.build_svg(
            generate.LIGHT_THEME,
            particles=self.particles,
            stats=self.stats,
            title=value,
        )
        root = ElementTree.fromstring(svg)
        title = root.find(f"{SVG_NAMESPACE}title")
        self.assertEqual(title.text, value)
        self.assertNotIn("<tag>", svg)
        self.assertIn("&lt;tag&gt;", svg)

    def test_declared_text_bounds_do_not_overflow_or_overlap(self):
        for svg in (self.dark, self.light):
            root = ElementTree.fromstring(svg)
            boxes = []
            for element in root.iter(f"{SVG_NAMESPACE}text"):
                left = float(element.attrib["data-layout-left"])
                right = float(element.attrib["data-layout-right"])
                top = float(element.attrib["data-layout-top"])
                bottom = float(element.attrib["data-layout-bottom"])
                self.assertGreaterEqual(left, 0)
                self.assertLessEqual(right, generate.CARD_WIDTH)
                self.assertGreaterEqual(top, 0)
                self.assertLessEqual(bottom, generate.CARD_HEIGHT)
                self.assertLess(left, right)
                self.assertLess(top, bottom)
                boxes.append((left, right, top, bottom, "".join(element.itertext())))

            for index, first in enumerate(boxes):
                for second in boxes[index + 1 :]:
                    horizontal = min(first[1], second[1]) - max(first[0], second[0])
                    vertical = min(first[3], second[3]) - max(first[2], second[2])
                    self.assertFalse(
                        horizontal > 0.1 and vertical > 0.1,
                        f"text collision: {first[4]!r} and {second[4]!r}",
                    )

            for element in root.iter(f"{SVG_NAMESPACE}rect"):
                x = float(element.attrib.get("x", 0))
                y = float(element.attrib.get("y", 0))
                width = float(element.attrib["width"])
                height = float(element.attrib["height"])
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + width, generate.CARD_WIDTH)
                self.assertLessEqual(y + height, generate.CARD_HEIGHT)

    def test_readme_scale_keeps_functional_text_legible(self):
        scale = generate.README_WIDTH / generate.CARD_WIDTH
        root = ElementTree.fromstring(self.dark)
        rendered_sizes = [
            float(element.attrib["font-size"]) * scale
            for element in root.iter(f"{SVG_NAMESPACE}text")
        ]
        self.assertGreaterEqual(min(rendered_sizes), 7.9)
        self.assertGreaterEqual(12 * scale, 10)

    def test_portrait_uses_approved_positions_and_animation(self):
        root = ElementTree.fromstring(self.dark)
        circles = [
            element
            for element in root.iter(f"{SVG_NAMESPACE}circle")
            if element.attrib.get("class") == "portrait-particle"
        ]
        self.assertEqual(len(circles), 1350)
        expected_positions = [
            (generate._svg_number(item["x"]), generate._svg_number(item["y"]))
            for item in self.particles
        ]
        actual_positions = [(item.attrib["cx"], item.attrib["cy"]) for item in circles]
        self.assertEqual(actual_positions, expected_positions)
        self.assertEqual(self.dark.count("@keyframes portrait-particle-cycle"), 1)
        self.assertIn("animation: portrait-particle-cycle 10s", self.dark)
        self.assertIn('clip-path="url(#portrait-clip-dark)"', self.dark)

    def test_light_preserves_particle_style_and_dark_uses_approved_lift(self):
        particle = {
            "x": 220,
            "y": 210,
            "r": 1.4,
            "opacity": 0.78,
            "color": "#29252d",
            "emphasis": 0.9,
            "feature": 1.0,
        }
        light = generate.particle_style_for_theme(particle, generate.LIGHT_THEME)
        dark = generate.particle_style_for_theme(particle, generate.DARK_THEME)
        self.assertEqual(light, ("#29252d", 1.4, 0.78))
        self.assertNotEqual(dark[0], particle["color"])
        self.assertGreater(dark[1], particle["r"])
        self.assertGreater(dark[2], particle["opacity"])

    def test_sequential_animation_and_reduced_motion_are_present(self):
        self.assertIn("@keyframes reveal-content", self.dark)
        self.assertIn("@keyframes cursor-blink", self.dark)
        self.assertGreaterEqual(self.dark.count('class="reveal"'), 9)
        delays = ["0.04s", "0.16s", "0.32s", "0.58s", "0.86s", "1.02s"]
        for delay in delays:
            self.assertIn(f"--delay:{delay}", self.dark)
        self.assertIn("prefers-reduced-motion: reduce", self.dark)
        self.assertIn("animation: none !important", self.dark)
        self.assertIn("opacity: 1 !important", self.dark)
        self.assertIn("transform: none !important", self.dark)

    def test_no_javascript_external_resources_or_secrets(self):
        for svg in (self.dark, self.light):
            forbidden = (
                "<script",
                "javascript:",
                "href=",
                "xlink:href",
                "<foreignObject",
                "<image",
                "@import",
                "Bearer ",
                "ghp_",
                "github_pat_",
            )
            for marker in forbidden:
                self.assertNotIn(marker, svg)
            self.assertNotIn("url(http", svg)
            self.assertNotIn("url(https", svg)
            self.assertNotIn(
                "http://", svg.replace("http://www.w3.org/2000/svg", "")
            )

    def test_generate_module_uses_only_standard_library_imports(self):
        tree = ast.parse(Path("generate.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        allowed = {
            "__future__",
            "argparse",
            "colorsys",
            "dataclasses",
            "datetime",
            "html",
            "json",
            "math",
            "pathlib",
            "re",
            "typing",
            "xml",
        }
        self.assertLessEqual(imported, allowed)

    def test_output_writers_create_canonical_and_scaled_assets(self):
        svgs = {"dark": self.dark, "light": self.light}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = generate.write_svgs(svgs, root / "assets")
            previews = generate.write_previews(svgs, root / "previews")
            self.assertEqual({path.name for path in assets}, {"dark.svg", "light.svg"})
            self.assertEqual(
                {path.name for path in previews},
                {
                    "dashboard-dark-full.svg",
                    "dashboard-dark-readme.svg",
                    "dashboard-light-full.svg",
                    "dashboard-light-readme.svg",
                },
            )
            for path in previews:
                svg_root = ElementTree.parse(path).getroot()
                if "readme" in path.name:
                    self.assertEqual(svg_root.attrib["width"], str(generate.README_WIDTH))
                    self.assertEqual(svg_root.attrib["height"], str(generate.README_HEIGHT))
                else:
                    self.assertEqual(svg_root.attrib["width"], str(generate.CARD_WIDTH))
                    self.assertEqual(svg_root.attrib["height"], str(generate.CARD_HEIGHT))

    def test_svg_outputs_are_reasonably_sized(self):
        for svg in (self.dark, self.light):
            size = len(svg.encode("utf-8"))
            self.assertGreater(size, 150_000)
            self.assertLess(size, 500_000)


if __name__ == "__main__":
    unittest.main()
