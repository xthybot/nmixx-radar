from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import HTTPException
from PIL import Image

from app.config import Settings
from app.image_proxy import ImageProxy


class ImageProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.settings = Settings.for_test(Path(self.temporary_directory.name) / "runtime")
        self.proxy = ImageProxy(self.settings)

    async def asyncTearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_only_https_allowlisted_sources_are_accepted(self) -> None:
        with self.assertRaises(HTTPException):
            self.proxy.validate_source("http://i.ytimg.com/vi/example.jpg")
        with self.assertRaises(HTTPException):
            self.proxy.validate_source("https://untrusted.example/image.jpg")

    async def test_redirects_are_rejected_instead_of_followed(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"location": "https://i.ytimg.com/next.jpg"})
        )
        proxy = ImageProxy(self.settings, transport=transport)

        with self.assertRaises(HTTPException) as raised:
            await proxy.fetch_source("https://i.ytimg.com/vi/example.jpg")

        self.assertEqual(raised.exception.status_code, 502)

    async def test_pixel_bomb_is_rejected_before_resize(self) -> None:
        raw = BytesIO()
        Image.new("RGB", (4000, 4000), color="white").save(raw, format="PNG")

        async def fake_fetch(source: str) -> bytes:
            return raw.getvalue()

        self.proxy.fetch_source = fake_fetch  # type: ignore[method-assign]

        with self.assertRaises(HTTPException) as raised:
            await self.proxy.get_optimized_image("https://i.ytimg.com/vi/example.jpg", 900, 74)

        self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
