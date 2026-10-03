"""Downloads for `scout refresh`: one polite HTTP client with a per-version file cache.

Raw responses are saved under data/cache/<source>/<version>/ so a rebuild doesn't hit the
network again (docs/DATA.md: Storage layout, Being a polite client). Tests use a fake with the
same two methods and never touch the network (CLAUDE.md hard rule 7).
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from scout import __version__

USER_AGENT = f"sidekick-scout/{__version__} (personal, non-commercial)"


class FetchError(Exception):
    """A download failed after retries."""


class NotFound(FetchError):
    """The server says the URL doesn't exist (HTTP 404)."""


class Fetcher(Protocol):
    def text(self, url: str, cache: Path | None = None, *, refresh: bool = False) -> str: ...

    def json(self, url: str, cache: Path | None = None, *, refresh: bool = False) -> Any: ...


@dataclass
class HttpFetcher:
    """GET with retries. With `cache`, reuse the saved copy unless `refresh` is set."""

    timeout_s: float = 30.0
    retries: int = 2
    log: list[dict[str, Any]] = field(default_factory=list)  # one entry per URL, for manifests

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            timeout=self.timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )

    def text(self, url: str, cache: Path | None = None, *, refresh: bool = False) -> str:
        if cache is not None and cache.exists() and not refresh:
            self.log.append({"url": url, "from_cache": True})
            return cache.read_text(encoding="utf-8")
        started = time.monotonic()
        body = self._download(url)
        self.log.append({
            "url": url, "from_cache": False,
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        })  # fmt: skip
        if cache is not None:
            write_atomic(cache, body)
        return body

    def json(self, url: str, cache: Path | None = None, *, refresh: bool = False) -> Any:
        return json.loads(self.text(url, cache, refresh=refresh))

    def close(self) -> None:
        self._client.close()

    def _download(self, url: str) -> str:
        for attempt in range(self.retries + 1):
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                error = f"{url}: {exc}"
            else:
                if response.status_code == 404:
                    raise NotFound(f"{url}: HTTP 404")
                if response.is_success:
                    return response.text
                error = f"{url}: HTTP {response.status_code}"
                if response.status_code < 500 and response.status_code != 429:
                    break  # a client error won't fix itself
            if attempt < self.retries:
                time.sleep(1.0 + attempt)
        raise FetchError(error)


def write_atomic(path: Path, text: str) -> None:
    """Write via a temporary file so a crash never leaves half a file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)
