import allure
import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup


@pytest.fixture(scope="class")
def _two_step_flow_configured(
    browser, environment_config, app_config, two_step_property
) -> None:
    """One-time admin setup on a temporary HB context (one Chromium context)."""
    from common_utils.browser_sessions import hb_admin_context

    with hb_admin_context(browser, environment_config, app_config) as hb_login_page:
        LeaseConfigurationSetup(
            hb_login_page,
            environment_config,
            app_config,
            property_name=two_step_property.lease_configuration_property_name,
            fms_property_name=two_step_property.fms_property_name,
        ).enable_two_step_clickwrap_and_super_lease()


@allure.feature("MP Reservation")
@allure.story("Two-Step Flow: Reservation")
@pytest.mark.usefixtures("_two_step_flow_configured")
class TestTwoStepReservation:
    # Confirmed live (2026-09-08, stage): environment_config's own
    # default property (Hamilton Self Storage/Garden Grove) is a
    # Mariposa-only property that can never enable Two-Step Rental - a
    # hard, permanent site-side restriction (attempting it there leaves
    # the switch snapping back to unchecked no matter how long you
    # wait), not a config toggle. This suite runs against
    # properties.ini two_step_property (e.g. Rutland/Lightning Storage)
    # via the two_step_property fixture.

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
        property_landing_page_url,
    ) -> None:
        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            two_step_property.mp_state,
            two_step_property.mp_city,
        )
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
        property_landing_page_url,
    ) -> None:
        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            two_step_property.mp_state,
            two_step_property.mp_city,
        )
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
