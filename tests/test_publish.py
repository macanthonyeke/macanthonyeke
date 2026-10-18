import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import validate


ROOT = Path(__file__).resolve().parents[1]


class ReadmeAndPublicationTests(unittest.TestCase):
    def test_readme_theme_switching_links_and_local_assets(self):
        validate.validate_readme(ROOT / "README.md")
        markup = (ROOT / "README.md").read_text(encoding="utf-8")
        expected_assets = (
            "assets/dark.svg",
            "assets/light.svg",
            "assets/snake-dark.svg",
            "assets/snake-light.svg",
        )
        for asset in expected_assets:
            self.assertIn(asset, markup)
            self.assertTrue((ROOT / asset).is_file())
        self.assertEqual(markup.count("<picture>"), 2)
        self.assertEqual(markup.count("prefers-color-scheme: dark"), 2)
        self.assertEqual(markup.count("prefers-color-scheme: light"), 2)
        self.assertNotIn("<h1", markup)
        self.assertNotIn("## ", markup)

    def test_canonical_publication_set_passes_offline_validation(self):
        validate.validate_publication(
            readme=ROOT / "README.md",
            stats_path=ROOT / "assets/github-stats.json",
            dots_path=ROOT / "assets/dots.json",
            dashboard_dark=ROOT / "assets/dark.svg",
            dashboard_light=ROOT / "assets/light.svg",
            snake_dark=ROOT / "assets/snake-dark.svg",
            snake_light=ROOT / "assets/snake-light.svg",
        )

    def test_svg_validator_rejects_external_resources(self):
        source = (ROOT / "assets/dark.svg").read_text(encoding="utf-8")
        unsafe = source.replace(
            "</svg>", '<image href="https://example.com/pixel.png" /></svg>'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.svg"
            path.write_text(unsafe, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "forbidden"):
                validate._validate_svg(path)

    def test_scheduling_guide_covers_all_local_platforms(self):
        guide = (ROOT / "docs/local-weekly-update.md").read_text(encoding="utf-8")
        for marker in ("launchd", "cron", "Task Scheduler", "./update.sh"):
            self.assertIn(marker, guide)
        self.assertIn("does not use GitHub Actions", guide)


class UpdateWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = Path(self.temporary.name) / "profile"
        (self.fixture / "assets").mkdir(parents=True)
        (self.fixture / "tests").mkdir()
        (self.fixture / "tmp").mkdir()
        for name in ("github_graphql.py", "generate.py", "snake.py", "validate.py"):
            (self.fixture / name).write_text("# fixture\n", encoding="utf-8")
        (self.fixture / "README.md").write_text("fixture readme\n", encoding="utf-8")
        fixtures = {
            "github-stats.json": "snapshot\n",
            "dots.json": "dots\n",
            "dark.svg": "dark\n",
            "light.svg": "light\n",
            "snake-dark.svg": "snake dark\n",
            "snake-light.svg": "snake light\n",
        }
        for name, content in fixtures.items():
            (self.fixture / "assets" / name).write_text(content, encoding="utf-8")

        self.python_log = self.fixture / "python.log"
        self.git_log = self.fixture / "git.log"
        self.fake_python = self.fixture / "fake-python"
        self.fake_git = self.fixture / "fake-git"
        self.fake_python.write_text(
            """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$MOCK_PYTHON_LOG"
if [ "${1:-}" = "-m" ]; then
  [ "${MOCK_FAIL_AT:-}" = "tests" ] && exit 19
  exit 0
fi
name=$(basename -- "$1")
shift
[ "$name" = "github_graphql.py" ] && [ "${MOCK_FAIL_AT:-}" = "auth" ] && exit 17
[ "$name" = "generate.py" ] && [ "${MOCK_FAIL_AT:-}" = "generation" ] && exit 18
[ "$name" = "validate.py" ] && [ "${MOCK_FAIL_AT:-}" = "validation" ] && exit 20
output=""
output_dir=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --output-dir) output_dir=$2; shift 2 ;;
    *) shift ;;
  esac
done
case "$name" in
  github_graphql.py)
    mkdir -p "$(dirname -- "$output")"
    cp "$PROFILE_ROOT_DIR/assets/github-stats.json" "$output"
    ;;
  generate.py)
    mkdir -p "$output_dir"
    cp "$PROFILE_ROOT_DIR/assets/dark.svg" "$output_dir/dark.svg"
    cp "$PROFILE_ROOT_DIR/assets/light.svg" "$output_dir/light.svg"
    ;;
  snake.py)
    mkdir -p "$output_dir"
    cp "$PROFILE_ROOT_DIR/assets/snake-dark.svg" "$output_dir/snake-dark.svg"
    cp "$PROFILE_ROOT_DIR/assets/snake-light.svg" "$output_dir/snake-light.svg"
    ;;
esac
""",
            encoding="utf-8",
        )
        self.fake_git.write_text(
            """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$MOCK_GIT_LOG"
case " $* " in
  *" status --porcelain "*) printf '%s' "${MOCK_GIT_STATUS:-}" ;;
  *" symbolic-ref "*) printf '%s\\n' 'origin/main' ;;
  *" branch --show-current "*) printf '%s\\n' 'main' ;;
esac
exit 0
""",
            encoding="utf-8",
        )
        self.fake_python.chmod(0o755)
        self.fake_git.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def run_updater(self, *arguments, fail_at=None, git_status=""):
        environment = os.environ.copy()
        environment.update(
            {
                "PROFILE_ROOT_DIR": str(self.fixture),
                "PROFILE_PYTHON": str(self.fake_python),
                "PROFILE_GIT": str(self.fake_git),
                "MOCK_PYTHON_LOG": str(self.python_log),
                "MOCK_GIT_LOG": str(self.git_log),
                "MOCK_GIT_STATUS": git_status,
                "TMPDIR": str(self.fixture / "tmp"),
                "GITHUB_TOKEN": "test-token-must-not-appear",
            }
        )
        if fail_at:
            environment["MOCK_FAIL_AT"] = fail_at
        return subprocess.run(
            [str(ROOT / "update.sh"), *arguments],
            cwd=self.fixture,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_no_changes_skips_commit_and_push(self):
        result = self.run_updater()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing to commit or push", result.stdout)
        git_calls = self.git_log.read_text(encoding="utf-8")
        self.assertIn("status --porcelain", git_calls)
        self.assertNotIn(" commit ", f" {git_calls} ")
        self.assertNotIn(" push ", f" {git_calls} ")
        self.assertNotIn("test-token-must-not-appear", result.stdout + result.stderr)

    def test_changed_publication_commits_and_pushes_only_after_success(self):
        result = self.run_updater(git_status=" M assets/dark.svg\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        git_calls = self.git_log.read_text(encoding="utf-8")
        self.assertIn("commit --only -m chore(profile): refresh dashboard assets", git_calls)
        self.assertIn("push origin HEAD:main", git_calls)
        validation_position = self.python_log.read_text(encoding="utf-8").rfind("validate.py")
        test_position = self.python_log.read_text(encoding="utf-8").find("-m unittest")
        self.assertGreaterEqual(validation_position, 0)
        self.assertGreaterEqual(test_position, 0)

    def test_authentication_failure_preserves_canonical_files(self):
        before = {
            path.name: path.read_bytes() for path in (self.fixture / "assets").iterdir()
        }
        result = self.run_updater(fail_at="auth")
        self.assertNotEqual(result.returncode, 0)
        after = {
            path.name: path.read_bytes() for path in (self.fixture / "assets").iterdir()
        }
        self.assertEqual(before, after)
        self.assertFalse(self.git_log.exists())
        self.assertNotIn("test-token-must-not-appear", result.stdout + result.stderr)

    def test_generation_or_validation_failure_never_promotes_or_commits(self):
        for failure in ("generation", "validation", "tests"):
            with self.subTest(failure=failure):
                if self.git_log.exists():
                    self.git_log.unlink()
                before = {
                    path.name: path.read_bytes()
                    for path in (self.fixture / "assets").iterdir()
                }
                result = self.run_updater(fail_at=failure)
                self.assertNotEqual(result.returncode, 0)
                after = {
                    path.name: path.read_bytes()
                    for path in (self.fixture / "assets").iterdir()
                }
                self.assertEqual(before, after)
                self.assertFalse(self.git_log.exists())


if __name__ == "__main__":
    unittest.main()
