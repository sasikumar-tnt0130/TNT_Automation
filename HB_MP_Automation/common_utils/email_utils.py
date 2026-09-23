"""Inbox wait / parse API used by rental and HB email checks.

Polls the Gmail account in secrets.ini [gmail]. Message shape is
``{id, subject, time, parts}``.
"""

from __future__ import annotations

import html
import logging
import re
import time
from collections.abc import Callable

from common_utils.email_providers import provider_for_address
from common_utils.email_providers._http import TransientInboxError, poll_sleep

logger = logging.getLogger(__name__)

# Shared inbox keeps every earlier confirmation. A reservation, rental, or
# autopay email is only valid when it was sent less than two minutes ago.
CONFIRMATION_MAX_AGE_MS = 120_000


def _fresh_confirmation(message_time_ms: int) -> bool:
    """True when the message Date is less than two minutes old.

    A minute of future skew is allowed so a clock difference on the mail
    server does not hide a message that just arrived.
    """
    if not message_time_ms:
        return False
    age_ms = int(time.time() * 1000) - int(message_time_ms)
    return -60_000 < age_ms < CONFIRMATION_MAX_AGE_MS


def wait_for_email(
    email: str, subject_contains: str | None = None, timeout: float = 120
) -> dict:
    """Poll until a message appears (optional subject match), return full body."""
    provider = provider_for_address(email)
    deadline = time.monotonic() + timeout
    transient_hits = 0
    logger.info(
        "Polling %s for %s (subject %r)",
        type(provider).__name__,
        email,
        subject_contains,
    )

    while time.monotonic() < deadline:
        try:
            summaries = provider.list_summaries(email, deadline=deadline, soft=True)
        except TransientInboxError:
            transient_hits += 1
            if not poll_sleep(deadline):
                break
            continue
        for summary in reversed(summaries):
            if (
                subject_contains
                and subject_contains.lower() not in summary.get("subject", "").lower()
            ):
                continue
            if not _fresh_confirmation(summary.get("time", 0)):
                continue
            try:
                return provider.get_message(
                    summary["id"], deadline=deadline, soft=True
                )
            except TransientInboxError:
                transient_hits += 1
                if not poll_sleep(deadline):
                    break
                break
        else:
            if not poll_sleep(deadline):
                break
            continue
        continue

    detail = (
        f" matching subject containing {subject_contains!r}" if subject_contains else ""
    )
    if transient_hits:
        detail += f" ({transient_hits} inbox read retries)"
    raise TimeoutError(
        f"No email newer than 2 minutes arrived via {type(provider).__name__} "
        f"for '{email}' within {timeout}s{detail}"
    )


def _matching_summaries(
    email: str,
    subject_contains: str,
    *,
    deadline: float | None = None,
    soft: bool = False,
) -> list[dict]:
    provider = provider_for_address(email)
    return [
        m
        for m in provider.list_summaries(email, deadline=deadline, soft=soft)
        if subject_contains.lower() in m.get("subject", "").lower()
    ]


def list_message_summaries(email: str) -> list[dict]:
    """Every message the inbox currently lists, oldest first (id, subject, time)."""
    return provider_for_address(email).list_summaries(email)


def snapshot_inbox_ids(email: str) -> set[str]:
    """Message ids already in the inbox. Call this before the action that sends mail."""
    try:
        ids = {item["id"] for item in list_message_summaries(email)}
    except (RuntimeError, TransientInboxError, OSError) as error:
        logger.warning("Inbox snapshot failed for %s: %s", email, error)
        return set()
    logger.info("Inbox snapshot for %s: %s existing messages", email, len(ids))
    return ids


def message_contains(message: dict, token: str) -> bool:
    """True when ``token`` is in the raw body, the plain text, or either with whitespace removed."""
    raw = get_email_text(message)
    plain = get_email_plain_text(message)
    compact = re.sub(r"\s+", "", plain + raw)
    return token in raw or token in plain or token in compact


def latest_email_time(email: str) -> int:
    """Newest message time in the inbox (ms), 0 if empty."""
    summaries = provider_for_address(email).list_summaries(email)
    return max((m.get("time", 0) for m in summaries), default=0)


