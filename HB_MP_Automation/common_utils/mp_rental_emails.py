import re
import time
from datetime import date
from pathlib import Path

import allure
from playwright.sync_api import BrowserContext

from common_utils.email_utils import (
    find_email_link_matching,
    get_email_plain_text,
    get_email_text,
    list_message_summaries,
    message_contains,
    wait_for_email_where,
)
from common_utils.wrapper_methods import attach_saved_screenshot, save_email_screenshot
from config.config_reader import load_config

# The Two-Step rental's first Rental Confirmation, sent at Pay Now, says
# "Click “Get Access” to provide remaining information required to access
# your space" (confirmed live 2026-09-15, stage/Rutland) - so the second
# one, sent after Get Access, is a newer one without this text.
from common_utils.mp_lease_costs import (
    TWO_STEP_PAY_NOW_EMAIL_MARKER,
    assert_cost_line_items,
    expected_rental_email_move_in_total,
    parse_move_in_total,
)

TWO_STEP_FIRST_EMAIL_TEXT = TWO_STEP_PAY_NOW_EMAIL_MARKER
# How long to wait for that second email lives in config/environments.ini
# [email] second_rental_email_wait_ms - no copy of it here.

_SUPERLEASE_LINK_PATTERN = r"download\s+super\s*-?\s*lease|download\s+lease"


def pdf_text_from_bytes(pdf_bytes: bytes | None) -> str:
    """Extract plain text from PDF bytes (empty string when not a PDF)."""
    if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
        return ""
    from io import BytesIO

    from pypdf import PdfReader

    return "".join(
        (page.extract_text() or "") for page in PdfReader(BytesIO(pdf_bytes)).pages
    )


def _allure_doc_name(document_label: str, space_number: str) -> str:
    """Allure attachment title: lease document name + space id."""
    space = re.sub(r"^#", "", str(space_number or "").strip())
    if space:
        return f"{document_label} #{space}"
    return document_label


def _download_pdf_bytes(context: BrowserContext, url: str) -> tuple[bytes | None, str]:
    """Fetch a CloudFront / PandaDoc PDF with retries.

    Playwright ``APIRequestContext.get`` often hits ``ECONNRESET`` on these
    signed URLs (stage 2026-09-20); retry, then urllib, then an in-browser
    fetch (same approach as HB Documents PDF open).
    """
    errors: list[str] = []

    for attempt in range(1, 4):
        try:
            response = context.request.get(url, timeout=90_000)
            body = response.body()
            if response.status == 200 and body and body[:4] == b"%PDF":
                return body, ""
            errors.append(
                f"request attempt {attempt}: HTTP {response.status}, "
                f"bytes={len(body) if body else 0}"
            )
        except Exception as exc:
            errors.append(f"request attempt {attempt}: {type(exc).__name__}: {exc}")
        time.sleep(1.5 * attempt)

    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read()
        if body and body[:4] == b"%PDF":
            return body, ""
        errors.append(f"urllib: not a PDF (bytes={len(body) if body else 0})")
    except Exception as exc:
        errors.append(f"urllib: {type(exc).__name__}: {exc}")

    page = None
    try:
        page = context.new_page()
        data = page.evaluate(
            """async (url) => {
                const r = await fetch(url, { credentials: 'omit' });
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return Array.from(new Uint8Array(await r.arrayBuffer()));
            }""",
            url,
        )
        body = bytes(data)
        if body[:4] == b"%PDF":
            return body, ""
        errors.append(f"browser fetch: not a PDF (bytes={len(body)})")
    except Exception as exc:
        errors.append(f"browser fetch: {type(exc).__name__}: {exc}")
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass

    return None, "; ".join(errors)[:1500]


