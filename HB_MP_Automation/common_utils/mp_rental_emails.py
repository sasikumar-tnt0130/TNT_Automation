import re
from datetime import date
from pathlib import Path

from playwright.sync_api import BrowserContext

from common_utils.mailinator_utils import get_email_plain_text, get_email_text, wait_for_email
from common_utils.wrapper_methods import save_email_screenshot


def assert_rental_confirmation_emails(
    context: BrowserContext,
    confirmation_dir: Path,
    guest: dict,
    space_number: str,
    move_in_date: date,
    amount_paid: float,
    security_deposit: float | None,
    autopay: bool = True,
) -> None:
    """Old Robot suite's 10604 ("Validate Tenant email for Rental") and 10633
    (its Move-In Date is the lease date), for both storefront rental flows.
    Confirmed live: the rental sends "<property> Rental Confirmation"
    (Two-Step on Chula Vista 2026-09-13, Legacy on Bellflower 2026-09-14) -
    the old "You have successfully completed your rental" wording is gone -
    whose Account Summary lists the name, "Unit Space <space>", "Move-In
    Date: Sep 13, 2026", each charge and "Total Cost To Move-In $ 112.40";
    with autopay, "<property> Auto Payment Confirmation" arrives too."""
    message = wait_for_email(guest["email"], subject_contains="Rental Confirmation")
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
    if autopay:
        wait_for_email(guest["email"], subject_contains="Auto Payment Confirmation")
