"""Named waits for the page objects, in milliseconds, from
config/environments.ini's [waits] section: short (a control settling - a
checkbox ticking, a dialog closing), medium (a section or grid loading), long
(a slow one-off screen, e.g. signing or a document generating) and
poll_interval (the pause inside a polling loop).

[browser] timeout stays the overall wait, and everything derived from it
(self.timeout / 2, / 500 ...) still follows it. These name the shorter roles
that were repeated as literals across the page objects, so they're tuned in
one place. Read once per session; the defaults match the values the code used
before, so a missing [waits] section changes nothing."""
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Waits:
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
        tiny=config.getint("waits", "tiny_ms"),
        short=config.getint("waits", "short_ms"),
        medium=config.getint("waits", "medium_ms"),
        long=config.getint("waits", "long_ms"),
        extra_long=config.getint("waits", "extra_long_ms"),
        poll_interval=config.getint("waits", "poll_interval_ms"),
    )
