"""Named waits for the page objects, in milliseconds, from
config/environments.ini's [waits] section.

Two budgets (do not mix them up):

* **settle_*** — blind ``wait_for_timeout`` pauses after a click/toggle/cache
  flush. Keep these small; the UI should finish sooner and callers that need
  a condition should use ``expect`` instead.
* **tiny / short / medium / long / extra_long** — ceilings for ``expect``,
  ``click(timeout=...)``, ``goto``, etc. High values only matter on failure
  (or when the UI is genuinely slow); they do not add time on the happy path.
* **poll_interval** — pause inside a polling loop.

[browser] timeout stays the overall default. Read once per session.
"""
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Waits:
    settle_tiny: int
    settle_short: int
    settle_medium: int
    tiny: int
    short: int
    medium: int
    long: int
    extra_long: int
    poll_interval: int


@lru_cache(maxsize=1)
def waits() -> Waits:
    """The [waits] settings. load_config is imported here so the page objects
    keep no import-time dependency on config."""
    from config.config_reader import load_config

    config = load_config()
    # No fallbacks: environments.ini is the one source of truth, so a missing
    # key raises configparser's own error naming the section and key rather
    # than silently using a stale default copied into this file.
    return Waits(
        settle_tiny=config.getint("waits", "settle_tiny_ms"),
        settle_short=config.getint("waits", "settle_short_ms"),
        settle_medium=config.getint("waits", "settle_medium_ms"),
        tiny=config.getint("waits", "tiny_ms"),
        short=config.getint("waits", "short_ms"),
        medium=config.getint("waits", "medium_ms"),
        long=config.getint("waits", "long_ms"),
        extra_long=config.getint("waits", "extra_long_ms"),
        poll_interval=config.getint("waits", "poll_interval_ms"),
    )
