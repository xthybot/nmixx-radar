from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTests(unittest.TestCase):
    def test_sample_environment_has_safe_bootstrap_placeholder(self) -> None:
        content = (PROJECT_ROOT / ".sample.env").read_text(encoding="utf-8")
        self.assertIn("BOOTSTRAP_ADMIN_PASSWORD=change-me-before-first-start", content)
        self.assertNotIn("sk-", content)

    def test_private_runtime_paths_are_ignored(self) -> None:
        ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for path in (".env", "data/", ".push_state/", ".update_state/", ".image_cache/"):
            with self.subTest(path=path):
                self.assertIn(path, ignored)

    def test_readme_has_no_machine_specific_paths_or_private_addresses(self) -> None:
        content = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("/home/xthybot", content)
        self.assertNotIn("10.14.0.200", content)


if __name__ == "__main__":
    unittest.main()
