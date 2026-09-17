from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DeploymentFilesTests(unittest.TestCase):
    def test_systemd_units_cover_site_and_both_periodic_jobs(self) -> None:
        units = ROOT / "deploy" / "systemd"
        expected = {
            "nmixx-radar.service": "uvicorn app.main:app",
            "nmixx-radar-update.service": "app.update_watcher --once --respect-interval",
            "nmixx-radar-hero.service": "app.hero_image_watcher --once --respect-interval",
        }
        for filename, command in expected.items():
            content = (units / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIn("EnvironmentFile=/opt/nmixx-radar/.env", content)
                self.assertIn(command, content)
                self.assertNotIn("User=root", content)
        website_unit = (units / "nmixx-radar.service").read_text(encoding="utf-8")
        self.assertIn("--host ${APP_HOST}", website_unit)
        self.assertIn("--port ${APP_PORT}", website_unit)
        for filename in ("nmixx-radar-update.timer", "nmixx-radar-hero.timer"):
            content = (units / filename).read_text(encoding="utf-8")
            self.assertIn("OnUnitActiveSec=1min", content)

    def test_nginx_example_terminates_https_on_443_and_uses_loopback_upstream(self) -> None:
        content = (ROOT / "deploy" / "nginx" / "nmixx-radar.conf").read_text(encoding="utf-8")
        self.assertIn("listen 443 ssl", content)
        self.assertIn("proxy_pass http://127.0.0.1:32765", content)
        self.assertIn("X-Forwarded-Proto https", content)


if __name__ == "__main__":
    unittest.main()
