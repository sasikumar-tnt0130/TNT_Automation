import re

import allure
import pytest
from playwright.sync_api import expect

from common_utils.mp_my_account_setup import MPMyAccountSetup
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.title(
    "A tenant links another rental to their online account with its unit number and "
    "access code, and can remove it again"
)
@allure.feature("MP Storage Facility Smoke")
@allure.story(
    "Linking a Unit from HB to Website + Link a Rental Space to Online Bill Pay Account "
    "(Two-Step)"
)
@pytest.mark.usefixtures("two_step_superlease_checked")
def test_link_rented_space_to_online_account(
    page,
    environment_config,
    app_config,
    mp_guest,
    mp_second_guest,
    two_step_property,
    property_landing_page_url,
    hb_admin_session,
    test_data,
) -> None:
    # Old Robot suite's 8907 and 8859 (user choice 2026-09-13: two fresh
    # storefront rentals per run). Tenant 1 creates the online account;
    # tenant 2's space is linked into it with the unit number and the access
    # code HB issued, then removed again. Walked live 2026-09-13 on
    # uat_storoutlet/Chula Vista. Each run creates two tenants, one online
    # account and two sandbox card charges.
    state, city = two_step_property.mp_state, two_step_property.mp_city
    property_url = property_landing_page_url(environment_config.mp_base_url, state, city)
    rental_data = test_data("mp_rental")
    rental = MPTwoStepReservationSetup(
        page,
        environment_config,
        app_config,
        property_url=property_url,
        property_config=two_step_property,
    )

    with allure.step("Setup: tenant 1 rents a unit"):
        rental.reserve_unit(mp_guest, renting_as_business=False)
        space_1 = rental.rent_reserved_unit(mp_guest, rental_data)["space_number"]
    with allure.step("Setup: tenant 2 rents a unit"):
        rental.reserve_unit(mp_second_guest, renting_as_business=False)
        space_2 = rental.rent_reserved_unit(mp_second_guest, rental_data)["space_number"]
    assert space_1 != space_2, f"Both rentals got the same space {space_1}"

    with allure.step("HB: tenant 2's active gate access code"):
        hb_admin_session.ensure_logged_in()
        tenants = HBTenantSpacesPage(
            hb_admin_session.page, app_config.getint("browser", "timeout")
        )
        tenants.open_tenants(two_step_property.hb_property_name)
        access_code = tenants.gate_access_code(
            f"{mp_second_guest['first_name']} {mp_second_guest['last_name']}", space_2
        )

    account = MPMyAccountSetup(page, environment_config, app_config, billing_address=rental_data)
    my_account = account.account_page
    with allure.step("Tenant 1 creates the online account with the emailed code"):
        account.create_account_and_log_in(mp_guest, rental_data["account_password"], state, city)
        my_account.assert_space_listed(space_1)

    with allure.step("8907: a wrong access code is refused"):
        wrong_code = "000000" if access_code != "000000" else "999999"
        my_account.open_link_space_form()
        my_account.submit_link_space(state, city, space_2, wrong_code)
        my_account.assert_link_refused(space_2)

    with allure.step("8907/8859: tenant 2's space links with its HB access code"):
        my_account.submit_link_space(state, city, space_2, access_code)
        linked_card = my_account.assert_space_linked(space_2)
        if rental_data.get("enroll_autopay", True):
            assert "Autopay On" in linked_card, f"Linked space card lacks 'Autopay On': {linked_card!r}"
        expect(
            page.locator(".card-header").filter(has_text=f"Space {space_1}").first
        ).to_be_visible()
        account_info = my_account.open_account_info_for_space(space_2)
        assert mp_second_guest["email"] in account_info, (
            f"ACCOUNT INFO for {space_2} doesn't show tenant 2's email {mp_second_guest['email']}"
        )
        assert re.sub(r"\D", "", mp_second_guest["mobile"]) in account_info, (
            f"ACCOUNT INFO for {space_2} doesn't show tenant 2's phone {mp_second_guest['mobile']}"
        )

    with allure.step("Clean-up: remove the linked space again"):
        my_account.remove_space(space_2)
        expect(
            page.locator(".card-header").filter(has_text=f"Space {space_1}").first
        ).to_be_visible()
        expect(page.locator(".card-header").filter(has_text=f"Space {space_2}")).to_have_count(0)
