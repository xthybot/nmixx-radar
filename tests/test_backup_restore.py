from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupRestoreTests(unittest.TestCase):
    def test_runtime_backup_can_be_restored_only_with_explicit_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "generated_updates.json").write_text('{"items": ["before"]}', encoding="utf-8")
            environment = {**os.environ, "DATA_DIR": str(data_dir)}
            backup = subprocess.run(
                [sys.executable, "-m", "scripts.backup_runtime", "--output-dir", str(root / "backups")],
                cwd=ROOT,
                env=environment,
                text=True,
                check=True,
                capture_output=True,
            )
            archive = Path(backup.stdout.strip())
            self.assertTrue(archive.is_file())
            (data_dir / "generated_updates.json").write_text('{"items": ["after"]}', encoding="utf-8")
            subprocess.run(
                [sys.executable, "-m", "scripts.restore_runtime", str(archive), "--yes-replace-data"],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("before", (data_dir / "generated_updates.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
