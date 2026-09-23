"""Gmail IMAP backend.

Guests use the address in secrets.ini [gmail] exactly. All Mail does not
include Spam, so a poll opens Spam only when All Mail has nothing from the
last two minutes. Search uses IMAP SINCE, not X-GM-RAW, because Gmail's raw
index lags behind newly delivered mail. SINCE is day-only, so it only builds
the id list. Headers are downloaded for the last 10 minutes.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime

from common_utils.email_providers._http import TransientInboxError

logger = logging.getLogger(__name__)

_IMAP_HOST = "imap.gmail.com"
_IMAP_PORT = 993
_LOCK = threading.Lock()
_ALL_MAIL = "[Gmail]/All Mail"
_SPAM = "[Gmail]/Spam"
# all:<uid> and spam:<uid>. UIDs are only unique inside one mailbox.
_MAILBOX_FOR_PREFIX = {"all": _ALL_MAIL, "spam": _SPAM}
# How far back a poll downloads headers. The confirmation itself still has
# to be under two minutes old; this only limits the download.
_HEADER_WINDOW_MS = 10 * 60 * 1000


def gmail_credentials() -> tuple[str, str]:
    """(address, app password) from secrets.ini [gmail]."""
    from config.config_reader import load_config

    config = load_config()
    if not config.has_section("gmail"):
        raise RuntimeError(
            "secrets.ini [gmail] is missing. Set email and app_password "
            "(Google Account → Security → App passwords)."
        )
    address = config.get("gmail", "email", fallback="", raw=True).strip()
    password = config.get("gmail", "app_password", fallback="", raw=True).strip()
    password = password.replace(" ", "")
    if not address or not password:
        raise RuntimeError(
            "secrets.ini [gmail] email and app_password are required when "
            "provider=gmail. Use a Google App Password, not the login password."
        )
    return address, password


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    chunks: list[str] = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            chunks.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            chunks.append(text)
    return "".join(chunks)


def _time_ms(value: str | None) -> int:
    if not value:
        return 0
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _body_parts(message: email.message.Message) -> list[dict]:
    html_parts: list[dict] = []
    plain_parts: list[dict] = []

    def take(part: email.message.Message) -> None:
        if part.get_content_type() not in {"text/html", "text/plain"}:
            return
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        body = {"body": payload.decode(charset, errors="replace")}
        if part.get_content_type() == "text/html":
            html_parts.append(body)
        else:
            plain_parts.append(body)

    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            take(part)
    else:
        take(message)
    return html_parts + plain_parts


def _age_ms(message_time_ms: int) -> int | None:
    if not message_time_ms:
        return None
    return int(time.time() * 1000) - int(message_time_ms)


def _recent_ms(message_time_ms: int) -> bool:
    """True when a header Date is less than two minutes old."""
    age_ms = _age_ms(message_time_ms)
    return age_ms is not None and -60_000 < age_ms < 120_000


def _in_header_window(message_time_ms: int) -> bool:
    """True when a header Date is inside the last 10 minutes."""
    age_ms = _age_ms(message_time_ms)
    return age_ms is not None and -60_000 < age_ms < _HEADER_WINDOW_MS


def _split_message_id(message_id: str) -> tuple[str, str]:
    prefix, sep, uid = message_id.partition(":")
    if sep and prefix in _MAILBOX_FOR_PREFIX:
        return prefix, uid
    return "all", message_id


def _auth_failure(error: BaseException) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "invalid credentials",
            "authenticationfailed",
            "application-specific password",
            "username and password not accepted",
            "web login required",
        )
    )


class GmailProvider:
    def __init__(self) -> None:
        self._imap: imaplib.IMAP4_SSL | None = None
        # Header summaries already read, keyed by mailbox:uid. A later poll
        # only downloads headers for UIDs that were not in the previous search.
        self._headers: dict[str, dict] = {}
        self._spam_empty_until = 0.0

    def list_summaries(
        self,
        address: str,
        *,
        deadline: float | None = None,
        soft: bool = False,
    ) -> list[dict]:
        del deadline
        try:
            with _LOCK:
                imap = self._connection()
                summaries = self._mailbox_summaries(imap, "all", _ALL_MAIL)
                if summaries is None:
                    summaries = self._mailbox_summaries(imap, "all", "INBOX") or []
                # Spam is separate from All Mail. Open it only when All Mail
                # has nothing from the last two minutes, so a normal poll is
                # one mailbox instead of a second full scan.
                newest = max((item.get("time", 0) for item in summaries), default=0)
                if not _recent_ms(newest) and time.monotonic() >= self._spam_empty_until:
                    spam = self._mailbox_summaries(imap, "spam", _SPAM) or []
                    if spam:
                        summaries.extend(spam)
                    else:
                        self._spam_empty_until = time.monotonic() + 30
                logger.info(
                    "Gmail listed %s messages from the last 10 minutes for %s",
                    len(summaries),
                    address,
                )
                return sorted(summaries, key=lambda item: item.get("time", 0))
        except RuntimeError:
            raise
        except (imaplib.IMAP4.error, OSError, TransientInboxError) as error:
            self._drop()
            if _auth_failure(error):
                raise RuntimeError(
                    "Gmail IMAP login failed. Put a Google App Password in "
                    "secrets.ini [gmail] app_password (Google Account → Security "
                    "→ App passwords)."
                ) from error
            if soft:
                raise TransientInboxError(f"Gmail IMAP unavailable: {error}") from error
            raise RuntimeError(f"Gmail IMAP request failed: {error}") from error

    def get_message(
        self,
        message_id: str,
        *,
        deadline: float | None = None,
        soft: bool = False,
    ) -> dict:
        del deadline
        prefix, uid = _split_message_id(message_id)
        mailbox = _MAILBOX_FOR_PREFIX.get(prefix, _ALL_MAIL)
        try:
            with _LOCK:
                imap = self._connection()
                if not self._select_mailbox(imap, mailbox):
                    if not self._select_mailbox(imap, "INBOX"):
                        raise TransientInboxError(
                            f"Gmail mailbox select failed for {mailbox}"
                        )
                raw = self._fetch(imap, uid.encode(), "(BODY.PEEK[])")
                message = email.message_from_bytes(raw)
                return {
                    "id": message_id,
                    "subject": _decode_mime(message.get("Subject")),
                    "time": _time_ms(message.get("Date")),
                    "parts": _body_parts(message),
                }
        except RuntimeError:
            raise
        except (imaplib.IMAP4.error, OSError, TransientInboxError) as error:
            self._drop()
            if _auth_failure(error):
                raise RuntimeError(
                    "Gmail IMAP login failed. Put a Google App Password in "
                    "secrets.ini [gmail] app_password."
                ) from error
            if soft:
                raise TransientInboxError(f"Gmail IMAP unavailable: {error}") from error
            raise RuntimeError(f"Gmail IMAP request failed: {error}") from error

    def _connection(self) -> imaplib.IMAP4_SSL:
        if self._imap is not None:
            try:
                self._imap.noop()
                return self._imap
            except (imaplib.IMAP4.error, OSError):
                self._drop()
        address, password = gmail_credentials()
        imap = imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT)
        try:
            imap.login(address, password)
        except imaplib.IMAP4.error as error:
            try:
                imap.logout()
            except (imaplib.IMAP4.error, OSError):
                pass
            if _auth_failure(error):
                raise RuntimeError(
                    "Gmail IMAP login failed. Put a Google App Password in "
                    "secrets.ini [gmail] app_password (Google Account → Security "
                    "→ App passwords) and turn IMAP on in Gmail settings."
                ) from error
            raise
        self._imap = imap
        self._headers.clear()
        self._spam_empty_until = 0.0
        logger.info("Gmail IMAP connected for %s", address)
        return imap

    def _select_mailbox(self, imap: imaplib.IMAP4_SSL, mailbox: str) -> bool:
        # Selecting the mailbox already open returns a stale view, so a
        # confirmation that arrives mid-poll never shows up. Close first.
        try:
            imap.close()
        except (imaplib.IMAP4.error, OSError):
            pass
        typ, _data = imap.select(mailbox, readonly=True)
        return typ == "OK"

    def _mailbox_summaries(
        self, imap: imaplib.IMAP4_SSL, prefix: str, mailbox: str
    ) -> list[dict] | None:
        if not self._select_mailbox(imap, mailbox):
            return None
        uids = self._search_uids(imap)
        if not uids:
            return []
        # UIDs rise as mail arrives, so the tail is the newest mail. Download
        # that tail until a header is older than 10 minutes and leave the rest.
        summaries = self._summaries_in_header_window(imap, prefix, uids)
        logger.info(
            "Gmail %s: %s ids on the date search, %s headers in the last 10 minutes",
            mailbox,
            len(uids),
            len(summaries),
        )
        return summaries

    def _summaries_in_header_window(
        self, imap: imaplib.IMAP4_SSL, prefix: str, uids: list[bytes]
    ) -> list[dict]:
        kept: list[dict] = []
        pending: list[bytes] = []

        def consume_pending() -> bool:
            """Download the current tail. True once a header is outside the window."""
            if not pending:
                return False
            fetched = self._fetch_headers(imap, list(pending))
            reached_older = False
            for uid in pending:
                uid_text = uid.decode()
                header = fetched.get(uid_text)
                if header is None:
                    continue
                summary = self._remember_header(prefix, uid_text, header)
                if reached_older or not _in_header_window(summary["time"]):
                    reached_older = True
                    continue
                kept.append(summary)
            pending.clear()
            return reached_older

        for uid in reversed(uids):
            cached = self._headers.get(f"{prefix}:{uid.decode()}")
            if cached is None:
                pending.append(uid)
                if len(pending) >= 10 and consume_pending():
                    return kept
                continue
            if consume_pending():
                return kept
            if not _in_header_window(cached.get("time", 0)):
                return kept
            kept.append(cached)
        consume_pending()
        return kept

    def _remember_header(self, prefix: str, uid: str, header: bytes) -> dict:
        message = email.message_from_bytes(header)
        summary = {
            "id": f"{prefix}:{uid}",
            "subject": _decode_mime(message.get("Subject")),
            "time": _time_ms(message.get("Date")),
        }
        self._headers[summary["id"]] = summary
        return summary

    @staticmethod
    def _fetch_headers(imap: imaplib.IMAP4_SSL, uids: list[bytes]) -> dict[str, bytes]:
        """One UID FETCH for every header. Per-message fetches were ~12s a poll."""
        typ, data = imap.uid(
            "FETCH",
            b",".join(uids),
            "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])",
        )
        if typ != "OK" or not data:
            raise TransientInboxError("Gmail header fetch failed")
        headers: dict[str, bytes] = {}
        for item in data:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            meta = item[0] if isinstance(item[0], bytes) else b""
            match = re.search(br"\bUID (\d+)", meta)
            if not match:
                continue
            headers[match.group(1).decode()] = item[1]
        if not headers:
            raise TransientInboxError("Gmail header fetch returned no messages")
        return headers

    @staticmethod
    def _search_uids(imap: imaplib.IMAP4_SSL) -> list[bytes]:
        since = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%d-%b-%Y")
        typ, data = imap.uid("SEARCH", "SINCE", since)
        if typ != "OK":
            typ, data = imap.uid("SEARCH", "ALL")
        if typ != "OK":
            raise TransientInboxError("Gmail search failed")
        return (data[0] or b"").split()

    @staticmethod
    def _fetch(imap: imaplib.IMAP4_SSL, uid: bytes, what: str) -> bytes:
        typ, data = imap.uid("FETCH", uid, what)
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise TransientInboxError(f"Gmail fetch failed for uid {uid!r}")
        return data[0][1]

    def _drop(self) -> None:
        imap = self._imap
        self._imap = None
        if imap is None:
            return
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
