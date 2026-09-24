import re

import allure
import pytest
from playwright.sync_api import expect

from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
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
@pytest.mark.usefixtures("two_step_superlease_checked")
def test_void_remove_autopay_and_move_out(
    page,
    environment_config,
    app_config,
    mp_guest,
    two_step_property,
    mp_property_landing_urls,
    hb_admin_session,
    test_data,
) -> None:
    # Old Robot Mariposa ReservationAndRentals cases 3-5 on one storefront
    # rental, walked live 2026-09-13 on uat_storoutlet/Chula Vista (space
    # OP1): void the payment, void the invoice it paid (a reason is
    # required), remove the AutoPay card, move out. Each run creates a
    # tenant and a sandbox card charge, then voids it and closes the lease.
    property_url = mp_property_landing_urls["two_step"]
    timeout = app_config.getint("browser", "timeout")
    rental_data = test_data("mp_rental")
    guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
    rental = MPTwoStepReservationSetup(
        page,
        environment_config,
        app_config,
        property_url=property_url,
        property_config=two_step_property,
    )

    with allure.step("Reserve and rent a unit with AutoPay"):
        rental.reserve_unit(mp_guest, renting_as_business=False)
        bill = rental.rent_reserved_unit(mp_guest, {**rental_data, "enroll_autopay": True})
    space_number = bill["space_number"]

    hb_admin_session.ensure_logged_in()
    hb_page = hb_admin_session.page
    tenants = HBTenantSpacesPage(hb_page, timeout)
    tenants.open_tenants(two_step_property.hb_property_name)
    tenants.open_storefront_tenant(guest_name, space_number)
    tenant_url = hb_page.url

    with allure.step("Void the payment and the invoice"):
        history = HBTransactionHistoryPage(hb_page, timeout)
        history.open()
        history.void_payment(bill["pay_now"])
        history.void_open_invoice("Automation - void the storefront rental invoice")

    with allure.step("Remove the AutoPay card and move the tenant out"):
        hb_page.goto(tenant_url)
        tenants.remove_autopay(space_number)
        HBMoveOutPage(hb_page, timeout).move_out_space(space_number, "No Longer Needed")
        page.goto(tenant_url)
        expect(page.get_by_text(re.compile(r"CLOSED LEASES")).first).to_be_visible(timeout=timeout)