def wait_for_email_after(
    email: str, subject_contains: str, after_time: int, timeout: float = 120
) -> dict:
    """First matching message that arrived after ``after_time`` (ms baseline)."""
    provider = provider_for_address(email)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            newer = [
                m
                for m in _matching_summaries(
                    email, subject_contains, deadline=deadline, soft=True
                )
                if m.get("time", 0) > after_time
                and _fresh_confirmation(m.get("time", 0))
            ]
        except TransientInboxError:
            if not poll_sleep(deadline):
                break
            continue
        if newer:
            try:
                return provider.get_message(newer[0]["id"], deadline=deadline, soft=True)
            except TransientInboxError:
                if not poll_sleep(deadline):
                    break
                continue
        if not poll_sleep(deadline):
            break
    raise TimeoutError(
        f"No email matching {subject_contains!r} newer than 2 minutes arrived via "
        f"{type(provider).__name__} for '{email}' after the baseline within {timeout}s"
    )


def wait_for_email_where(
    email: str,
    subject_contains: str,
    matches: Callable[[dict], bool] = lambda message: True,
    after_time: int = 0,
    timeout: float = 120,
    newest: bool = False,
    ignore_ids: set[str] | None = None,
) -> dict:
    """Matching subject after ``after_time`` whose full body passes ``matches``.

    ``ignore_ids`` are messages already in the inbox before this test sent
    mail. A shared Gmail address keeps every earlier confirmation, so those
    ids are skipped and only a message that arrives afterward can match.
    """
    provider = provider_for_address(email)
    prior = set(ignore_ids or ())
    checked: set[str] = set(prior)
    seen_subjects: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            summaries = _matching_summaries(
                email, subject_contains, deadline=deadline, soft=True
            )
        except TransientInboxError:
            if not poll_sleep(deadline):
                break
            continue
        if newest:
            summaries = list(reversed(summaries))
        fresh = [
            item
            for item in summaries
            if item["id"] not in prior and _fresh_confirmation(item.get("time", 0))
        ]
        fresh_subjects = [item.get("subject", "") for item in fresh]
        if fresh_subjects != seen_subjects:
            seen_subjects = fresh_subjects
            logger.info(
                "Inbox %s has %s %r messages, %s under 2 minutes (%s older skipped)",
                email,
                len(summaries),
                subject_contains,
                len(fresh),
                len(summaries) - len(fresh),
            )
        progressed = False
        for summary in summaries:
            if summary["id"] in checked or summary.get("time", 0) <= after_time:
                continue
            if not _fresh_confirmation(summary.get("time", 0)):
                continue
            try:
                message = provider.get_message(
                    summary["id"], deadline=deadline, soft=True
                )
            except TransientInboxError:
                if not poll_sleep(deadline):
                    progressed = True
                    break
                progressed = True
                break
            checked.add(summary["id"])
            message.setdefault("id", summary["id"])
            if matches(message):
                return message
        if progressed:
            continue
        if not poll_sleep(deadline):
            break
    raise TimeoutError(
        f"No matching email {subject_contains!r} newer than 2 minutes arrived via "
        f"{type(provider).__name__} for '{email}' within {timeout}s. "
        f"Ignored {len(prior)} messages already in the inbox. "
        f"New subjects during the wait: {seen_subjects or 'none'}."
    )


def get_email_text(message: dict) -> str:
    """Concatenates every body part into one string for content assertions."""
    return "\n".join(part.get("body", "") for part in message.get("parts", []))


def get_email_plain_text(message: dict) -> str:
    """get_email_text with styles/tags stripped, HTML entities decoded."""
    text = re.sub(
        r"<(style|script)\b.*?</\1>",
        " ",
        get_email_text(message),
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<(?:br|/p|/div|/tr|/li|/h\d)\b[^>]*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r"\n+", "\n", text).strip()


def find_email_link(message: dict, link_text: str) -> str:
    """Href of the first link whose visible text is exactly ``link_text``."""
    anchors = re.findall(
        r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        get_email_text(message),
        re.IGNORECASE | re.DOTALL,
    )
    want = re.sub(r"\s+", " ", link_text).strip().lower()
    for href, inner_html in anchors:
        visible = re.sub(r"<[^>]+>|\s+", " ", inner_html).strip().lower()
        if visible == want:
            return html.unescape(href)
    raise AssertionError(
        f"No {link_text!r} link in email {message.get('subject', '')!r}"
    )


def find_email_link_matching(message: dict, pattern: str) -> str:
    """First link whose visible text matches ``pattern`` (case-insensitive)."""
    anchors = re.findall(
        r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        get_email_text(message),
        re.IGNORECASE | re.DOTALL,
    )
    regex = re.compile(pattern, re.I)
    for href, inner_html in anchors:
        visible = re.sub(r"<[^>]+>|\s+", " ", inner_html).strip()
        if regex.search(visible):
            return html.unescape(href)
    raise AssertionError(
        f"No link matching {pattern!r} in email {message.get('subject', '')!r}"
    )
