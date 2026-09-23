from datetime import date, timedelta

import allure
import pytest

from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from pages.common.hb_lead_management_page import HBLeadManagementPage
from tests.mp.reservations._helpers import ensure_two_step_superlease


@pytest.fixture(scope="module", autouse=True)
def precondition(
    hb_admin_session, environment_config, app_config, two_step_property
) -> None:
    """Once: APW + Two-Step/CW/SL + days + Clear Cache (same as rentals)."""
    ensure_two_step_superlease(
        hb_admin_session, environment_config, app_config, two_step_property
    )


@allure.title("A storefront reservation can be cancelled from its lead in HB")
@allure.feature("MP Reservations and Rentals")
@allure.story("Reserve a Space in Mariposa + Retire a Lead From HummingBird")
def test_cancel_storefront_reservation_from_lead(
    page,
    environment_config,
    app_config,
    mp_guest,
    two_step_property,
    property_landing_page_url,
    hb_admin_session,
) -> None:
    # Old Robot Mariposa ReservationAndRentals: "Reserve a Space in
    # Mariposa" + "Retire a Lead From HummingBird". HB no longer retires a
    # lead that holds a reservation (confirmed live 2026-09-13, Chula Vista)
    # - it only offers "Cancel Reservation", so that's what's checked (user
    # choice). Runs on the environment's Two-Step property.
    property_url = property_landing_page_url(
        environment_config.mp_base_url, two_step_property.mp_state, two_step_property.mp_city
    )
    timeout = app_config.getint("browser", "timeout")
    reservation = MPTwoStepReservationSetup(
        page,
        environment_config,
        app_config,
        property_url=property_url,
        property_config=two_step_property,
    )

    with allure.step("Reserve a space on the storefront"):
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)

    with allure.step("HB lists the reservation as a web reservation lead"):
        hb_admin_session.ensure_logged_in()
        leads = HBLeadManagementPage(hb_admin_session.page, timeout)
        leads.open_leads(two_step_property.hb_property_name)
        leads.assert_web_reservation_lead(
            mp_guest["email"], reservation_code, date.today() + timedelta(days=1)
        )

    with allure.step("Cancel the reservation from its lead"):
        leads.cancel_reservation_for_lead(
            mp_guest["email"], "Automation - cancel a storefront reservation from its lead"
        )
        leads.assert_lead_not_active(mp_guest["email"])