def attach_lease_pdf_from_email(
    context: BrowserContext,
    message: dict,
    *,
    space_number: str,
    document_label: str,
    confirmation_dir: Path | None = None,
    attach_allure: bool = False,
) -> tuple[bytes | None, str | None]:
    """Download the Superlease / lease PDF linked from a Rental Confirmation.

    Returns ``(pdf_bytes_or_None, download_url_or_None)``. By default does
    **not** attach the PDF to Allure (``attach_allure=False``) — Compare
    costs attaches Pay Now + Updated Superlease together. Set
    ``attach_allure=True`` only when a caller wants the PDF inline.
    """
    step = _allure_doc_name(document_label, space_number)
    with allure.step(f"Download lease PDF link from email: {step}"):
        try:
            url = find_email_link_matching(message, _SUPERLEASE_LINK_PATTERN)
        except AssertionError as err:
            allure.attach(
                str(err),
                name=f"{step} link not found",
                attachment_type=allure.attachment_type.TEXT,
            )
            return None, None
        body, download_error = _download_pdf_bytes(context, url)
        if body is None:
            allure.attach(
                f"URL: {url}\n{download_error}",
                name=f"{step} download failed",
                attachment_type=allure.attachment_type.TEXT,
            )
            return None, url
        if confirmation_dir is not None:
            safe = re.sub(r"[^\w.-]+", "_", step).strip("_") or "lease"
            confirmation_dir.mkdir(parents=True, exist_ok=True)
            (confirmation_dir / f"{safe}.pdf").write_bytes(body)
        if attach_allure:
            _attach_superlease_pdf_bytes(
                body,
                allure_name=step,
                document_label=document_label,
                space_number=space_number,
            )
        return body, url


def _attach_superlease_pdf_bytes(
    pdf_bytes: bytes,
    *,
    allure_name: str,
    document_label: str,
    space_number: str,
) -> None:
    """Attach a Superlease PDF + space-card screenshot to Allure."""
    allure.attach(
        pdf_bytes,
        name=allure_name,
        attachment_type=allure.attachment_type.PDF,
        extension="pdf",
    )
    try:
        from common_utils.mp_payment_report import attach_payment_screenshots_from_pdf

        attach_payment_screenshots_from_pdf(
            pdf_bytes,
            document_name=document_label,
            space_number=space_number,
        )
    except Exception as exc:
        allure.attach(
            f"{type(exc).__name__}: {exc}"[:500],
            name=f"{allure_name} space-card screenshot failed",
            attachment_type=allure.attachment_type.TEXT,
        )


def ensure_email_superlease_pdf(
    context: BrowserContext,
    artifacts: dict,
    *,
    space_number: str,
    pdf_key: str,
    text_key: str,
    url_key: str,
    document_label: str,
) -> bytes | None:
    """Return PDF bytes from artifacts, retrying CloudFront via ``url_key``."""
    body = artifacts.get(pdf_key)
    if body:
        if not artifacts.get(text_key):
            artifacts[text_key] = pdf_text_from_bytes(body)
        return body
    url = artifacts.get(url_key)
    if not url:
        return None
    body, err = _download_pdf_bytes(context, url)
    if body is None:
        allure.attach(
            f"URL: {url}\n{err}",
            name=f"{_allure_doc_name(document_label, space_number)} retry failed",
            attachment_type=allure.attachment_type.TEXT,
        )
        return None
    artifacts[pdf_key] = body
    artifacts[text_key] = pdf_text_from_bytes(body)
    return body


