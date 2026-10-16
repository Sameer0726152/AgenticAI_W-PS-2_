"""Keeps LLM usage under the provider's tokens-per-minute and tokens-per-day limits."""
import threading
import time
from collections import deque
from datetime import datetime, timezone

from app import config

SAFETY = 0.85  # use at most 85% of the per-minute limit
WINDOW = 60.0


class BudgetExceeded(Exception):
    pass


def utc_today():
    return datetime.now(timezone.utc).date()


class RateLimiter:
    def __init__(self, tpm: int, tpd: int):
        self.tpm_budget = int(tpm * SAFETY)
        self.tpd = tpd
        self._window: deque[list] = deque()  # [timestamp, tokens]
        self._day = utc_today()
        self._used_today = 0
        self._lock = threading.Lock()

    @property
    def used_today(self) -> int:
        self._roll_day()
        return self._used_today

    def set_used_today(self, tokens: int) -> None:
        """Restore today's usage after a restart (from the LLM cache table)."""
        with self._lock:
            self._day, self._used_today = utc_today(), tokens

    def _roll_day(self) -> None:
        if utc_today() != self._day:
            self._day, self._used_today = utc_today(), 0

    def acquire(self, estimated: int) -> list:
        """Block until `estimated` tokens fit in the last-minute window; returns a reservation."""
        while True:
            with self._lock:
                self._roll_day()
                if self._used_today + estimated > self.tpd:
                    raise BudgetExceeded(f"Daily LLM token budget ({self.tpd}) would be exceeded")
                now = time.monotonic()
                while self._window and now - self._window[0][0] >= WINDOW:
                    self._window.popleft()
                used = sum(t for _, t in self._window)
                if not self._window or used + estimated <= self.tpm_budget:
                    entry = [now, estimated]
                    self._window.append(entry)
                    return entry
                wait = WINDOW - (now - self._window[0][0]) + 0.1
            time.sleep(wait)

    def record(self, entry: list, actual: int) -> None:
        """Replace a reservation's estimate with the real token count."""
        with self._lock:
            entry[1] = actual
            self._roll_day()
            self._used_today += actual


limiter = RateLimiter(config.LLM_TPM_LIMIT, config.LLM_TPD_LIMIT)
