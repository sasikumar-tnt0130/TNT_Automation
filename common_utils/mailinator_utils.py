import html
import re
import time

import requests

MAILINATOR_API_BASE = "https://www.mailinator.com/api/v2/domains/public"

# Confirmed live 2026-09-08 and re-confirmed 2026-09-09: Mailinator's
# free public API intermittently returns a bare 500 with no body on an
# otherwise-valid request (not a real error - retrying the same request
# moments later succeeds, and spot-checks both days saw roughly 1-in-5
# requests succeed - i.e. per-call failure probability ~0.8), so every
# call here retries generously instead of treating one 500 as "no
# email". 15 retries still had a ~0.8**15 =~ 3.5% chance of exhausting
# every attempt on an unlucky run (confirmed live 2026-09-09 - hit
# exactly that during a real test run) - 25 drops that to
# 0.8**25 =~ 0.4%.
_HTTP_RETRIES = 60
_HTTP_RETRY_DELAY = 4


def _inbox_name(email: str) -> str:
    """Mailinator's public API addresses inboxes by their local-part
    (the text before '@'), not the full address."""
    return email.split("@", 1)[0]


def _get_json(url: str) -> dict:
    last_error: Exception | None = None
    for _ in range(_HTTP_RETRIES):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except (requests.HTTPError, requests.exceptions.JSONDecodeError) as error:
            last_error = error
            time.sleep(_HTTP_RETRY_DELAY)
    raise RuntimeError(f"Mailinator API request failed after retries: {url}") from last_error


def wait_for_email(email: str, subject_contains: str | None = None, timeout: float = 120) -> dict:
    """Polls the given Mailinator public inbox until a message appears
    (optionally matching `subject_contains`, case-insensitive), then
    returns that message's full body. Raises TimeoutError if none
    arrives in time - Mailinator's free public API has no delivery SLA,
    so this is a real wait, not a single check."""
    inbox = _inbox_name(email)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        data = _get_json(f"{MAILINATOR_API_BASE}/inboxes/{inbox}")
        for message in data.get("msgs", []):
            if (
                subject_contains
                and subject_contains.lower() not in message.get("subject", "").lower()
            ):
                continue
            return _get_json(f"{MAILINATOR_API_BASE}/messages/{message['id']}")
        time.sleep(5)

    raise TimeoutError(
        f"No email arrived in Mailinator inbox '{inbox}' within {timeout}s"
        + (f" matching subject containing {subject_contains!r}" if subject_contains else "")
    )


def _matching_messages(email: str, subject_contains: str) -> list[dict]:
    """Inbox summaries whose subject contains subject_contains
    (case-insensitive), oldest first."""
    data = _get_json(f"{MAILINATOR_API_BASE}/inboxes/{_inbox_name(email)}")
    return sorted(
        (m for m in data.get("msgs", []) if subject_contains.lower() in m.get("subject", "").lower()),
        key=lambda m: m.get("time", 0),
    )


def latest_email_time(email: str) -> int:
    """Newest message time in the inbox (ms, Mailinator's own clock), 0 if
    empty - a baseline for wait_for_email_after that doesn't depend on this
    machine's clock."""
    data = _get_json(f"{MAILINATOR_API_BASE}/inboxes/{_inbox_name(email)}")
    return max((m.get("time", 0) for m in data.get("msgs", [])), default=0)


def wait_for_email_after(
    email: str, subject_contains: str, after_time: int, timeout: float = 120
) -> dict:
    """Full body of the first message matching subject_contains that arrived
    after after_time (a latest_email_time baseline) - for emails a flow
    sends more than once (e.g. "Auto Payment Confirmation" after a rental
    and again after a later re-enrolment). Counting matches instead proved
    unreliable: confirmed 2026-09-13, one inbox listing showed two such
    emails and a later listing only one."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        newer = [
            m for m in _matching_messages(email, subject_contains) if m.get("time", 0) > after_time
        ]
        if newer:
            return _get_json(f"{MAILINATOR_API_BASE}/messages/{newer[0]['id']}")
        time.sleep(5)
    raise TimeoutError(
        f"No email matching {subject_contains!r} arrived in Mailinator inbox "
        f"'{_inbox_name(email)}' after the baseline within {timeout}s"
    )


def get_email_text(message: dict) -> str:
    """Concatenates every body part (Mailinator splits multipart emails
    into several `parts`, e.g. an HTML part plus a stripped-attachment
    placeholder part) into one string for content assertions."""
    return "\n".join(part.get("body", "") for part in message.get("parts", []))


def get_email_plain_text(message: dict) -> str:
    """get_email_text with styles/tags stripped, HTML entities decoded and
    whitespace collapsed - for phrase and amount assertions against HTML
    emails (e.g. "5&#39; x 5&#39;", "$&nbsp;112.40")."""
    text = re.sub(
        r"<(style|script)\b.*?</\1>", " ", get_email_text(message), flags=re.IGNORECASE | re.DOTALL
    )
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()


def find_email_link(message: dict, link_text: str) -> str:
    """Returns the href of the first link whose visible text is exactly
    link_text - e.g. the reservation confirmation's "Rent Now", confirmed
    live 2026-09-13 as a renter.link short URL that resumes the rental."""
    anchors = re.findall(
        r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        get_email_text(message),
        re.IGNORECASE | re.DOTALL,
    )
    for href, inner_html in anchors:
        if re.sub(r"<[^>]+>|\s+", " ", inner_html).strip() == link_text:
            return html.unescape(href)
    raise AssertionError(
        f"No {link_text!r} link in email {message.get('subject', '')!r}"
    )
