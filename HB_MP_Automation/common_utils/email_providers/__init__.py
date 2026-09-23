"""Gmail inbox client for wait_for_email*."""

from __future__ import annotations

from functools import lru_cache

from common_utils.email_providers.gmail_imap import GmailProvider, gmail_credentials

__all__ = [
    "GmailProvider",
    "is_test_inbox_email",
    "provider_for_address",
    "test_inbox_address",
]


@lru_cache(maxsize=1)
def _gmail() -> GmailProvider:
    return GmailProvider()


def provider_for_address(email: str):
    """The Gmail account in secrets.ini. ``email`` is the guest address logged on the message."""
    del email
    return _gmail()


def test_inbox_address(tag: str) -> str:
    """Guest address: the Gmail account in secrets.ini [gmail], unchanged."""
    del tag
    base, _password = gmail_credentials()
    return base.strip()


def is_test_inbox_email(address: str) -> bool:
    """True when ``address`` is exactly the configured Gmail account."""
    text = (address or "").strip().lower()
    if not text or "@" not in text:
        return False
    base, _password = gmail_credentials()
    return text == base.strip().lower()
