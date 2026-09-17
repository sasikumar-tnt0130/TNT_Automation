from datetime import date, timedelta

import allure
import pytest

from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from config.config_reader import load_property
from pages.common.hb_lead_management_page import HBLeadManagementPage


@allure.title("A storefront reservation can be cancelled from its lead in HB")
@allure.feature("MP Reservations and Rentals")
@allure.story("Reserve a Space in Mariposa + Retire a Lead From HummingBird")
def test_cancel_storefront_reservation_from_lead(
    page,
    environment,
    environment_config,
    app_config,
    mp_guest,
    property_landing_page_url,
    hb_login_page,
) -> None:
    # Old Robot Mariposa ReservationAndRentals: "Reserve a Space in
    # Mariposa" + "Retire a Lead From HummingBird". HB no longer retires a
    # lead that holds a reservation (confirmed live 2026-09-13, Chula Vista)
    # - it only offers "Cancel Reservation", so that's what's checked (user
    # choice). Runs on the environment's Two-Step property.
    property_key = app_config.get(environment, "two_step_property", fallback="").strip()
    if not property_key:
        pytest.skip(f"No two_step_property configured for {environment} in environments.ini")
    two_step_property = load_property(app_config, environment, property_key)
    property_url = property_landing_page_url(
        environment_config.mp_base_url, two_step_property.mp_state, two_step_property.mp_city
    )
    timeout = app_config.getint("browser", "timeout")
    reservation = MPTwoStepReservationSetup(
        page, environment_config, app_config, property_url=property_url
    )

    with allure.step("Reserve a space on the storefront"):
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)

    with allure.step("HB lists the reservation as a web reservation lead"):
        if hb_login_page.open_login_page():
            hb_login_page.submit_login_credentials()
        hb_login_page.assert_login_successful()
        leads = HBLeadManagementPage(page, timeout)
        leads.open_leads(two_step_property.hb_property_name)
        leads.assert_web_reservation_lead(
            mp_guest["email"], reservation_code, date.today() + timedelta(days=1)
        )

    with allure.step("Cancel the reservation from its lead"):
        leads.cancel_reservation_for_lead(
            mp_guest["email"], "Automation - cancel a storefront reservation from its lead"
        )
        leads.assert_lead_not_active(mp_guest["email"])
