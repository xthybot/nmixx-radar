from __future__ import annotations

import argparse
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings


def copy_database(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as destination_connection:
        source_connection.backup(destination_connection)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a consistent NMIXX Radar runtime backup.")
    parser.add_argument("--output-dir", type=Path, default=Path("./backups"))
    args = parser.parse_args()
    settings = Settings.from_env()
    source = settings.data_dir.resolve()
    if not source.is_dir():
        raise SystemExit(f"Runtime data directory does not exist: {source}")
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_path = args.output_dir / f"nmixx-radar-{timestamp}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="nmixx-radar-backup-") as temporary_directory:
        staged_data = Path(temporary_directory) / "data"
        shutil.copytree(source, staged_data, ignore=shutil.ignore_patterns("radar.sqlite3", "radar.sqlite3-*", ".*.lock"))
        database = source / "radar.sqlite3"
        if database.exists():
            copy_database(database, staged_data / "radar.sqlite3")
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(staged_data, arcname="data", recursive=True)
    archive_path.chmod(0o600)
    print(archive_path)


if __name__ == "__main__":
    main()
