import allure
import pytest

from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from tests.mp.reservations._helpers import ensure_legacy_reservation_flow


@pytest.fixture(scope="module", autouse=True)
def precondition(hb_admin_session, environment_config, app_config) -> None:
    """Once for this file: APW + Legacy traditional + landing layout + Clear Cache."""
    # ensure_legacy_reservation_flow(
    #     hb_admin_session, environment_config, app_config
    # )
    pass

@allure.feature("MP Reservation")
@allure.story("Legacy Flow: Reservation")
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
    # Precondition matches rentals ensure_legacy_traditional (+ landing layout).

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
