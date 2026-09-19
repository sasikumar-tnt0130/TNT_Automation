import allure
import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup


@pytest.fixture(scope="class")
def _legacy_flow_configured(hb_admin_session, environment_config, app_config) -> None:
    """One-time admin setup for this class on the module HB admin session."""
    lease_configuration = LeaseConfigurationSetup(
        hb_admin_session, environment_config, app_config
    )
    lease_configuration.disable_two_step_clickwrap_and_super_lease()
    if environment_config.landing_page_layout:
        lease_configuration.set_landing_page_layout(
            environment_config.landing_page_layout
        )
    lease_configuration.flush_website_cache()


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
    @pytest.mark.smoke
    @pytest.mark.testrail("C10474")
    def test_individual_reservation_desktop(
        self, page, environment_config, app_config, mp_guest
    ) -> None:
        reservation = MPLegacyReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Individual reservation can be completed - Mobile")
    @pytest.mark.smoke
    @pytest.mark.testrail("C10474")
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
    @pytest.mark.smoke
    @pytest.mark.testrail("C683633")
    @pytest.mark.testrail("C30837")
    def test_rab_reservation_desktop(
        self, page, environment_config, app_config, mp_guest
    ) -> None:
        reservation = MPLegacyReservationSetup(page, environment_config, app_config)
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"

    @allure.title("Reserve As Business reservation can be completed - Mobile")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683633")
    @pytest.mark.testrail("C30837")
    def test_rab_reservation_mobile(
        self, mobile_page, environment_config, app_config, mp_guest, mp_property_url
    ) -> None:
        reservation = MPLegacyReservationSetup(
            mobile_page, environment_config, app_config, property_url=mp_property_url
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"
