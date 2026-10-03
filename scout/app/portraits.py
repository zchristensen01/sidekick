"""Champion pictures for the app (M14): Data Dragon's square portraits, cached on disk.

Data Dragon serves each champion's square picture at
https://ddragon.leagueoflegends.com/cdn/<version>/img/champion/<champion id>.png
(the same id as everywhere else in Sidekick). `scout refresh` downloads the missing ones;
the page asks for the ones it shows and gets them as data: URIs (the window has no web server,
so this is the simplest way to show a local picture).
"""

import base64
import re
import threading
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx

from scout.data.ddragon import BASE
from scout.data.fetch import USER_AGENT

ID = re.compile(r"[A-Za-z0-9]{1,40}")
Get = Callable[[str], bytes]


def url(version: str, champ: str) -> str:
    return f"{BASE}/cdn/{version}/img/champion/{champ}.png"


def http_get(timeout_s: float = 15.0) -> Get:
    client = httpx.Client(timeout=timeout_s, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT})  # fmt: skip

    def get(address: str) -> bytes:
        response = client.get(address)
        response.raise_for_status()
        return response.content

    return get


class Portraits:
    """Pictures in `folder` (data/cache/img/champion); downloads the missing ones if `get`."""

    def __init__(self, folder: Path, version: str, known: Iterable[str],
                 get: Get | None = None) -> None:  # fmt: skip
        self.folder, self.version, self.get = folder, version, get
        self.known = set(known)
        self._failed: set[str] = set()
        self._lock = threading.Lock()

    def path(self, champ: str) -> Path | None:
        """Where a champion's picture lives; None for anything that isn't a known id."""
        if champ not in self.known or not ID.fullmatch(champ):
            return None
        return self.folder / f"{champ}.png"

    def load(self, champ: str) -> bytes | None:
        path = self.path(champ)
        if path is None:
            return None
        if path.exists():
            return path.read_bytes()
        with self._lock:
            if self.get is None or champ in self._failed:
                return None
        try:
            data = self.get(url(self.version, champ))
        except Exception:  # offline or a missing picture: show initials instead
            with self._lock:
                self._failed.add(champ)
            return None
        if not data.startswith(b"\x89PNG"):
            with self._lock:
                self._failed.add(champ)
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
        return data

    def data_uri(self, champ: str) -> str | None:
        data = self.load(champ)
        return "data:image/png;base64," + base64.b64encode(data).decode() if data else None

    def many(self, champs: Iterable[str]) -> dict[str, str]:
        found = {}
        for champ in dict.fromkeys(champs):
            uri = self.data_uri(champ)
            if uri:
                found[champ] = uri
        return found

    def fetch_missing(self) -> tuple[int, int]:
        """Download every known champion's picture that isn't saved yet: (got, failed)."""
        got = failed = 0
        for champ in sorted(self.known):
            path = self.path(champ)
            if path is None or path.exists():
                continue
            if self.load(champ):
                got += 1
            else:
                failed += 1
        return got, failed