def assert_rental_confirmation_emails(
    context: BrowserContext,
    confirmation_dir: Path,
    guest: dict,
    space_number: str,
    move_in_date: date,
    amount_paid: float,
    security_deposit: float | None,
    autopay: bool = True,
    get_access_baseline: int | None = None,
    charges: dict[str, float] | None = None,
    body_out: list[str] | None = None,
    lease_artifacts_out: dict | None = None,
) -> str:
    """Old Robot suite's 10604 ("Validate Tenant email for Rental") and 10633
    (its Move-In Date is the lease date), for both storefront rental flows.
    Confirmed live: the rental sends "<property> Rental Confirmation"
    (Two-Step on Chula Vista 2026-09-13, Legacy on Bellflower 2026-09-14) -
    the old "You have successfully completed your rental" wording is gone -
    whose Account Summary lists the name, "Unit Space <space>", "Move-In
    Date: Sep 13, 2026", each charge and "Total Cost To Move-In $ 112.40";
    with autopay, "<property> Auto Payment Confirmation" arrives too.

    When ``charges`` is passed and ``[validation] validate_cost_line_items``
    is true, every label/amount is asserted in the email body too. By
    default only Total Cost To Move-In (already in ``expected`` below) is
    required.

    Returns the Rental Confirmation plain-text body for three-way cost compare
    (MP confirmation page | email | lease agreement).

    ``body_out``: when provided, the Pay Now / first confirmation body is
    appended as soon as it is read so a later failure (second email, autopay)
    still leaves text for best-effort cost compare in the Allure report.

    ``lease_artifacts_out``: when provided, filled with Pay Now / Updated
    Superlease PDF bytes + text (and Get Access email body) for the
    Compare costs step.

    Two-Step (get_access_baseline = the inbox's newest message time taken
    just before Get Access): the rental sends two Rental Confirmations, one
    per step. The oldest - Pay Now's - gets the checks above and downloads
    its Superlease PDF into artifacts; the one after Get Access downloads
    the updated Superlease. Compare costs attaches both PDFs together.
    Stage sent none in 27 minutes on 2026-09-15, so a missing second email
    is noted in the report rather than failed."""
    two_step = get_access_baseline is not None
    if lease_artifacts_out is not None:
        lease_artifacts_out.clear()
    first_step = (
        "1. Rental Confirmation email (Pay Now)"
        if two_step
        else "Rental Confirmation email"
    )
    with allure.step(first_step):
        # Storefront Pay Now / rental confirmation page (taken during Rent it).
        attach_saved_screenshot(
            confirmation_dir / f"rental-{space_number}.png",
            f"storefront-confirmation-pay-now-{space_number}"
            if two_step
            else f"storefront-confirmation-{space_number}",
        )
        if not two_step:
            message = wait_for_email_where(
                guest["email"],
                "Rental Confirmation",
                matches=lambda message, space=space_number: message_contains(
                    message, space
                ),
                newest=True,
            )
        else:
            # Pay Now email (Get Access prompt) for this space, not an older
            # rental and not the later updated confirmation.
            message = wait_for_email_where(
                guest["email"],
                "Rental Confirmation",
                matches=lambda message, space=space_number: (
                    message_contains(message, space)
                    and TWO_STEP_FIRST_EMAIL_TEXT.lower()
                    in get_email_plain_text(message).lower()
                ),
                newest=True,
            )
        save_email_screenshot(
            context,
            get_email_text(message),
            confirmation_dir / f"rental-email-{space_number}.png",
            allure_name=f"rental-email-{space_number}",
        )
        body = get_email_plain_text(message)
        if body_out is not None:
            body_out.clear()
            body_out.append(body)
        pay_now_label = "Superlease (Pay Now)" if two_step else "Superlease"
        pay_now_pdf, pay_now_url = attach_lease_pdf_from_email(
            context,
            message,
            space_number=space_number,
            document_label=pay_now_label,
            confirmation_dir=confirmation_dir,
        )
        if lease_artifacts_out is not None:
            if pay_now_url:
                lease_artifacts_out["pay_now_pdf_url"] = pay_now_url
            if pay_now_pdf:
                lease_artifacts_out["pay_now_pdf"] = pay_now_pdf
                lease_artifacts_out["pay_now_pdf_text"] = pdf_text_from_bytes(pay_now_pdf)
        expected_total = expected_rental_email_move_in_total(amount_paid, body, charges)
        found_total = parse_move_in_total(body)
        date_pattern = rf"{move_in_date:%b} 0?{move_in_date.day}, {move_in_date.year}"
        expected = {
            "Account Summary": r"Account Summary",
            "guest name": re.escape(f"{guest['first_name']} {guest['last_name']}"),
            # Emails often uppercase the space id (BGne51 vs BGNE51).
            "space number": rf"(?i){re.escape(space_number)}",
            "Move-In Date = today (10633)": rf"Move-In Date:\s*{date_pattern}",
            "Total Cost To Move-In = amount paid": (
                rf"Total Cost To Move-In\s*\$\s*{re.escape(f'{expected_total:,.2f}')}"
            ),
        }
        if security_deposit is not None:
            expected["Security Deposit"] = (
                rf"Security Deposit\s*\$\s*{re.escape(f'{security_deposit:,.2f}')}"
            )
        missing = [
            name for name, pattern in expected.items() if not re.search(pattern, body)
        ]
        if (
            "Total Cost To Move-In = amount paid" in missing
            and found_total is not None
        ):
            missing = [
                (
                    f"Total Cost To Move-In = {expected_total:.2f} "
                    f"(email has {found_total:.2f}, amount_paid={amount_paid:.2f})"
                    if name == "Total Cost To Move-In = amount paid"
                    else name
                )
                for name in missing
            ]
        assert not missing, (
            f"Rental Confirmation email is missing {missing}. Text: {body[:800]}"
        )
        if charges:
            assert_cost_line_items(
                body, charges, total=expected_total, source="Rental Confirmation email"
            )
        first_email_id = message["id"]

    if two_step:
        _check_get_access_rental_email(
            context,
            confirmation_dir,
            guest,
            space_number,
            first_email_id,
            get_access_baseline,
            lease_artifacts_out=lease_artifacts_out,
        )
    if autopay:
        with allure.step("Auto Payment Confirmation email"):
            autopay_message = wait_for_email_where(
                guest["email"],
                "Auto Payment Confirmation",
                matches=lambda message, space=space_number: message_contains(
                    message, space
                ),
                newest=True,
            )
            save_email_screenshot(
                context,
                get_email_text(autopay_message),
                confirmation_dir / f"autopay-email-{space_number}.png",
                allure_name=f"autopay-email-{space_number}",
            )
    return body


