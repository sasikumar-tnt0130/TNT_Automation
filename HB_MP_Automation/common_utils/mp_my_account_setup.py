import re
from configparser import ConfigParser

from playwright.sync_api import Page

from common_utils.mailinator_utils import (
    get_email_plain_text,
    latest_email_time,
    wait_for_email,
    wait_for_email_after,
)
from common_utils.wrapper_methods import log_method_exceptions
from config.config_reader import EnvironmentConfig
from pages.mariposa.mp_my_account_page import MPMyAccountPage


class MPMyAccountSetup:
    """Storefront My Account scenarios for a tenant rented on the storefront
    (see MPTwoStepReservationSetup.rent_reserved_unit) - the old Robot
    suite's 8860/8861/8862/10605, ported against what's live (2026-09-13,
    uat_storoutlet/Chula Vista): the Robot suite logged in to one fixed,
    pre-made account; here each run's tenant creates its own online account
    with the code emailed to its Mailinator inbox. Card data comes from
    secrets.ini's [payment] section, as for the rental; billing_address
    is the address the tenant gave at rental (config/test_data/mp_rental.json
    - address1/address2/zip/state_code/city)."""

    @log_method_exceptions
    def __init__(
        self,
        page: Page,
        environment_config: EnvironmentConfig,
        app_config: ConfigParser,
        billing_address: dict,
    ) -> None:
        self.environment_config = environment_config
        self.billing_address = billing_address
        self.account_page = MPMyAccountPage(
            page, environment_config.mp_base_url, app_config.getint("browser", "timeout")
        )

    def _card(self, guest: dict) -> dict:
        return {
            "card_number": self.environment_config.card_number,
            "card_expiry": self.environment_config.card_expiry,
            "card_cvc": self.environment_config.card_cvc,
            "name_on_card": f"{guest['first_name']} {guest['last_name']}",
            "billing_address": self.billing_address,
        }

    @log_method_exceptions
    def create_account_and_log_in(self, guest: dict, password: str, state: str, city: str) -> None:
        """Confirmed live: the code arrives within seconds as "<company> OTP
        Notification" - "Your login code is 255212."."""
        self.account_page.open_login(state, city)
        self.account_page.create_account(guest["email"], password)
        message = wait_for_email(guest["email"], subject_contains="OTP Notification")
        code = re.search(r"login code is (\d{4,8})", get_email_plain_text(message))
        assert code, "No login code found in the OTP Notification email"
        self.account_page.verify_email_code(code.group(1))

    @log_method_exceptions
    def pay_bill(self, guest: dict, months: int = 1) -> dict:
        return self.account_page.pay_bill(months=months, **self._card(guest))

    @log_method_exceptions
    def enroll_autopay(self, guest: dict) -> dict:
        return self.account_page.enroll_autopay(**self._card(guest))

    @log_method_exceptions
    def assert_payment_email(self, guest: dict, space_number: str, amount_paid: float) -> None:
        """Confirmed live: a My Account payment sends "<property> Online
        Payment Confirmation" (twice, a couple of seconds apart) - "Thank
        you for your Payment", a Payment Summary with "Unit Space <space>",
        each charge and "Total Payment Amount $ 170.00"."""
        body = get_email_plain_text(
            wait_for_email(guest["email"], subject_contains="Online Payment Confirmation")
        )
        expected = {
            "Thank you for your Payment": r"Thank you for your Payment",
            "space number": re.escape(space_number),
            "Total Payment Amount = amount paid": (
                rf"Total Payment Amount\s*\$\s*{re.escape(f'{amount_paid:,.2f}')}"
            ),
        }
        missing = [name for name, pattern in expected.items() if not re.search(pattern, body)]
        assert not missing, f"Online Payment Confirmation email is missing {missing}. Text: {body[:600]}"

    @log_method_exceptions
    def email_baseline(self, guest: dict) -> int:
        """Newest message time in the guest's inbox - take it just before
        re-enrolling and pass it to assert_autopay_enrollment_email, so
        only an "Auto Payment Confirmation" arriving afterwards counts (the
        rental itself already sent one)."""
        return latest_email_time(guest["email"])

    @log_method_exceptions
    def assert_autopay_enrollment_email(self, guest: dict, after_time: int) -> None:
        """Old Robot suite's 10605 ("Autopay Emails are received ... while
        enrolling Autopay from the My Account section"): its phrases are
        still in the live email - "You are successfully enrolled in our
        auto-payment program." and "Auto-Payment Confirmation"."""
        body = get_email_plain_text(
            wait_for_email_after(guest["email"], "Auto Payment Confirmation", after_time)
        )
        expected = {
            "enrolled phrase": re.escape("You are successfully enrolled in our auto-payment program."),
            "Auto-Payment Confirmation": re.escape("Auto-Payment Confirmation"),
            "guest name": re.escape(f"{guest['first_name']} {guest['last_name']}"),
        }
        missing = [name for name, pattern in expected.items() if not re.search(pattern, body)]
        assert not missing, f"Auto Payment Confirmation email is missing {missing}. Text: {body[:600]}"
