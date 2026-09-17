import allure
import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from pages.common.hb_login_page import HBLoginPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


@pytest.fixture(scope="class")
def _two_step_flow_configured(browser, environment_config, app_config) -> None:
    """One-time admin-side setup for every test in this class - see
    test_legacy_reservation.py's fixture of the same shape for the full
    rationale (server-side HB setting, own class-scoped login/context
    instead of every test repeating it)."""
    timeout = app_config.getint("browser", "timeout")
    permissions = [
        p.strip()
        for p in app_config.get("browser", "permissions", fallback="").split(",")
        if p.strip()
    ]
    context = browser.new_context(permissions=permissions, no_viewport=True)
    setup_page = context.new_page()
    setup_page.set_default_timeout(timeout)
    # Own context for the storefront self-heal check (enable_two_step_
    # clickwrap_and_super_lease's rental_page arg) - kept separate from
    # the admin context above, which stays on HB admin throughout.
    storefront_context = browser.new_context(permissions=permissions, no_viewport=True)
    try:
        hb_login_page = HBLoginPage(setup_page, environment_config, timeout)
        if hb_login_page.open_login_page():
            hb_login_page.submit_login_credentials()
        hb_login_page.assert_login_successful()

        storefront_page = storefront_context.new_page()
        storefront_page.set_default_timeout(timeout)
        rental_page = MPUnitSearchPage(
            storefront_page, environment_config.mp_base_url, timeout
        )

        LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        ).enable_two_step_clickwrap_and_super_lease(rental_page=rental_page)
    finally:
        storefront_context.close()
        context.close()


@allure.feature("MP Reservation")
@allure.story("Two-Step Flow: Reservation")
@pytest.mark.usefixtures("_two_step_flow_configured")
class TestTwoStepReservation:
    # Confirmed live (2026-09-08, stage): environment_config's own
    # default property (Hamilton Self Storage/Garden Grove) is a
    # Mariposa-only property that can never enable Two-Step Rental - a
    # hard, permanent site-side restriction (attempting it there leaves
    # the switch snapping back to unchecked no matter how long you
    # wait), not a config toggle. This suite runs against Rutland/
    # Lightning Storage instead (the staging environment's own banner
    # documents this property as "2 Step Configured") - its identity is
    # resolved per-test below via property_landing_page_url rather than
    # environment_config's own default property.

    @allure.title("Individual reservation can be completed - Desktop")
    def test_individual_reservation_desktop(
        self, page, environment_config, app_config, mp_guest
    ) -> None:
        reservation = MPTwoStepReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Individual reservation can be completed - Mobile")
    def test_individual_reservation_mobile(
        self,
        mobile_page,
        environment_config,
        app_config,
        mp_guest,
        property_landing_page_url,
    ) -> None:
        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            environment_config.mp_state,
            environment_config.mp_city,
        )
        reservation = MPTwoStepReservationSetup(
            mobile_page, environment_config, app_config, property_url=property_url
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Reserve As Business reservation can be completed - Desktop")
    def test_rab_reservation_desktop(
        self, page, environment_config, app_config, mp_guest
    ) -> None:
        reservation = MPTwoStepReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Reserve As Business reservation can be completed - Mobile")
    def test_rab_reservation_mobile(
        self,
        mobile_page,
        environment_config,
        app_config,
        mp_guest,
        property_landing_page_url,
    ) -> None:
        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            environment_config.mp_state,
            environment_config.mp_city,
        )
        reservation = MPTwoStepReservationSetup(
            mobile_page, environment_config, app_config, property_url=property_url
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"
    #     reservation.assert_confirmation_email(mp_guest, reservation_code)
