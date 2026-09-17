import re
from configparser import ConfigParser
from datetime import date
from pathlib import Path

from playwright.sync_api import Page

from common_utils.mailinator_utils import get_email_text, wait_for_email
from common_utils.mp_rental_emails import assert_rental_confirmation_emails
from common_utils.test_identities import new_additional_contact
from common_utils.wrapper_methods import (
    confirmation_dir_for_current_test,
    log_method_exceptions,
    save_confirmation_screenshot,
    save_email_screenshot,
)
from config.config_reader import EnvironmentConfig
from pages.mariposa.mp_legacy_reservation_form_page import MPLegacyReservationFormPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


class MPLegacyReservationSetup:
    """Reusable MP storefront reservation/rental scenarios, built on top of
    the Rental and Legacy Rental page objects. The property to search for
    comes from config/environments.ini (per environment, see
    LeaseConfigurationSetup); payment scenario data for converting a
    reservation to a rental comes from the same EnvironmentConfig, merged
    in from environments.ini's own global `[payment]` section.

    This suite's properties are configured for the Legacy flow (see
    LeaseConfigurationSetup.disable_two_step_clickwrap_and_super_lease,
    used by every caller). reserve_unit checks which flow actually
    rendered (MPUnitSearchPage.wait_for_reservation_flow) and raises a
    clear, actionable error immediately if it's Two-Step instead - a
    known intermittent storefront-side routing issue, not something to
    silently paper over by completing the reservation through the
    "wrong" flow.

    Takes whichever `page` the caller wants driven (the shared desktop
    `page` fixture, or the phone-viewport `mobile_page` fixture) - lease
    configuration itself is set up separately, on HB's own page, via
    LeaseConfigurationSetup.
    """

    @log_method_exceptions
    def __init__(
        self,
        page: Page,
        environment_config: EnvironmentConfig,
        app_config: ConfigParser,
        property_url: str | None = None,
    ) -> None:
        timeout = app_config.getint("browser", "timeout")
        self.environment_config = environment_config
        self.rental_page = MPUnitSearchPage(page, environment_config.mp_base_url, timeout)
        self.legacy_page = MPLegacyReservationFormPage(page, environment_config.mp_base_url, timeout)
        # Computed once here, not per-screenshot - reserve_unit and
        # assert_confirmation_email save into the same folder, so a
        # reservation's confirmation + email screenshots land together
        # (see confirmation_dir_for_current_test's own docstring).
        self.confirmation_dir = confirmation_dir_for_current_test(REPORTS_DIR)

        # No property configured for this environment (dev/uat, per
        # environments.ini) falls back to dynamic discovery
        # (select_first_available_location) instead of guessing one.
        self.mp_state = environment_config.mp_state
        self.mp_city = environment_config.mp_city
        # Pass the property_landing_page_url fixture's value here (see
        # its own docstring) to skip straight to the property via
        # MPUnitSearchPage.open_property_page instead of the state/city
        # click-through search - mainly for mobile callers, where that
        # click-through has been observed unreliable.
        self.property_url = property_url
        # The space being rented, as soon as the rental form names it - so a
        # caller can still move it out when a later step fails.
        self.space_number: str | None = None

    @log_method_exceptions
    def reserve_unit(self, guest: dict, renting_as_business: bool = False) -> str:
        """Search, select a unit, and submit the Legacy reservation form.
        Returns the reservation code shown on confirmation."""
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
        if flow != "legacy":
            raise AssertionError(
                "Storefront served the Two-Step Rental flow "
                "(\"Reserve Now\") instead of Legacy (\"Reserve This "
                "Space\") for this session, even though this suite "
                "configures the property for Legacy - a known "
                "intermittent storefront-side routing issue, not a "
                "config problem."
            )
        self.legacy_page.reserve_unit(
            email=guest["email"],
            mobile=guest["mobile"],
            first_name=guest["first_name"],
            last_name=guest["last_name"],
            renting_as_business=renting_as_business,
            business_name=business_name,
        )
        reservation_code = self.legacy_page.get_reservation_code()
        save_confirmation_screenshot(
            self.legacy_page.page,
            self.confirmation_dir / f"reservation-{reservation_code}.png",
            allure_name=f"reservation-confirmation-{reservation_code}",
        )
        return reservation_code

    @log_method_exceptions
    def assert_confirmation_email(self, guest: dict, reservation_code: str) -> None:
        """Confirms the reservation confirmation email actually arrived
        on the guest's Mailinator inbox (not just that the storefront
        claimed success), and that its content matches this reservation
        - the reservation code, and the property name when this
        environment's config has one set."""
        message = wait_for_email(guest["email"], subject_contains="Reservation Confirmation")
        body = get_email_text(message)
        save_email_screenshot(
            self.legacy_page.page.context,
            body,
            self.confirmation_dir / f"email-{reservation_code}.png",
            allure_name=f"confirmation-email-{reservation_code}",
        )
        assert reservation_code in body, (
            f"Reservation code {reservation_code!r} not found in confirmation email body"
        )
        property_name = self.environment_config.lease_configuration_property_name
        if property_name:
            assert property_name in body, (
                f"Property name {property_name!r} not found in confirmation email body"
            )

    @log_method_exceptions
    def convert_reservation_to_rental(
        self, guest: dict, rental_data: dict, payment_method: str = "card", autopay: bool = False
    ) -> dict:
        """Resume a just-created reservation ("Rent online now"), fill the
        rental application, pay by card or ACH - with or without autopay -
        and finish it: "Sign Agreements" and signing every document
        (Traditional signing), or the agreement box and "Pay Now" - which of
        the two is decided by the property's lease configuration. Walked live
        2026-09-14 on uat_storoutlet/Bellflower (Traditional, ACH + autopay).
        Returns the Lease Summary read before submitting, the space the
        confirmation names and which ending the form had."""
        self.legacy_page.rent_online_now()
        self.legacy_page.ensure_payment_method(payment_method)
        alternate = new_additional_contact()
        # The storefront rejects digits in names ("Name contains invalid
        # characters", 2026-09-14) - the helper's "Alt3f9a1c" becomes letters.
        alternate["last_name"] = re.sub(
            r"\d", lambda digit: "abcdefghij"[int(digit.group())], alternate["last_name"]
        )
        self.legacy_page.fill_rental_application(rental_data, alternate, guest)
        payer = {
            "name": f"{guest['first_name']} {guest['last_name']}",
            "card_number": self.environment_config.card_number,
            "card_expiry": self.environment_config.card_expiry,
            "card_cvc": self.environment_config.card_cvc,
            "routing_number": self.environment_config.ach_routing_number,
            "account_number": self.environment_config.ach_account_number,
        }
        self.legacy_page.pay_with(payment_method, autopay, payer, rental_data)
        totals = self.legacy_page.read_lease_totals()
        self.space_number = totals["space_number"]
        ending = self.legacy_page.submit_rental()
        space_number = self.legacy_page.assert_rental_complete()
        if totals["space_number"] and totals["space_number"] != space_number:
            raise AssertionError(
                f"The Lease Summary named space {totals['space_number']}, "
                f"the confirmation space {space_number}"
            )
        self.space_number = space_number
        save_confirmation_screenshot(
            self.legacy_page.page,
            self.confirmation_dir / f"rental-{space_number}.png",
            allure_name=f"rental-confirmation-{space_number}",
        )
        return {**totals, "space_number": space_number, "ending": ending}

    @log_method_exceptions
    def assert_rental_emails(
        self,
        guest: dict,
        space_number: str,
        move_in_date: date,
        amount_paid: float,
        security_deposit: float | None,
        autopay: bool = True,
    ) -> None:
        """The same Rental Confirmation / Auto Payment Confirmation checks as
        the Two-Step flow (mp_rental_emails)."""
        assert_rental_confirmation_emails(
            self.legacy_page.page.context,
            self.confirmation_dir,
            guest,
            space_number,
            move_in_date,
            amount_paid,
            security_deposit,
            autopay,
        )
