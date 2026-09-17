import allure
import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from pages.common.hb_login_page import HBLoginPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


@pytest.fixture(scope="class")
def _legacy_flow_configured(browser, environment_config, app_config) -> None:
    """One-time admin-side setup for every test in this class: disables
    Two-Step Rental/Clickwrap/Super Lease and applies the configured
    Landing Page Layout. These are server-side HB settings, not
    per-browser-session state, so doing this once per class - on its
    own class-scoped login/context, separate from the function-scoped
    `page`/`hb_login_page` fixtures the reservation flow itself uses -
    is equivalent to, and much faster than, every test repeating it."""
    timeout = app_config.getint("browser", "timeout")
    permissions = [
        p.strip()
        for p in app_config.get("browser", "permissions", fallback="").split(",")
        if p.strip()
    ]
    context = browser.new_context(permissions=permissions, no_viewport=True)
    setup_page = context.new_page()
    setup_page.set_default_timeout(timeout)
    # Own context for the storefront self-heal check (disable_two_step_
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

        lease_configuration = LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        )
        lease_configuration.disable_two_step_clickwrap_and_super_lease(
            rental_page=rental_page
        )
        if environment_config.landing_page_layout:
            lease_configuration.set_landing_page_layout(
                environment_config.landing_page_layout
            )
    finally:
        storefront_context.close()
        context.close()



@allure.feature("MP Reservation")
@allure.story("Legacy Flow: Reservation")
@pytest.mark.usefixtures("_legacy_flow_configured")
class TestLegacyReservation:
    # This suite exercises the Legacy Flow specifically, which requires
    # Two-Step Rental disabled on the property (the storefront reaches a
    # tier-selection dialog and completes a single "Reserve This Space"
    # form directly - Two-Step's own unit-listing/reservation UI is a
    # different flow entirely, not just a config variant of this one).
    # Reservation form/confirmation content itself doesn't depend on
    # Clickwrap/Super Lease (confirmed live 2026-09-07) - only converting
    # a reservation to a rental is affected by those - but they're
    # disabled here too since "Legacy Flow" means neither is active.

    @allure.title("Individual reservation can be completed - Desktop")
    def test_individual_reservation_desktop(
        self, page, environment_config, app_config, mp_guest
    ) -> None:
        reservation = MPLegacyReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Individual reservation can be completed - Mobile")
    def test_individual_reservation_mobile(
        self, mobile_page, environment_config, app_config, mp_guest, mp_property_url
    ) -> None:
        reservation = MPLegacyReservationSetup(
            mobile_page, environment_config, app_config, property_url=mp_property_url
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Reserve As Business reservation can be completed - Desktop")
    def test_rab_reservation_desktop(
        self, page, environment_config, app_config, mp_guest
    ) -> None:
        reservation = MPLegacyReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"

    @allure.title("Reserve As Business reservation can be completed - Mobile")
    def test_rab_reservation_mobile(
        self, mobile_page, environment_config, app_config, mp_guest, mp_property_url
    ) -> None:
        reservation = MPLegacyReservationSetup(
            mobile_page, environment_config, app_config, property_url=mp_property_url
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"
