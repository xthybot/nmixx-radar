from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings


def extract_backup(archive_path: Path, destination: Path) -> Path:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members or any(
            (member.name != "data" and not member.name.startswith("data/"))
            or member.issym()
            or member.islnk()
            for member in members
        ):
            raise ValueError("Backup archive has an unsafe or unexpected layout.")
        archive.extractall(destination, filter="data")
    extracted = destination / "data"
    if not extracted.is_dir():
        raise ValueError("Backup archive does not contain a data directory.")
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a NMIXX Radar runtime backup.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--yes-replace-data", action="store_true", help="Required acknowledgement for replacement.")
    args = parser.parse_args()
    if not args.yes_replace_data:
        raise SystemExit("Refusing to replace runtime data without --yes-replace-data.")
    if not args.archive.is_file():
        raise SystemExit(f"Backup archive does not exist: {args.archive}")
    settings = Settings.from_env()
    target = settings.data_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="nmixx-radar-restore-") as temporary_directory:
        extracted = extract_backup(args.archive, Path(temporary_directory))
        previous = target.with_name(
            f"{target.name}.before-restore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        )
        if target.exists():
            target.rename(previous)
        shutil.move(str(extracted), str(target))
        target.chmod(0o700)
    print(f"Restored {target}. Previous data, if any, was retained at {previous}.")


if __name__ == "__main__":
    main()
