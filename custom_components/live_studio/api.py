"""Small injectable client for the local Live Studio API."""

import asyncio
from urllib.parse import urlsplit

import aiohttp


class StudioError(Exception):
    pass


class StudioAuthError(StudioError):
    pass


def endpoint(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use an HTTP(S) origin without path or credentials")
    return value.rstrip("/")


class StudioClient:
    def __init__(self, session, url, token):
        self.session = session
        self.url = endpoint(url)
        self.token = token

    async def request(self, path, data=None):
        try:
            async with self.session.request(
                "GET" if data is None else "POST",
                self.url + "/api/" + path,
                json=data,
                headers={"Authorization": "Bearer " + self.token},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 401:
                    raise StudioAuthError("Authentication failed")
                if response.status >= 400:
                    raise StudioError("Engine rejected the operation")
                result = await response.json()
                if not isinstance(result, dict):
                    raise StudioError("Invalid engine response")
                return result
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            raise StudioError("Engine unavailable or invalid response") from None

    async def image(self, identity):
        try:
            async with self.session.get(
                self.url + "/api/cameras/" + identity + "/snapshot.jpg",
                headers={"Authorization": "Bearer " + self.token},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 401:
                    raise StudioAuthError("Authentication failed")
                if response.status != 200:
                    raise StudioError("No fresh image")
                data = await response.read()
                if not data.startswith(b"\xff\xd8"):
                    raise StudioError("Invalid image")
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise StudioError("Camera unavailable") from None
