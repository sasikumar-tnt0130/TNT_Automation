"""Poll timing for the Gmail inbox wait."""

from __future__ import annotations

import time
from functools import lru_cache


class TransientInboxError(Exception):
    """Inbox read failed for this poll. Wait loops continue; hard callers may retry."""


@lru_cache(maxsize=1)
def inbox_poll_seconds() -> float:
    from config.config_reader import load_config

    return load_config().getfloat("email", "inbox_poll_seconds", fallback=4)


def sleep_until(seconds: float, deadline: float | None) -> bool:
    if seconds <= 0:
        return deadline is None or time.monotonic() < deadline
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        seconds = min(seconds, remaining)
    time.sleep(seconds)
    return deadline is None or time.monotonic() < deadline


def poll_sleep(deadline: float) -> bool:
    return sleep_until(inbox_poll_seconds(), deadline)
