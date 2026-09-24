import allure
import pytest

from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from tests.mp.reservations._helpers import ensure_two_step_superlease


@pytest.fixture(scope="module", autouse=True)
def precondition(
    hb_admin_session, environment_config, app_config, two_step_property
) -> None:
    """Once for this file: APW + Two-Step/Clickwrap/Super Lease + days + Clear Cache."""
    ensure_two_step_superlease(
        hb_admin_session, environment_config, app_config, two_step_property
    )


@allure.feature("MP Reservation")
@allure.story("Two-Step Flow: Reservation")
class TestTwoStepReservation:
    # Confirmed live (2026-09-08, stage): environment_config's own
    # default property (Hamilton Self Storage/Garden Grove) is a
    # Mariposa-only property that can never enable Two-Step Rental - a
    # hard, permanent site-side restriction (attempting it there leaves
    # the switch snapping back to unchecked no matter how long you
    # wait), not a config toggle. This suite runs against
    # properties.ini two_step_property (e.g. Rutland/Lightning Storage)
    # via the two_step_property fixture.
    # Precondition matches rentals ensure_two_step_superlease.

    @allure.title("Individual reservation can be completed - Desktop")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683626")
    def test_individual_reservation_desktop(
        self, page, environment_config, app_config, mp_guest, two_step_property
    ) -> None:
        reservation = MPTwoStepReservationSetup(
            page,
            environment_config,
            app_config,
            property_config=two_step_property,
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Individual reservation can be completed - Mobile")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683626")
    def test_individual_reservation_mobile(
        self,
        mobile_page,
        environment_config,
        app_config,
        mp_guest,
        two_step_property,
        mp_property_landing_urls,
    ) -> None:
        property_url = mp_property_landing_urls["two_step"]
        reservation = MPTwoStepReservationSetup(
            mobile_page,
            environment_config,
            app_config,
            property_url=property_url,
            property_config=two_step_property,
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Reserve As Business reservation can be completed - Desktop")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683635")
    def test_rab_reservation_desktop(
        self, page, environment_config, app_config, mp_guest, two_step_property
    ) -> None:
        reservation = MPTwoStepReservationSetup(
            page,
            environment_config,
            app_config,
            property_config=two_step_property,
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)

    @allure.title("Reserve As Business reservation can be completed - Mobile")
    @pytest.mark.smoke
    @pytest.mark.testrail("C683635")
    def test_rab_reservation_mobile(
        self,
        mobile_page,
        environment_config,
        app_config,
        mp_guest,
        two_step_property,
        mp_property_landing_urls,
    ) -> None:
        property_url = mp_property_landing_urls["two_step"]
        reservation = MPTwoStepReservationSetup(
            mobile_page,
            environment_config,
            app_config,
            property_url=property_url,
            property_config=two_step_property,
        )
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=True)
        assert reservation_code, "Expected a non-empty reservation code"
        reservation.assert_confirmation_email(mp_guest, reservation_code)
