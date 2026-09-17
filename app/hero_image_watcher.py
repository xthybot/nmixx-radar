from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.config import Settings
from app.runtime_data import RuntimeDataStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_URL = "https://nmixx.jype.com/Default/Gallery"
USER_AGENT = "idol-site-py-hero-image-watcher/0.1"
GALLERY_IMAGE_HOSTS = (
    "d1al7qj7ydfbpt.cloudfront.net",
    "d1meds70430yck.cloudfront.net",
)


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def clean_image_url(url: str) -> str:
    cleaned = (
        url.strip()
        .rstrip("\\")
        .replace("\\u0026", "&")
        .replace("\\/", "/")
        .replace("&amp;", "&")
    )
    parsed = urlsplit(cleaned)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def extract_gallery_images(html: str, limit: int) -> list[str]:
    hosts_pattern = "|".join(re.escape(host) for host in GALLERY_IMAGE_HOSTS)
    urls = [
        clean_image_url(match)
        for match in re.findall(rf"https://(?:{hosts_pattern})/[^\"'<> )]+", html)
    ]
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if "/artists/nmixx/galleries/" not in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
        if len(result) >= limit:
            break
    return result


def build_slides(urls: list[str]) -> list[dict[str, str]]:
    return [
        {
            "src": url,
            "alt": f"NMIXX 官方 Gallery 最新圖片 {index}",
            "label": f"官方 Gallery · {index:02d}",
            "source": "JYP 官方 Gallery",
        }
        for index, url in enumerate(urls, start=1)
    ]


def write_generated_hero_slides(
    store: RuntimeDataStore, slides: list[dict[str, str]]
) -> list[dict[str, Any]]:
    return store.write_hero_slides(slides)


def should_check(
    state: dict[str, Any], force: bool, minimum_interval_seconds: int | None = None
) -> bool:
    if force:
        return True
    if minimum_interval_seconds:
        checked_at = state.get("checked_at")
        if isinstance(checked_at, str):
            try:
                last_checked = datetime.fromisoformat(checked_at)
                return (datetime.now(last_checked.tzinfo) - last_checked).total_seconds() >= minimum_interval_seconds
            except ValueError:
                pass
    return state.get("checked_date") != datetime.now(UTC).date().isoformat()


def run_once(
    source_url: str = DEFAULT_SOURCE_URL,
    state_path: Path | None = None,
    limit: int = 10,
    dry_run: bool = False,
    force: bool = False,
    runtime_data: RuntimeDataStore | None = None,
    minimum_interval_seconds: int | None = None,
) -> int:
    if runtime_data is None:
        settings = Settings.from_env()
        runtime_data = RuntimeDataStore(settings.data_dir, settings.max_generated_updates)
    runtime_data.initialize()
    state_path = state_path or runtime_data.data_dir / "hero_slides_state.json"
    state = read_json(state_path, {})
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if not should_check(state, force, minimum_interval_seconds):
        print(f"[same-day] hero slides already checked on {state.get('checked_at')}")
        return 0

    html = fetch_html(source_url)
    urls = extract_gallery_images(html, limit)
    if not urls:
        print("[skip] no NMIXX gallery images found", file=sys.stderr)
        return 1

    digest = hashlib.sha256("\n".join(urls).encode("utf-8")).hexdigest()
    changed = digest != state.get("hash")
    if changed:
        slides = build_slides(urls)
        if dry_run:
            print(f"[dry-run] would update {len(slides)} hero slide(s)")
        else:
            write_generated_hero_slides(runtime_data, slides)
            print(f"[updated] wrote {len(slides)} hero slide(s)")
    else:
        print("[same] hero slides already use the latest gallery images")

    if not dry_run:
        state.update(
            {
                "source_url": source_url,
                "hash": digest,
                "checked_date": datetime.now(UTC).date().isoformat(),
                "checked_at": now,
                "image_count": len(urls),
                "images": urls,
            }
        )
        write_json(state_path, state)
    return 0


def watch(interval_seconds: int, **kwargs: Any) -> None:
    while True:
        try:
            run_once(**kwargs)
        except (OSError, TimeoutError, ValueError) as error:
            print(f"[error] {error}", file=sys.stderr)
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update NMIXX hero carousel from JYP Gallery images.")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument("--watch", action="store_true", help="Keep checking on an interval.")
    parser.add_argument("--interval-seconds", type=int, default=86400)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Check even if today's run already happened.")
    parser.add_argument("--respect-interval", action="store_true", help="Use HERO_UPDATE_INTERVAL_SECONDS for timer runs.")
    args = parser.parse_args()

    settings = Settings.from_env()
    runtime_data = RuntimeDataStore(settings.data_dir, settings.max_generated_updates)
    options = {
        "source_url": args.source_url,
        "state_path": args.state_path,
        "limit": args.limit,
        "dry_run": args.dry_run,
        "force": args.force,
        "runtime_data": runtime_data,
        "minimum_interval_seconds": settings.hero_update_interval_seconds if args.respect_interval else None,
    }
    if args.watch:
        watch(args.interval_seconds, **options)
        return
    run_once(**options)


if __name__ == "__main__":
    main()
