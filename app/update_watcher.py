from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.database import Database
from app.push import PushService
from app.runtime_data import RuntimeDataStore
from app.site_data import UPDATES
from app.url_policy import is_allowed_external_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "app" / "update_sources.json"
USER_AGENT = "idol-site-py-update-watcher/0.1"
MIN_AI_CONFIDENCE = 0.7
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


class TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored_tag_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_tag_depth += 1
        if tag in {"br", "p", "li", "tr", "div", "section", "article", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_tag_depth:
            self._ignored_tag_depth -= 1
        if tag in {"p", "li", "tr", "div", "section", "article", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_tag_depth:
            return
        value = data.strip()
        if value:
            self.parts.append(value)

    def normalized_text(self) -> str:
        text = "\n".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    tag: str
    tone: str


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def load_config(path: Path, runtime_dir: Path | None = None) -> tuple[int, Path, list[Source]]:
    config = read_json(path, {})
    interval = int(config.get("interval_seconds", 3600))
    state_name = Path(str(config.get("state_path", "update_state.json"))).name
    state_path = (runtime_dir or PROJECT_ROOT / "data") / state_name
    sources = [
        Source(
            name=str(item["name"]),
            url=str(item["url"]),
            tag=str(item.get("tag", "公告")),
            tone=str(item.get("tone", "lime")),
        )
        for item in config.get("sources", [])
    ]
    if not sources:
        raise ValueError(f"No sources configured in {path}")
    return interval, state_path, sources


def fetch_source(source: Source) -> tuple[str, str]:
    request = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        html = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    parser = TextExtractor()
    parser.feed(html)
    text = parser.normalized_text()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest, text


def compact(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n...\n{tail}"


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def is_traditional_chinese_user_text(value: str) -> bool:
    """Visible site and push text must contain Chinese and no untranslated Korean."""
    return bool(re.search(r"[\u3400-\u9fff]", value)) and not bool(
        re.search(r"[\uac00-\ud7af]", value)
    )


def local_today() -> date:
    return datetime.now(TAIPEI_TZ).date()


def explicit_date(value: str) -> date | None:
    """Extract a publication date from AI metadata, if one is present."""
    match = re.search(r"(?<!\d)(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})日?", value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def known_update_keys(existing_updates: list[dict[str, Any]] | None = None) -> set[tuple[str, str]]:
    keys = set()
    for item in [*(existing_updates or []), *UPDATES]:
        keys.add((str(item.get("href", "")).strip(), normalize_title(str(item.get("title", "")))))
    return keys


def dedupe_items(
    items: list[dict[str, str]],
    source: Source | None = None,
    existing_updates: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    known = known_update_keys(existing_updates)
    seen = set()
    result = []
    today = local_today()
    for item in items:
        if item.get("should_notify") is False:
            continue
        title = str(item.get("title", "")).strip()
        href = str(item.get("href", "")).strip()
        if not title or not href or not is_allowed_external_url(href):
            continue
        item_date = explicit_date(str(item.get("meta", "")))
        # Never let an AI decision turn a backfilled article into a push.
        # Google News candidates must have an explicit publication date so an
        # undated/ambiguous result fails closed.
        if item_date is not None and item_date < today:
            continue
        if source and source.name.startswith("Google News") and item_date is None:
            continue
        key = (href, normalize_title(title))
        if key in known or key in seen:
            continue
        confidence = float(item.get("confidence", 1))
        if confidence < MIN_AI_CONFIDENCE:
            continue
        notification_title = str(item.get("notification_title", "")).strip()
        notification_body = str(item.get("notification_body", "")).strip()
        if not all(
            is_traditional_chinese_user_text(value)
            for value in (title, notification_title, notification_body)
        ):
            continue
        seen.add(key)
        is_news_rss = bool(source and source.name.startswith("Google News"))
        meta = str(item.get("meta", "")).strip() or "官方更新"
        if is_news_rss and "新聞 RSS" not in meta:
            meta = f"{meta} · 新聞 RSS"
        result.append(
            {
                "tag": "新聞" if is_news_rss else (str(item.get("tag", "公告")).strip() or "公告"),
                "title": title,
                "meta": meta,
                "href": href,
                "tone": str(item.get("tone", "lime")).strip() or "lime",
                "notification_title": notification_title,
                "notification_body": notification_body,
                "notification_reason": str(item.get("notification_reason", "")).strip(),
            }
        )
    return result


def review_change(
    source: Source,
    previous_text: str,
    current_text: str,
    existing_updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if os.environ.get("USE_HEURISTIC_REVIEW") == "1":
        return review_with_heuristics(source, current_text)

    payload = {
        "source": {
            "name": source.name,
            "url": source.url,
            "default_tag": source.tag,
            "default_tone": source.tone,
        },
        "current_date": local_today().isoformat(),
        "existing_updates": [
            {"title": item["title"], "href": item["href"], "meta": item["meta"]}
            for item in [*(existing_updates or []), *UPDATES]
        ],
        "previous_text": compact(previous_text),
        "current_text": compact(current_text),
        "instructions": (
            "Return JSON only, no markdown. Compare previous_text and current_text. "
            "Decide whether current_text contains newly published NMIXX information that is not "
            "already listed in existing_updates. Treat layout changes, menu changes, ordering changes, "
            "counter changes, repeated titles, and generic website text as not new. "
            "The current date is current_date. Each candidate item must be judged by AI for push "
            "notification suitability. Do not notify old dated items, archive/list backfill, birthday "
            "greetings, anniversaries, repeated notices, or items whose date is before current_date "
            "unless the text proves it was newly published today. "
            "Only return is_new=true when you can identify a concrete new, push-worthy notice, schedule item, "
            "release, video, or official image update. Use source.url as href if no item-specific URL "
            "is visible. Use the source default tag and tone unless there is a better obvious match. "
            "Every item must include tag, title, meta, href, tone, should_notify, "
            "notification_title, notification_body, notification_reason, and confidence from 0 to 1. "
            "All user-facing fields—tag, title, meta, notification_title, and notification_body—must be "
            "written in Traditional Chinese. Translate Korean and English source headlines into natural "
            "Traditional Chinese; retain only necessary names, song titles, and other proper nouns. "
            "notification_title is the user-facing push title in Traditional Chinese. It must be short, "
            "specific, and under 18 Chinese characters; summarize the update instead of copying a long title. "
            "notification_body is the user-facing push body in Traditional Chinese. It must be a real content "
            "summary under 60 Chinese characters. Do not include call-to-action wording such as 點擊查看, "
            "查看詳情, 開啟, 點我, or similar. Do not put only the date, source, URL, or your AI judgment "
            "reason in notification_body. "
            f"Set confidence below {MIN_AI_CONFIDENCE} when unsure. "
            "Schema: {\"is_new\": boolean, \"items\": [{\"tag\": string, \"title\": string, "
            "\"meta\": string, \"href\": string, \"tone\": string, \"should_notify\": boolean, "
            "\"notification_title\": string, \"notification_body\": string, "
            "\"notification_reason\": string, \"confidence\": number}], "
            "\"reason\": string}. If the page changed but no new information is found, return "
            "{\"is_new\": false, \"items\": [], \"reason\": \"...\"}."
        ),
    }

    command = os.environ.get("AI_REVIEW_COMMAND")
    if command:
        return review_with_command(command, payload)

    if os.environ.get("OLLAMA_MODEL"):
        return review_with_ollama(payload)

    if os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_MODEL"):
        return review_with_openai(payload)

    return {
        "is_new": False,
        "items": [],
        "reason": (
            "AI is not configured. Set OLLAMA_MODEL, AI_REVIEW_COMMAND, "
            "or OPENAI_API_KEY and OPENAI_MODEL."
        ),
        "needs_ai": True,
    }


def parse_item_date(value: str) -> date | None:
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def review_with_heuristics(source: Source, current_text: str) -> dict[str, Any]:
    today = local_today()
    lines = [line.strip() for line in current_text.splitlines() if line.strip()]
    items: list[dict[str, Any]] = []

    if source.name.startswith("Google News"):
        include_terms = re.compile(
            r"공연|투어|시구|개최|확정|발매|공개|컴백|콘서트|AAA|tour|concert|release|comeback",
            re.I,
        )
        exclude_terms = re.compile(r"포토|앰버서더|로션|출시|지원사격|photo|ambassador|lotion", re.I)
        seen_hrefs: set[str] = set()
        for index, line in enumerate(lines):
            if line.startswith(("http://", "https://", "CBMi")) or "<a href=" in line:
                continue
            if "google" in line.lower() and "新聞" in line:
                continue
            if not re.search(r"NMIXX|엔믹스", line, re.I):
                continue
            if not include_terms.search(line) or exclude_terms.search(line):
                continue
            if not is_traditional_chinese_user_text(line):
                continue

            href = next(
                (
                    candidate
                    for candidate in lines[index + 1 : index + 5]
                    if candidate.startswith("https://news.google.com/rss/articles/")
                ),
                "",
            )
            published = next(
                (
                    parsed
                    for parsed in (
                        parse_item_date(candidate) for candidate in lines[index + 1 : index + 8]
                    )
                    if parsed is not None
                ),
                None,
            )
            if not href or published != today:
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            items.append(
                {
                    "tag": source.tag,
                    "title": line,
                    "meta": today.isoformat(),
                    "href": href,
                    "tone": source.tone,
                    "should_notify": True,
                    "notification_title": line.split(" - ", 1)[0][:18],
                    "notification_body": line.split(" - ", 1)[0][:60],
                    "notification_reason": "Heuristic match for today's NMIXX news item.",
                    "confidence": 0.85,
                }
            )
            if len(items) >= 3:
                break
    else:
        for index, line in enumerate(lines):
            published = parse_item_date(line)
            if published != today or index == 0:
                continue
            title = lines[index - 1]
            if len(title) < 4 or title.isdigit():
                continue
            if not is_traditional_chinese_user_text(title):
                continue
            items.append(
                {
                    "tag": source.tag,
                    "title": title,
                    "meta": f"{today.isoformat()} · JYP 官方",
                    "href": source.url,
                    "tone": source.tone,
                    "should_notify": True,
                    "notification_title": title[:18],
                    "notification_body": title[:60],
                    "notification_reason": "Heuristic match for today's official NMIXX item.",
                    "confidence": 0.9,
                }
            )

    return {
        "is_new": bool(items),
        "items": items,
        "reason": "Heuristic review completed.",
        "reviewer": "heuristic",
    }


def review_with_command(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    command_parts = shlex.split(command)
    if not command_parts:
        return {"is_new": False, "items": [], "reason": "AI command is empty.", "error": True}
    process = subprocess.run(
        command_parts,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        shell=False,
        check=False,
        capture_output=True,
        timeout=120,
    )
    if process.returncode != 0:
        return {
            "is_new": False,
            "items": [],
            "reason": process.stderr.strip() or f"AI command failed with {process.returncode}",
            "error": True,
        }
    return parse_json_response(process.stdout)


def review_with_ollama(payload: dict[str, Any]) -> dict[str, Any]:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    body = {
        "model": os.environ["OLLAMA_MODEL"],
        "stream": False,
        "format": "json",
        "think": False,
        "system": "You review official idol website changes and return strict JSON only.",
        "prompt": json.dumps(payload, ensure_ascii=False),
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as error:
        return {
            "is_new": False,
            "items": [],
            "reason": f"Ollama request failed: {error}",
            "error": True,
        }

    response_text = str(data.get("response", "")).strip()
    if not response_text and data.get("thinking"):
        response_text = str(data["thinking"])
    result = parse_json_response(response_text)
    result["reviewer"] = "ollama"
    result["model"] = os.environ["OLLAMA_MODEL"]
    return result


def review_with_openai(payload: dict[str, Any]) -> dict[str, Any]:
    body = {
        "model": os.environ["OPENAI_MODEL"],
        "input": [
            {
                "role": "system",
                "content": "You review official idol website changes and return strict JSON only.",
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        return {"is_new": False, "items": [], "reason": message, "error": True}

    text = data.get("output_text", "")
    if not text:
        text_parts: list[str] = []
        for output in data.get("output", []):
            for content in output.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    text_parts.append(str(content.get("text", "")))
        text = "\n".join(text_parts)
    return parse_json_response(text)


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return {"is_new": False, "items": [], "reason": "AI did not return JSON.", "error": True}
        result = json.loads(match.group(0))
    if not isinstance(result, dict):
        return {"is_new": False, "items": [], "reason": "AI JSON root is not an object.", "error": True}
    result.setdefault("is_new", False)
    result.setdefault("items", [])
    result.setdefault("reason", "")
    return result


def write_generated_updates(store: RuntimeDataStore, items: list[dict[str, str]]) -> list[dict[str, Any]]:
    return store.prepend_updates(items)


def compact_notification_title(item: dict[str, str], max_chars: int = 18) -> str:
    title = str(item.get("notification_title", "")).strip()
    if not title:
        title = str(item.get("title", "")).strip()
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"\s*[·|｜-]\s*JYP.*$", "", title, flags=re.I)
    title = title.replace("NMIXX, Anderson .Paak", "Caution")
    title = title.replace("NMIXX(엔믹스)", "NMIXX")
    title = title.strip(" -·｜|")
    if len(title) <= max_chars:
        return title
    return title[: max_chars - 1].rstrip() + "…"


def sanitize_notification_body(body: str) -> str:
    cleaned = re.sub(r"\s+", " ", body).strip()
    cleaned = re.sub(r"[，,。；;：: ]*(點擊查看詳情|點擊查看|查看詳情|點我查看|開啟查看|點擊可查看最新動態)[。！!]*", "", cleaned)
    return cleaned.strip(" ，,。；;：:")[:60]


def push_body_for_item(item: dict[str, str]) -> str:
    body = sanitize_notification_body(str(item.get("notification_body", "")))
    if body:
        return body
    tag = str(item.get("tag", "官方")).strip() or "官方"
    title = str(item.get("title", "新消息")).strip() or "新消息"
    return sanitize_notification_body(f"NMIXX 有新的{tag}：{title}")


def run_once(
    config_path: Path,
    dry_run: bool = False,
    runtime_data: RuntimeDataStore | None = None,
    push_service: PushService | None = None,
    minimum_interval_seconds: int | None = None,
) -> int:
    settings: Settings | None = None
    if runtime_data is None:
        settings = Settings.from_env()
        runtime_data = RuntimeDataStore(settings.data_dir, settings.max_generated_updates)
    runtime_data.initialize()
    _, state_path, sources = load_config(config_path, runtime_data.data_dir)
    state = read_json(state_path, {"sources": {}, "events": []})
    if minimum_interval_seconds:
        last_run_raw = state.get("last_run_at")
        if isinstance(last_run_raw, str):
            try:
                last_run = datetime.fromisoformat(last_run_raw)
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=TAIPEI_TZ)
                elapsed = (datetime.now(last_run.tzinfo) - last_run).total_seconds()
                if elapsed < minimum_interval_seconds:
                    print("[interval] update check is not due yet")
                    return 0
            except ValueError:
                pass
    if push_service is None:
        settings = settings or Settings.from_env()
        database = Database(settings)
        database.initialize()
        push_service = PushService(database, settings)
    collected_new_items: list[dict[str, str]] = []
    existing_updates = runtime_data.read_updates()
    now = datetime.now().isoformat(timespec="seconds")

    for source in sources:
        try:
            digest, current_text = fetch_source(source)
        except Exception as error:
            print(f"[error] {source.name}: {error}", file=sys.stderr)
            continue

        source_state = state["sources"].get(source.url)
        if not source_state:
            state["sources"][source.url] = {
                "name": source.name,
                "hash": digest,
                "text": current_text,
                "checked_at": now,
            }
            print(f"[init] {source.name}: baseline saved")
            continue

        previous_hash = source_state.get("hash")
        previous_text = source_state.get("text", "")
        if digest == previous_hash:
            source_state["checked_at"] = now
            print(f"[same] {source.name}: no content change")
            continue

        review = review_change(source, previous_text, current_text, existing_updates)
        new_items = dedupe_items(
            review.get("items", []) if review.get("is_new") else [], source, existing_updates
        )
        if new_items:
            collected_new_items.extend(new_items)
            action = "would add" if dry_run else "added"
            print(f"[updated] {source.name}: {action} {len(new_items)} item(s)")
        else:
            reason = review.get("reason") or "no confident new information"
            print(f"[skip] {source.name}: {reason}")

        review_finished = not review.get("needs_ai") and not review.get("error")
        if dry_run:
            source_state["checked_at"] = now
        elif review_finished:
            source_state.update({"hash": digest, "text": current_text, "checked_at": now})
        else:
            source_state["checked_at"] = now

        state["events"].append(
            {
                "time": now,
                "source": source.name,
                "url": source.url,
                "old_hash": previous_hash,
                "new_hash": digest,
                "ai_review": review,
                "added": new_items,
            }
        )

    if collected_new_items and not dry_run:
        write_generated_updates(runtime_data, collected_new_items)
        latest = collected_new_items[0]
        push_result = push_service.send_notification(
            compact_notification_title(latest),
            push_body_for_item(latest),
            latest["href"],
        )
        print(
            "[push] sent={sent} failed={failed} subscriptions={subscriptions}".format(
                **push_result
            )
        )

    state["events"] = state["events"][-100:]
    if not dry_run:
        state["last_run_at"] = now
        write_json(state_path, state)
    return len(collected_new_items)


def watch(
    config_path: Path,
    runtime_data: RuntimeDataStore | None = None,
    push_service: PushService | None = None,
    minimum_interval_seconds: int | None = None,
) -> None:
    interval, _, _ = load_config(
        config_path, runtime_data.data_dir if runtime_data else None
    )
    while True:
        run_once(
            config_path,
            runtime_data=runtime_data,
            push_service=push_service,
            minimum_interval_seconds=minimum_interval_seconds,
        )
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check official NMIXX sources and update site data.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Check and review without writing files.")
    parser.add_argument("--respect-interval", action="store_true", help="Skip a timer run until UPDATE_INTERVAL_SECONDS has elapsed.")
    args = parser.parse_args()

    settings = Settings.from_env()
    runtime_data = RuntimeDataStore(settings.data_dir, settings.max_generated_updates)
    interval = settings.update_interval_seconds if args.respect_interval else None
    if args.once:
        run_once(args.config, dry_run=args.dry_run, runtime_data=runtime_data, minimum_interval_seconds=interval)
        return
    if args.dry_run:
        run_once(args.config, dry_run=True, runtime_data=runtime_data, minimum_interval_seconds=interval)
        return
    watch(args.config, runtime_data=runtime_data, minimum_interval_seconds=interval)


if __name__ == "__main__":
    main()
