import random
import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def _get_robots(base_url: str) -> urllib.robotparser.RobotFileParser:
    if base_url not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(base_url + "/robots.txt")
        rp.read()
        _robots_cache[base_url] = rp
    return _robots_cache[base_url]


def can_fetch(url: str) -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    rp = _get_robots(base)
    return rp.can_fetch(BASE_HEADERS["User-Agent"], url)


class BaseScraper:
    def __init__(self, rate_min: float = 1.0, rate_max: float = 2.5):
        self.client = httpx.Client(headers=BASE_HEADERS, timeout=30, follow_redirects=True)
        self.rate_min = rate_min
        self.rate_max = rate_max
        self._last_request: float = 0.0

    def _wait(self):
        elapsed = time.time() - self._last_request
        delay = random.uniform(self.rate_min, self.rate_max)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.time()

    def get(self, url: str) -> httpx.Response | None:
        if not can_fetch(url):
            print(f"[SKIP] robots.txt disallows: {url}")
            return None
        self._wait()
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            print(f"[HTTP {e.response.status_code}] {url}")
            return None
        except httpx.RequestError as e:
            print(f"[ERROR] {url}: {e}")
            return None

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
