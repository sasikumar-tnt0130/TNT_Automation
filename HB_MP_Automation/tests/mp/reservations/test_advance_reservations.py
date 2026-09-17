"""TestRail smoke run 2967 - advance (future move-in date) reservations.

Uses properties.ini `advance_reservation_days` (fallback 4) for the offset.
FMS "N days in advance" maps to storefront today..today+(N-1); config stores
that offset. Live walk 2026-09-16 stage: Legacy thank-you does not echo the
move-in date; Two-Step thank-you does (MM/DD/YYYY). Email (Mon D, YYYY) and
HB lead carry the date on both flows.
"""
from datetime import date

import allure
import pytest

from common_utils.browser_sessions import hb_admin_context
from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from config.config_reader import load_property
from pages.common.hb_lead_management_page import HBLeadManagementPage


def _advance_days(configured: int | None) -> int:
    # Offset from today; FMS "5 days in advance" → farthest selectable is +4.
    days = configured if configured and configured > 0 else 4
    return max(days, 1)


@pytest.fixture(scope="module")
def _legacy_flow_configured(browser, environment_config, app_config) -> None:
    with hb_admin_context(browser, environment_config, app_config) as hb_login_page:
        LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        ).disable_two_step_clickwrap_and_super_lease()


@pytest.fixture(scope="module")
def _two_step_flow_configured(
    browser, environment_config, app_config, two_step_property
) -> None:
    with hb_admin_context(browser, environment_config, app_config) as hb_login_page:
        LeaseConfigurationSetup(
            hb_login_page,
            environment_config,
            app_config,
            property_name=two_step_property.lease_configuration_property_name,
            fms_property_name=two_step_property.fms_property_name,
        ).enable_two_step_clickwrap_and_super_lease()


def _assert_hb_lead(
    hb_login_page,
    timeout: float,
    hb_property_name: str,
    guest: dict,
    reservation_code: str,
    move_in_date: date,
    business_name: str | None = None,
) -> None:
    if hb_login_page.open_login_page():
        hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    leads = HBLeadManagementPage(hb_login_page.page, timeout)
    leads.open_leads(hb_property_name)
    leads.assert_web_reservation_lead(
        guest["email"],
        reservation_code,
        move_in_date,
        business_name=business_name,
    )


def _default_hb_property(app_config, environment: str, environment_config) -> str:
    key = app_config.get(environment, "legacy_property", fallback="").strip()
    if key:
        return load_property(app_config, environment, key).hb_property_name
    return (
        environment_config.lease_configuration_property_name
        or ""
    )


@allure.feature("MP Reservation")
@allure.story("Advance reservation (future move-in date)")
@pytest.mark.usefixtures("_legacy_flow_configured")
class TestLegacyAdvanceReservation:
    @allure.title("Legacy Flow-Advance reservation with a future move-in date")
    @pytest.mark.smoke
    @pytest.mark.testrail("C10481")
    def test_legacy_advance_reservation_future_date(
        self,
        page,
        environment,
        environment_config,
        app_config,
        mp_guest,
        hb_login_page,
    ) -> None:
        if not (environment_config.mp_city and environment_config.mp_state):
            pytest.skip("No storefront property configured for this environment")
        days = _advance_days(environment_config.advance_reservation_days)
        reservation = MPLegacyReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(
            mp_guest, renting_as_business=False, days_from_today=days
        )
        assert reservation.move_in_date, "Expected a move-in date from the reservation"
        with allure.step("Confirmation email carries the future move-in date"):
            reservation.assert_confirmation_email(mp_guest, reservation_code)
        with allure.step("HB lead shows the future reservation / move-in date"):
            _assert_hb_lead(
                hb_login_page,
                app_config.getint("browser", "timeout"),
                _default_hb_property(app_config, environment, environment_config),
                mp_guest,
                reservation_code,
                reservation.move_in_date,
            )

    @allure.title("Legacy Flow-Reserve as Business with a future move-in date")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683634")
    def test_legacy_rab_reservation_future_date(
        self,
        page,
        environment,
        environment_config,
        app_config,
        mp_guest,
        hb_login_page,
    ) -> None:
        if not (environment_config.mp_city and environment_config.mp_state):
            pytest.skip("No storefront property configured for this environment")
        days = _advance_days(environment_config.advance_reservation_days)
        business_name = f"{mp_guest['first_name']} {mp_guest['last_name']} Business"
        reservation = MPLegacyReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(
            mp_guest, renting_as_business=True, days_from_today=days
        )
        assert reservation.move_in_date
        reservation.assert_confirmation_email(mp_guest, reservation_code)
        _assert_hb_lead(
            hb_login_page,
            app_config.getint("browser", "timeout"),
            _default_hb_property(app_config, environment, environment_config),
            mp_guest,
            reservation_code,
            reservation.move_in_date,
            business_name=business_name,
        )

    @allure.title("Reserve as Business-Reservation with a future date")
    @pytest.mark.smoke
    @pytest.mark.testrail("C30858")
    def test_rab_reservation_future_date_details_in_hb(
        self,
        page,
        environment,
        environment_config,
        app_config,
        mp_guest,
        hb_login_page,
    ) -> None:
        """HB-focused check: business name and move-in date on the lead."""
        if not (environment_config.mp_city and environment_config.mp_state):
            pytest.skip("No storefront property configured for this environment")
        days = _advance_days(environment_config.advance_reservation_days)
        business_name = f"{mp_guest['first_name']} {mp_guest['last_name']} Business"
        reservation = MPLegacyReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(
            mp_guest, renting_as_business=True, days_from_today=days
        )
        assert reservation.move_in_date
        _assert_hb_lead(
            hb_login_page,
            app_config.getint("browser", "timeout"),
            _default_hb_property(app_config, environment, environment_config),
            mp_guest,
            reservation_code,
            reservation.move_in_date,
            business_name=business_name,
        )