def _check_get_access_rental_email(
    context: BrowserContext,
    confirmation_dir: Path,
    guest: dict,
    space_number: str,
    first_email_id: str,
    get_access_baseline: int,
    lease_artifacts_out: dict | None = None,
) -> None:
    """The Two-Step rental's second Rental Confirmation, sent after Get
    Access: newer than the baseline, not Pay Now's email, and without its
    "provide remaining information" prompt. Checked for the guest's name and
    the space when it arrives; otherwise a note goes in the report.
    Attaches the updated Superlease PDF when the download link is present."""
    # config/environments.ini [email] second_rental_email_wait_ms overrides the
    # default, so a diagnostic run can wait much longer without slowing every
    # other run down. wait_for_email_where polls with time.sleep, so the
    # milliseconds from config become seconds here, at that boundary.
    wait_seconds = load_config().getfloat("email", "second_rental_email_wait_ms") / 1000
    with allure.step("2. Rental Confirmation email (Get Access / updated Superlease)"):
        try:
            message = wait_for_email_where(
                guest["email"],
                "Rental Confirmation",
                lambda message, space=space_number: (
                    message["id"] != first_email_id
                    and message_contains(message, space)
                    and TWO_STEP_FIRST_EMAIL_TEXT not in get_email_plain_text(message)
                ),
                after_time=get_access_baseline,
                timeout=wait_seconds,
            )
        except TimeoutError:
            arrived = "\n".join(
                f"{summary.get('time')}  {summary.get('subject')}"
                for summary in list_message_summaries(guest["email"])
            ) or "(inbox listed nothing)"
            allure.attach(
                "No second Rental Confirmation - the one carrying the updated super lease - "
                f"arrived within {wait_seconds:.0f}s of Get Access. Noted, not failed.\n"
                f"Newest message before Get Access (baseline): {get_access_baseline}\n"
                f"Inbox now:\n{arrived}",
                name="second-rental-email-not-received",
                attachment_type=allure.attachment_type.TEXT,
            )
            return
        # Storefront Get Access confirmation page (taken during Rent it).
        attach_saved_screenshot(
            confirmation_dir / f"get-access-{space_number}.png",
            f"storefront-confirmation-get-access-{space_number}",
        )
        save_email_screenshot(
            context,
            get_email_text(message),
            confirmation_dir / f"rental-email-get-access-{space_number}.png",
            allure_name=f"rental-email-get-access-{space_number}",
        )
        body = get_email_plain_text(message)
        updated_pdf, updated_url = attach_lease_pdf_from_email(
            context,
            message,
            space_number=space_number,
            document_label="Updated Superlease (Get Access)",
            confirmation_dir=confirmation_dir,
        )
        if lease_artifacts_out is not None:
            lease_artifacts_out["get_access_email_body"] = body
            if updated_url:
                lease_artifacts_out["updated_superlease_url"] = updated_url
            if updated_pdf:
                lease_artifacts_out["updated_superlease_pdf"] = updated_pdf
                lease_artifacts_out["updated_superlease_pdf_text"] = pdf_text_from_bytes(
                    updated_pdf
                )
        expected = {
            "guest name": re.escape(f"{guest['first_name']} {guest['last_name']}"),
            "space number": rf"(?i){re.escape(space_number)}",
            # This is the email that carries the updated super lease
            # (user, 2026-09-16), so its download link is the point of it.
            "updated super lease download": r"(?i)download\s+super\s*-?\s*lease",
        }
        missing = [
            name for name, pattern in expected.items() if not re.search(pattern, body)
        ]
        assert not missing, (
            f"Second Rental Confirmation (after Get Access) is missing {missing}. "
            f"Text: {body[:800]}"
        )
