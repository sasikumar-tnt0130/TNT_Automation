import re
from configparser import ConfigParser
from datetime import date
from pathlib import Path

from playwright.sync_api import Page, expect

from common_utils.mailinator_utils import (
    find_email_link,
    get_email_plain_text,
    get_email_text,
    latest_email_time,
    wait_for_email,
)
from common_utils.mp_rental_emails import assert_rental_confirmation_emails
from common_utils.wrapper_methods import (
    confirmation_dir_for_current_test,
    log_method_exceptions,
    save_confirmation_screenshot,
    save_email_screenshot,
)
from config.config_reader import EnvironmentConfig, PropertyConfig
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage
from pages.mariposa.mp_two_step_reservation_form_page import MPTwoStepReservationFormPage


REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


class MPTwoStepReservationSetup:
    """Reusable MP storefront Two-Step reservation scenarios - the
    Two-Step counterpart to MPLegacyReservationSetup, built on top of
    MPUnitSearchPage (shared unit/tier selection) and MPTwoStepReservationFormPage
    (the Two-Step-specific consolidated form) instead of
    MPLegacyReservationFormPage. Kept as its own class, not a branch inside
    MPLegacyReservationSetup, so a failure identifies which flow broke
    immediately - see MPTwoStepReservationFormPage's own docstring.

    The storefront property comes from properties.ini two_step_property
    (pass property_config= or rely on environment_config.two_step_property).
    The caller is expected to have already configured that facility for
    Two-Step (see test_two_step_reservation.py, which calls
    LeaseConfigurationSetup.enable_two_step_clickwrap_and_super_lease()
    first) rather than assuming a fixed external state - but the
    storefront has been observed serving Legacy's form anyway
    regardless of that setting, so reserve_unit checks which flow
    actually rendered (MPUnitSearchPage.wait_for_reservation_flow) and
    raises a clear, actionable error immediately if it's Legacy instead
    of silently completing the reservation through the "wrong" flow,
    mirroring MPLegacyReservationSetup.
    """

    @log_method_exceptions
    def __init__(
        self,
        page: Page,
        environment_config: EnvironmentConfig,
        app_config: ConfigParser,
        property_url: str | None = None,
        test_name: str | None = None,
        property_config: PropertyConfig | None = None,
    ) -> None:
        timeout = app_config.getint("browser", "timeout")
        self.environment_config = environment_config
        self.rental_page = MPUnitSearchPage(page, environment_config.mp_base_url, timeout)
        self.two_step_page = MPTwoStepReservationFormPage(
            page, environment_config.mp_base_url, timeout
        )
        # Computed once here, not per-screenshot - see
        # MPLegacyReservationSetup's mirror-image comment.
        # test_name / HB_MP_CURRENT_TEST keep the folder named after the
        # pytest case instead of "unknown".
        self.confirmation_dir = confirmation_dir_for_current_test(
            REPORTS_DIR, test_name=test_name
        )
        # Prefer an explicit two_step_property PropertyConfig - flat
        # environment_config.mp_* fields are the Legacy legacy_property.
        prop = property_config or environment_config.two_step_property
        self.mp_state = prop.mp_state if prop else environment_config.mp_state
        self.mp_city = prop.mp_city if prop else environment_config.mp_city
        # See MPLegacyReservationSetup's mirror-image comment - pass the
        # property_landing_page_url fixture's discovered URL for this
        # suite's own property (Lightning Storage/Rutland, not
        # Legacy's Garden Grove).
        self.property_url = property_url
        # See MPLegacyReservationSetup's space_number.
        self.space_number: str | None = None
        self.move_in_date: date | None = None
        # Set by rent_reserved_unit just before Get Access - see there.
        self.get_access_baseline: int | None = None

    @log_method_exceptions
    def reserve_unit(
        self,
        guest: dict,
        renting_as_business: bool = False,
        days_from_today: int = 1,
    ) -> str:
        """Search, select a unit, and submit the Two-Step reservation
        form ("Reserve Now"). Returns the reservation code. Sets
        self.move_in_date to the date selected on the form."""
        if self.property_url:
            self.rental_page.open_property_page(self.property_url)
        else:
            self.rental_page.open_storefront()
            if self.mp_state and self.mp_city:
                self.rental_page.search_storage_location(
                    state=self.mp_state, city=self.mp_city
                )
            else:
                self.rental_page.select_first_available_location()
        self.rental_page.select_unit()

        business_name = (
            f"{guest['first_name']} {guest['last_name']} Business"
            if renting_as_business
            else None
        )
        flow = self.rental_page.wait_for_reservation_flow()
        if flow != "two_step":
            raise AssertionError(
                "Storefront served the Legacy flow (\"Reserve This "
                "Space\") instead of Two-Step (\"Reserve Now\") for this "
                "session, even though this suite configures the "
                "property for Two-Step - a known intermittent "
                "storefront-side routing issue, not a config problem."
            )
        self.move_in_date = self.two_step_page.reserve_unit(
            email=guest["email"],
            mobile=guest["mobile"],
            first_name=guest["first_name"],
            last_name=guest["last_name"],
            renting_as_business=renting_as_business,
            business_name=business_name,
            days_from_today=days_from_today,
        )
        reservation_code = self.two_step_page.get_reservation_code()
        save_confirmation_screenshot(
            self.two_step_page.page,
            self.confirmation_dir / f"reservation-{reservation_code}.png",
            allure_name=f"reservation-confirmation-{reservation_code}",
        )
        return reservation_code

    @log_method_exceptions
    def assert_confirmation_email(
        self,
        guest: dict,
        reservation_code: str,
        property_name: str | None = None,
        move_in_date: date | None = None,
    ) -> float | None:
        """Same check as MPLegacyReservationSetup.assert_confirmation_email.
        Optionally asserts the move-in date. Returns email Web Rental Rate."""
        message = wait_for_email(guest["email"], subject_contains="Reservation Confirmation")
        body = get_email_text(message)
        plain = get_email_plain_text(message)
        save_email_screenshot(
            self.two_step_page.page.context,
            body,
            self.confirmation_dir / f"email-{reservation_code}.png",
            allure_name=f"confirmation-email-{reservation_code}",
        )
        assert reservation_code in body, (
            f"Reservation code {reservation_code!r} not found in confirmation email body"
        )
        property_name = (
            property_name or self.environment_config.lease_configuration_property_name
        )
        if property_name:
            assert property_name in body, (
                f"Property name {property_name!r} not found in confirmation email body"
            )
        check_date = move_in_date or self.move_in_date
        if check_date:
            # Prefer plain text: HTML parts use &nbsp; between month/day
            # (get_email_plain_text docstring). Also accept MM/DD/YYYY as on
            # the Two-Step thank-you page.
            date_patterns = [
                rf"{check_date:%b}\s+0?{check_date.day},?\s+{check_date.year}",
                rf"{check_date:%B}\s+0?{check_date.day},?\s+{check_date.year}",
                rf"{check_date:%m}/{check_date:%d}/{check_date:%Y}",
                rf"{check_date.month}/{check_date.day}/{check_date.year}",
            ]
            assert any(re.search(pattern, plain, re.I) for pattern in date_patterns), (
                f"Move-in date {check_date:%b %d, %Y} not found in confirmation email body"
            )
        rate = re.search(
            r"Web Rental Rate\s*\$\s*([\d,]+(?:\.\d+)?)", plain
        )
        return float(rate.group(1).replace(",", "")) if rate else None

    @log_method_exceptions
    def assert_confirmation_shows_move_in_date(self, move_in_date: date | None = None) -> None:
        check_date = move_in_date or self.move_in_date
        if not check_date:
            raise AssertionError("No move_in_date to assert on the confirmation page")
        body = self.two_step_page.page.locator("body")
        patterns = [
            rf"{check_date:%b} 0?{check_date.day}, {check_date.year}",
            rf"{check_date:%m}/{check_date:%d}/{check_date:%Y}",
            rf"{check_date.month}/{check_date.day}/{check_date.year}",
        ]
        matched = any(
            re.search(pattern, body.inner_text(), re.I) for pattern in patterns
        )
        assert matched, (
            f"Move-in date {check_date:%b %d, %Y} not found on confirmation page"
        )

    @log_method_exceptions
    def open_rental_from_email(self, guest: dict) -> dict:
        """Old Robot suite's 8900 "Check bill section details", Two-Step
        version: the confirmation email's "Rent Now" link resumes the
        rental (confirmed live 2026-09-13 - it lands on the consolidated
        /rent/<space type>/v1/?reservationId=... form) - returns that
        page's Lease Summary. Nothing is submitted; Pay Now is never
        clicked."""
        message = wait_for_email(guest["email"], subject_contains="Reservation Confirmation")
        self.two_step_page.open_rental_link(find_email_link(message, "Rent Now"))
        return self.two_step_page.read_lease_summary()

    @log_method_exceptions
    def rent_reserved_unit(
        self,
        guest: dict,
        rental_data: dict,
        payment_method: str = "card",
        card: dict | None = None,
    ) -> dict:
        """Old Robot suite's 8872 "Rent Storage w/ enrolling for auto-debit",
        Two-Step version (confirmed live 2026-09-13, uat_storoutlet/Chula
        Vista): resume the reservation from its email's "Rent Now", check
        the bill adds up before paying, pay by card with Autopay Enrollment
        (rental_data["enroll_autopay"]), wait for "You've got your space!",
        then Verify ID Later + mailing address/licence + Get Access.
        Returns the Lease Summary read before paying."""
        lease_summary = self.open_rental_from_email(guest)
        if lease_summary["pay_now"] is None:
            # Confirmed live (2026-09-13, stage/Rutland): the form sometimes
            # ends with "Sign Agreements" (lease signed before payment)
            # instead of Pay Now - not walked yet, so stop before charging.
            raise AssertionError(
                "The rental form shows 'Sign Agreements' instead of 'Pay Now' - "
                "that signing flow isn't supported yet; not paying"
            )
        charges_total = round(sum(lease_summary["charges"].values()), 2)
        assert charges_total == lease_summary["total"] == lease_summary["pay_now"], (
            f"Lease Summary doesn't add up - not paying: charges "
            f"{lease_summary['charges']} = {charges_total}, Total Cost to Move-in "
            f"{lease_summary['total']}, Pay Now {lease_summary['pay_now']}"
        )
        self.space_number = lease_summary["space_number"]
        self.two_step_page.fill_business_representative(guest, rental_data)
        payer_name = f"{guest['first_name']} {guest['last_name']}"
        enroll_autopay = rental_data.get("enroll_autopay", True)
        if payment_method == "ach":
            self.two_step_page.pay_rental_by_ach(
                name_on_account=payer_name,
                routing_number=self.environment_config.ach_routing_number,
                account_number=self.environment_config.ach_account_number,
                billing_address=rental_data,
                enroll_autopay=enroll_autopay,
            )
        else:
            card = card or {}
            self.two_step_page.pay_rental_by_card(
                card_number=card.get("card_number") or self.environment_config.card_number,
                card_expiry=card.get("card_expiry") or self.environment_config.card_expiry,
                card_cvc=card.get("card_cvc") or self.environment_config.card_cvc,
                name_on_card=payer_name,
                zip_code=self.environment_config.card_zip_code,
                enroll_autopay=enroll_autopay,
                billing_address=rental_data,
            )
        space_number = lease_summary["space_number"]
        self.two_step_page.assert_rental_complete(space_number)
        from common_utils.mp_lease_costs import read_confirmation_page_costs

        confirmation_costs = read_confirmation_page_costs(self.two_step_page.page)
        lease_summary = {
            **lease_summary,
            "confirmation_charges": confirmation_costs["charges"],
            "confirmation_total": confirmation_costs["total"],
        }
        save_confirmation_screenshot(
            self.two_step_page.page,
            self.confirmation_dir / f"rental-{space_number}.png",
            allure_name=f"rental-confirmation-{space_number}",
        )
        # The inbox's newest message time just before Get Access, so the
        # rental email check can tell the email Get Access sends from Pay
        # Now's (see mp_rental_emails).
        self.get_access_baseline = latest_email_time(guest["email"])
        self.two_step_page.verify_id_later_and_get_access(rental_data)
        # The second step's confirmation - "Your space is ready!" after Get
        # Access - next to the first step's (rental-<space>.png).
        save_confirmation_screenshot(
            self.two_step_page.page,
            self.confirmation_dir / f"get-access-{space_number}.png",
            allure_name=f"get-access-confirmation-{space_number}",
        )
        return lease_summary

    @log_method_exceptions
    def assert_rental_emails(
        self,
        guest: dict,
        space_number: str,
        move_in_date: date,
        amount_paid: float,
        security_deposit: float | None,
        autopay: bool = True,
        charges: dict[str, float] | None = None,
    ) -> str:
        """Old Robot suite's 10604 ("Validate Tenant email for Rental") and
        10633 (its Move-In Date is the lease date). Confirmed live
        (2026-09-13): the rental sends "<property> Rental Confirmation" -
        the old "You have successfully completed your rental" wording is
        gone - whose Account Summary lists the name, "Unit Space <space>",
        "Move-In Date: Sep 13, 2026", each charge and "Total Cost To
        Move-In $ 112.40"; with autopay, "<property> Auto Payment
        Confirmation" arrives too. Two-Step sends a second Rental
        Confirmation after Get Access - get_access_baseline tells the two
        apart (see mp_rental_emails). Pass ``charges`` from the Lease
        Summary / confirmation page to assert each cost line item.
        Returns the confirmation email plain text."""
        return assert_rental_confirmation_emails(
            self.two_step_page.page.context,
            self.confirmation_dir,
            guest,
            space_number,
            move_in_date,
            amount_paid,
            security_deposit,
            autopay,
            get_access_baseline=self.get_access_baseline,
            charges=charges,
        )