@allure.feature("MP Reservation")
@allure.story("Advance reservation (future move-in date) - Two-Step")
@pytest.mark.usefixtures("_two_step_flow_configured")
class TestTwoStepAdvanceReservation:
    @allure.title("2Step Flow-Advance reservation with a future move-in date")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683631")
    def test_two_step_advance_reservation_future_date(
        self,
        page,
        environment_config,
        app_config,
        mp_guest,
        two_step_property,
        property_landing_page_url,
        hb_login_page,
    ) -> None:
        two_step = two_step_property
        property_url = property_landing_page_url(
            environment_config.mp_base_url, two_step.mp_state, two_step.mp_city
        )
        days = _advance_days(two_step.advance_reservation_days)
        reservation = MPTwoStepReservationSetup(
            page,
            environment_config,
            app_config,
            property_url=property_url,
            property_config=two_step,
        )
        reservation_code = reservation.reserve_unit(
            mp_guest, renting_as_business=False, days_from_today=days
        )
        assert reservation.move_in_date
        # Live 2026-09-16 stage/Rutland: thank-you shows MM/DD/YYYY (Legacy does not).
        reservation.assert_confirmation_shows_move_in_date()
        reservation.assert_confirmation_email(
            mp_guest,
            reservation_code,
            property_name=two_step.lease_configuration_property_name,
        )
        _assert_hb_lead(
            hb_login_page,
            app_config.getint("browser", "timeout"),
            two_step.hb_property_name,
            mp_guest,
            reservation_code,
            reservation.move_in_date,
        )

    @allure.title("2Step Flow-Reserve as Business with a future move-in date")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683636")
    def test_two_step_rab_reservation_future_date(
        self,
        page,
        environment_config,
        app_config,
        mp_guest,
        two_step_property,
        property_landing_page_url,
        hb_login_page,
    ) -> None:
        two_step = two_step_property
        property_url = property_landing_page_url(
            environment_config.mp_base_url, two_step.mp_state, two_step.mp_city
        )
        days = _advance_days(two_step.advance_reservation_days)
        business_name = f"{mp_guest['first_name']} {mp_guest['last_name']} Business"
        reservation = MPTwoStepReservationSetup(
            page,
            environment_config,
            app_config,
            property_url=property_url,
            property_config=two_step,
        )
        reservation_code = reservation.reserve_unit(
            mp_guest, renting_as_business=True, days_from_today=days
        )
        assert reservation.move_in_date
        reservation.assert_confirmation_shows_move_in_date()
        reservation.assert_confirmation_email(
            mp_guest,
            reservation_code,
            property_name=two_step.lease_configuration_property_name,
        )
        _assert_hb_lead(
            hb_login_page,
            app_config.getint("browser", "timeout"),
            two_step.hb_property_name,
            mp_guest,
            reservation_code,
            reservation.move_in_date,
            business_name=business_name,
        )
