import re

import allure
import pytest
from playwright.sync_api import expect

from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from config.config_reader import load_property
from pages.common.hb_move_out_page import HBMoveOutPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage
from pages.common.hb_transaction_history_page import HBTransactionHistoryPage


@allure.title(
    "A storefront rental's payment and invoice can be voided in HB, its AutoPay card "
    "removed and the tenant moved out"
)
@allure.feature("MP Reservations and Rentals")
@allure.story(
    "Reserve a Space and convert to Rental + Void the Payment and Invoice + "
    "Remove Card Details and Move out the Tenant"
)
def test_void_remove_autopay_and_move_out(
    page,
    environment,
    environment_config,
    app_config,
    mp_guest,
    property_landing_page_url,
    hb_login_page,
    test_data,
) -> None:
    # Old Robot Mariposa ReservationAndRentals cases 3-5 on one storefront
    # rental, walked live 2026-09-13 on uat_storoutlet/Chula Vista (space
    # OP1): void the payment, void the invoice it paid (a reason is
    # required), remove the AutoPay card, move out. Each run creates a
    # tenant and a sandbox card charge, then voids it and closes the lease.
    property_key = app_config.get(environment, "two_step_property", fallback="").strip()
    if not property_key:
        pytest.skip(f"No two_step_property configured for {environment} in environments.ini")
    two_step_property = load_property(app_config, environment, property_key)
    property_url = property_landing_page_url(
        environment_config.mp_base_url, two_step_property.mp_state, two_step_property.mp_city
    )
    timeout = app_config.getint("browser", "timeout")
    rental_data = test_data("mp_rental")
    guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
    rental = MPTwoStepReservationSetup(page, environment_config, app_config, property_url=property_url)

    with allure.step("Reserve and rent a unit with AutoPay"):
        rental.reserve_unit(mp_guest, renting_as_business=False)
        bill = rental.rent_reserved_unit(mp_guest, {**rental_data, "enroll_autopay": True})
    space_number = bill["space_number"]

    if hb_login_page.open_login_page():
        hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    tenants = HBTenantSpacesPage(page, timeout)
    tenants.open_tenants(two_step_property.hb_property_name)
    tenants.open_storefront_tenant(guest_name, space_number)
    tenant_url = page.url

    with allure.step("Void the payment and the invoice"):
        history = HBTransactionHistoryPage(page, timeout)
        history.open()
        history.void_payment(bill["pay_now"])
        history.void_open_invoice("Automation - void the storefront rental invoice")

    with allure.step("Remove the AutoPay card and move the tenant out"):
        page.goto(tenant_url)
        tenants.remove_autopay(space_number)
        HBMoveOutPage(page, timeout).move_out_space(space_number, "No Longer Needed")
        page.goto(tenant_url)
        expect(page.get_by_text(re.compile(r"CLOSED LEASES")).first).to_be_visible(timeout=timeout)
