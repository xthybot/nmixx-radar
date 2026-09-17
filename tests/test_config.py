import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.config import Settings


class SettingsTests(unittest.TestCase):
    def test_uses_explicit_runtime_directory_from_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "runtime"
            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}, clear=False):
                settings = Settings.from_env()
            self.assertEqual(settings.data_dir, data_dir)

    def test_rejects_bootstrap_password_placeholder(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BOOTSTRAP_ADMIN_USERNAME": "admin",
                "BOOTSTRAP_ADMIN_PASSWORD": "change-me-before-first-start",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "BOOTSTRAP_ADMIN_PASSWORD"):
                Settings.from_env()

    def test_parses_trusted_proxy_addresses(self) -> None:
        with patch.dict(os.environ, {"TRUSTED_PROXY_IPS": "127.0.0.1, ::1"}, clear=False):
            settings = Settings.from_env()
        self.assertEqual(settings.trusted_proxy_ips, ("127.0.0.1", "::1"))


if __name__ == "__main__":
    unittest.main()
