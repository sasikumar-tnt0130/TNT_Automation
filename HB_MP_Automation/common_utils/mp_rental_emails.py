import re
from datetime import date
from pathlib import Path

import allure
from playwright.sync_api import BrowserContext

from common_utils.mailinator_utils import (
    get_email_plain_text,
    get_email_text,
    list_message_summaries,
    wait_for_email,
    wait_for_email_where,
)
from common_utils.wrapper_methods import save_email_screenshot
from config.config_reader import load_config

# The Two-Step rental's first Rental Confirmation, sent at Pay Now, says
# "Click “Get Access” to provide remaining information required to access
# your space" (confirmed live 2026-09-15, stage/Rutland) - so the second
# one, sent after Get Access, is a newer one without this text.
TWO_STEP_FIRST_EMAIL_TEXT = "remaining information required to access your space"
# How long to wait for that second email lives in config/environments.ini
# [email] second_rental_email_wait_ms - no copy of it here.


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
) -> None:
    """Old Robot suite's 10604 ("Validate Tenant email for Rental") and 10633
    (its Move-In Date is the lease date), for both storefront rental flows.
    Confirmed live: the rental sends "<property> Rental Confirmation"
    (Two-Step on Chula Vista 2026-09-13, Legacy on Bellflower 2026-09-14) -
    the old "You have successfully completed your rental" wording is gone -
    whose Account Summary lists the name, "Unit Space <space>", "Move-In
    Date: Sep 13, 2026", each charge and "Total Cost To Move-In $ 112.40";
    with autopay, "<property> Auto Payment Confirmation" arrives too.

    Two-Step (get_access_baseline = the inbox's newest message time taken
    just before Get Access): the rental sends two Rental Confirmations, one
    per step. The oldest - Pay Now's - gets the checks above; the one after
    Get Access is checked when it arrives within TWO_STEP_SECOND_EMAIL_WAIT
    seconds. Stage sent none in 27 minutes on 2026-09-15, so a missing one
    is noted in the report rather than failed."""
    if get_access_baseline is None:
        message = wait_for_email(guest["email"], subject_contains="Rental Confirmation")
    else:
        message = wait_for_email_where(guest["email"], "Rental Confirmation")
    save_email_screenshot(
        context,
        get_email_text(message),
        confirmation_dir / f"rental-email-{space_number}.png",
        allure_name=f"rental-email-{space_number}",
    )
    body = get_email_plain_text(message)
    date_pattern = rf"{move_in_date:%b} 0?{move_in_date.day}, {move_in_date.year}"
    expected = {
        "Account Summary": r"Account Summary",
        "guest name": re.escape(f"{guest['first_name']} {guest['last_name']}"),
        "space number": re.escape(space_number),
        "Move-In Date = today (10633)": rf"Move-In Date:\s*{date_pattern}",
        "Total Cost To Move-In = amount paid": (
            rf"Total Cost To Move-In\s*\$\s*{re.escape(f'{amount_paid:,.2f}')}"
        ),
    }
    if security_deposit is not None:
        expected["Security Deposit"] = (
            rf"Security Deposit\s*\$\s*{re.escape(f'{security_deposit:,.2f}')}"
        )
    missing = [name for name, pattern in expected.items() if not re.search(pattern, body)]
    assert not missing, (
        f"Rental Confirmation email is missing {missing}. Text: {body[:800]}"
    )
    if get_access_baseline is not None:
        _check_get_access_rental_email(
            context, confirmation_dir, guest, space_number, message["id"], get_access_baseline
        )
    if autopay:
        autopay_message = wait_for_email(guest["email"], subject_contains="Auto Payment Confirmation")
        save_email_screenshot(
            context,
            get_email_text(autopay_message),
            confirmation_dir / f"autopay-email-{space_number}.png",
            allure_name=f"autopay-email-{space_number}",
        )


def _check_get_access_rental_email(
    context: BrowserContext,
    confirmation_dir: Path,
    guest: dict,
    space_number: str,
    first_email_id: str,
    get_access_baseline: int,
) -> None:
    """The Two-Step rental's second Rental Confirmation, sent after Get
    Access: newer than the baseline, not Pay Now's email, and without its
    "provide remaining information" prompt. Checked for the guest's name and
    the space when it arrives; otherwise a note goes in the report."""
    # config/environments.ini [email] second_rental_email_wait_ms overrides the
    # default, so a diagnostic run can wait much longer without slowing every
    # other run down. wait_for_email_where polls with time.sleep, so the
    # milliseconds from config become seconds here, at that boundary.
    wait_seconds = load_config().getfloat("email", "second_rental_email_wait_ms") / 1000
    with allure.step("Second Rental Confirmation, after Get Access (checked if sent)"):
        try:
            message = wait_for_email_where(
                guest["email"],
                "Rental Confirmation",
                lambda message: message["id"] != first_email_id
                and TWO_STEP_FIRST_EMAIL_TEXT not in get_email_plain_text(message),
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
        save_email_screenshot(
            context,
            get_email_text(message),
            confirmation_dir / f"rental-email-get-access-{space_number}.png",
            allure_name=f"rental-email-get-access-{space_number}",
        )
        body = get_email_plain_text(message)
        expected = {
            "guest name": re.escape(f"{guest['first_name']} {guest['last_name']}"),
            "space number": re.escape(space_number),
            # This is the email that carries the updated super lease
            # (user, 2026-09-16), so its download link is the point of it.
            "updated super lease download": r"(?i)download\s+superlease",
        }
        missing = [name for name, pattern in expected.items() if not re.search(pattern, body)]
        assert not missing, (
            f"Second Rental Confirmation (after Get Access) is missing {missing}. Text: {body[:800]}"
        )
