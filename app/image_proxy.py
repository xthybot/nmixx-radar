from __future__ import annotations

import asyncio
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings


ALLOWED_HOSTS = {
    "d1al7qj7ydfbpt.cloudfront.net",
    "d1meds70430yck.cloudfront.net",
    "i.ytimg.com",
}
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_SOURCE_PIXELS = 12_000_000
MAX_WIDTH = 1600


def image_url(source: str, width: int, quality: int) -> str:
    return "/image?" + urlencode({"url": source, "w": width, "q": quality})


class ImageProxy:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.cache_dir = settings.data_dir / "image_cache"
        self.transport = transport

    def validate_source(self, source: str) -> str:
        parsed = urlparse(source)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username
            or parsed.password
        ):
            raise HTTPException(status_code=400, detail="Unsupported image source.")
        return source

    def _cache_path(self, source: str, width: int, quality: int) -> Path:
        key = sha256(f"{source}|{width}|{quality}|webp-v2".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.webp"

    async def fetch_source(self, source: str) -> bytes:
        timeout = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            headers={"User-Agent": "nmixx-radar-image-proxy/1.0"},
            transport=self.transport,
        ) as client:
            try:
                async with client.stream("GET", source) as response:
                    if response.is_redirect:
                        raise HTTPException(status_code=502, detail="Image source redirects are not allowed.")
                    if response.status_code >= 400:
                        raise HTTPException(status_code=502, detail="Image fetch failed.")
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > MAX_SOURCE_BYTES:
                        raise HTTPException(status_code=413, detail="Image is too large.")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes(64 * 1024):
                        total += len(chunk)
                        if total > MAX_SOURCE_BYTES:
                            raise HTTPException(status_code=413, detail="Image is too large.")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except HTTPException:
                raise
            except (httpx.HTTPError, ValueError) as error:
                raise HTTPException(status_code=502, detail="Image fetch failed.") from error

    def _write_optimized_image(self, raw: bytes, output_path: Path, width: int, quality: int) -> None:
        try:
            with Image.open(BytesIO(raw)) as image:
                if image.width * image.height > MAX_SOURCE_PIXELS:
                    raise HTTPException(status_code=413, detail="Image has too many pixels.")
                optimized = ImageOps.exif_transpose(image).convert("RGB")
                if optimized.width > width:
                    ratio = width / optimized.width
                    height = max(1, round(optimized.height * ratio))
                    optimized = optimized.resize((width, height), Image.Resampling.LANCZOS)
                self.cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                self.cache_dir.chmod(0o700)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{output_path.name}.", suffix=".tmp", dir=self.cache_dir
                )
                temporary_path = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "wb") as temporary_file:
                        optimized.save(temporary_file, format="WEBP", quality=quality, method=5)
                        temporary_file.flush()
                        os.fsync(temporary_file.fileno())
                    os.chmod(temporary_path, 0o600)
                    os.replace(temporary_path, output_path)
                    os.chmod(output_path, 0o600)
                finally:
                    if temporary_path.exists():
                        temporary_path.unlink()
        except HTTPException:
            raise
        except (OSError, UnidentifiedImageError) as error:
            raise HTTPException(status_code=502, detail="Image optimization failed.") from error

    def _trim_cache(self) -> None:
        if not self.cache_dir.exists():
            return
        files = sorted(
            (path for path in self.cache_dir.glob("*.webp") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
        )
        total = sum(path.stat().st_size for path in files)
        for path in files:
            if total <= self.settings.max_image_cache_bytes:
                break
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size

    async def get_optimized_image(self, source: str, width: int, quality: int) -> FileResponse:
        source = self.validate_source(source)
        width = min(max(width, 120), MAX_WIDTH)
        quality = min(max(quality, 60), 82)
        output_path = self._cache_path(source, width, quality)
        if not output_path.exists():
            raw = await self.fetch_source(source)
            await asyncio.to_thread(self._write_optimized_image, raw, output_path, width, quality)
            await asyncio.to_thread(self._trim_cache)
        return FileResponse(
            output_path,
            media_type="image/webp",
            headers={"Cache-Control": "private, max-age=604800, immutable"},
        )
