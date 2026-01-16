import os
import random
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session: Optional[Session] = None
_rate_lock = threading.Lock()


class SimpleRateLimiter:
    def __init__(self, rate_per_sec=0.25, burst=1):
        self.rate = float(rate_per_sec);
        self.capacity = int(burst)
        self.tokens = float(burst);
        self.last = time.monotonic();
        self.lock = threading.Lock()
    
    def acquire(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1.0:
                time.sleep(max(0.05, (1.0 - self.tokens) / self.rate))
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class CircuitBreaker:
    def __init__(self, cooldown_s=900):
        self.cooldown = cooldown_s;
        self.until = 0.0;
        self.lock = threading.Lock()
    
    def is_open(self): return time.monotonic() < self.until
    
    def trip(self):
        with self.lock:
            self.until = time.monotonic() + self.cooldown


_rate = SimpleRateLimiter(rate_per_sec=float(os.getenv("SNOMED_RATE_PER_SEC", "0.25")))
_cb = CircuitBreaker(cooldown_s=int(os.getenv("SNOMED_OFFLINE_COOLDOWN_S", "900")))


def _make_http_session() -> Session:
    s = Session()
    retry = Retry(
        total=2, backoff_factor=0.25,
        status_forcelist=[500, 502, 503, 504],  # exclude 429
        allowed_methods=["GET", "HEAD", "OPTIONS"],
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=50))
    s.headers.update({"User-Agent": "KeywordService/1.0 (+python-requests)"})
    return s


def _retry_after_delay(headers) -> Optional[int]:
    ra = headers.get("Retry-After")
    if not ra: return None
    try:
        return max(1, int(ra))
    except ValueError:
        try:
            return max(1, int((parsedate_to_datetime(ra) - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            return None


def http_session() -> Session:
    global _session
    if _session is None:
        _session = _make_http_session()
    return _session


def get_with_backoff(url: str, **kwargs) -> requests.Response:
    if _cb.is_open():
        raise requests.exceptions.RetryError(f"SNOMED circuit open; skipping {url}")
    attempts = 0
    while True:
        attempts += 1
        _rate.acquire()
        r = http_session().get(url, **kwargs)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        delay = _retry_after_delay(r.headers)
        if delay is None:
            delay = min(60, 2 ** min(attempts, 6))
        if attempts >= 2:
            _cb.trip()
            raise requests.exceptions.RetryError(f"429 after {attempts} attempts for {url}")
        time.sleep(delay + random.uniform(0, 0.5))


def install_requests_cache_if_enabled():
    if os.getenv("ENABLE_REQUESTS_CACHE", "0") not in ("1", "true", "True"):
        return
    try:
        import requests_cache, pathlib
        cache_path = os.getenv("REQUESTS_CACHE_PATH", "/tmp/snomed_http_cache.sqlite")
        pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        expire = int(os.getenv("REQUESTS_CACHE_EXPIRE_S", "86400"))
        requests_cache.install_cache(cache_path, expire_after=expire)
    except Exception:
        pass
