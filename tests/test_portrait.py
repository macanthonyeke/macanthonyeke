import unittest
import importlib.util
from pathlib import Path
from xml.etree import ElementTree

from portrait import (
    Particle,
    VARIANT_B,
    particles_to_svg,
    render_variant_previews,
    render_validation_previews,
    resolve_source_path,
    sample_particles,
    write_dots_json,
)


class PortraitSvgTests(unittest.TestCase):
    def test_hand_authored_particles_render_to_valid_svg(self):
        particles = (
            Particle(10, 12, 1.5, 0.8, "#b18cff", -18, 20),
            Particle(20, 24, 2.0, 1.0, "#7e57c2", 22, -14),
        )
        svg = particles_to_svg(particles, title="Snoozies & portrait")
        ElementTree.fromstring(svg)
        self.assertIn("Snoozies &amp; portrait", svg)
        self.assertIn("portrait-particle-cycle", svg)
        self.assertNotIn("https://", svg)
        self.assertNotIn("<image", svg)

    @unittest.skipUnless(
        importlib.util.find_spec("PIL") and importlib.util.find_spec("numpy"),
        "offline portrait dependencies are not installed",
    )
    def test_source_sampling_is_deterministic(self):
        try:
            source = resolve_source_path(Path("assets/source/snoozies-nft.jpg"))
        except FileNotFoundError:
            self.skipTest("Snoozies source image is not available")
        first = sample_particles(source, count=1500, canvas_size=320, seed=12345)
        second = sample_particles(source, count=1500, canvas_size=320, seed=12345)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1500)
        self.assertGreater(len({particle.color for particle in first}), 100)
        self.assertTrue(any(particle.scatter_x or particle.scatter_y for particle in first))

    @unittest.skipUnless(
        importlib.util.find_spec("PIL") and importlib.util.find_spec("numpy"),
        "offline portrait dependencies are not installed",
    )
    def test_fewer_larger_variant_is_deterministic(self):
        try:
            source = resolve_source_path(Path("assets/source/snoozies-nft.jpg"))
        except FileNotFoundError:
            self.skipTest("Snoozies source image is not available")
        first = sample_particles(source, canvas_size=320, seed=54321, variant=VARIANT_B)
        second = sample_particles(source, canvas_size=320, seed=54321, variant=VARIANT_B)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1350)
        self.assertGreater(sum(p.radius for p in first) / len(first), 1.8)

    @unittest.skipUnless(
        importlib.util.find_spec("PIL") and importlib.util.find_spec("numpy"),
        "offline portrait dependencies are not installed",
    )
    def test_validation_previews_include_actual_readme_dimensions(self):
        import tempfile

        try:
            source = resolve_source_path(Path("assets/source/snoozies-nft.jpg"))
        except FileNotFoundError:
            self.skipTest("Snoozies source image is not available")
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dots_path = root / "dots.json"
            write_dots_json(source, dots_path, count=1500, canvas_size=420, seed=12345)
            paths = render_validation_previews(dots_path, root / "previews")
            self.assertEqual(len(paths), 6)
            self.assertTrue(all(path.exists() for path in paths))
            readme_paths = [path for path in paths if "readme" in path.name]
            self.assertEqual(len(readme_paths), 2)
            for path in readme_paths:
                with Image.open(path) as preview:
                    self.assertEqual(preview.size, (231, 231))

    @unittest.skipUnless(
        importlib.util.find_spec("PIL") and importlib.util.find_spec("numpy"),
        "offline portrait dependencies are not installed",
    )
    def test_variant_preview_set_has_required_dimensions(self):
        import tempfile

        try:
            source = resolve_source_path(Path("assets/source/snoozies-nft.jpg"))
        except FileNotFoundError:
            self.skipTest("Snoozies source image is not available")
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dots_path = root / "dots.json"
            write_dots_json(source, dots_path, seed=98765, variant=VARIANT_B)
            paths = render_variant_previews(dots_path, root / "previews")
            self.assertEqual(len(paths), 6)
            for path in paths:
                with Image.open(path) as preview:
                    expected = (840, 840) if "large" in path.name else (231, 231)
                    self.assertEqual(preview.size, expected)


if __name__ == "__main__":
    unittest.main()
