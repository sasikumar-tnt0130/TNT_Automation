from datetime import date

import allure
import pytest

from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from config.config_reader import load_property
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.title(
    "A Two-Step reservation converts to a rental with autopay, shows in HB as a "
    "current tenant and emails a matching confirmation"
)
@allure.feature("MP Storage Facility Smoke")
@allure.story(
    "Rent Storage w/ enrolling for auto-debit + Convert Reservation to Rental + "
    "Validate Tenant email for Rental (Two-Step)"
)
def test_rent_reserved_unit_with_autopay(
    page,
    environment,
    environment_config,
    app_config,
    mp_guest,
    property_landing_page_url,
    hb_login_page,
    test_data,
) -> None:
    # Old Robot suite's 8872, 8885, 10604 and 10633 on one storefront rental
    # of the environment's Two-Step property (environments.ini
    # `two_step_property`). Walked live 2026-09-13 on uat_storoutlet/Chula
    # Vista. Each run creates a tenant and a sandbox card charge there.
    property_key = app_config.get(environment, "two_step_property", fallback="").strip()
    if not property_key:
        pytest.skip(f"No two_step_property configured for {environment} in environments.ini")
    two_step_property = load_property(app_config, environment, property_key)
    property_url = property_landing_page_url(
        environment_config.mp_base_url, two_step_property.mp_state, two_step_property.mp_city
    )
    rental_data = test_data("mp_rental")
    enroll_autopay = rental_data.get("enroll_autopay", True)
    guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
    reservation = MPTwoStepReservationSetup(
        page, environment_config, app_config, property_url=property_url
    )

    with allure.step("Reserve a unit on the Two-Step property"):
        reservation.reserve_unit(mp_guest, renting_as_business=False)

    with allure.step("8872: rent the reserved unit, enrolling in autopay"):
        # Bill consistency (charges = Total Cost to Move-in = Pay Now) is
        # checked inside rent_reserved_unit, before anything is charged.
        bill = reservation.rent_reserved_unit(mp_guest, rental_data)
    amount_paid = bill["pay_now"]
    security_deposit = next(
        (amount for label, amount in bill["charges"].items() if "deposit" in label.lower()),
        None,
    )

    with allure.step("10604/10633: rental confirmation (and autopay) emails"):
        # The rental form's move-in date defaults to today by this machine's
        # date - HB and the email both show that date (confirmed live).
        reservation.assert_rental_emails(
            mp_guest,
            bill["space_number"],
            date.today(),
            amount_paid,
            security_deposit,
            autopay=enroll_autopay,
        )

    with allure.step("8885: the rental shows in HB as a current tenant with autopay"):
        if hb_login_page.open_login_page():
            hb_login_page.submit_login_credentials()
        hb_login_page.assert_login_successful()
        tenants = HBTenantSpacesPage(page, app_config.getint("browser", "timeout"))
        tenants.open_tenants(two_step_property.hb_property_name)
        tenants.assert_web_rental_tenant(
            guest_name,
            bill["space_number"],
            date.today(),
            amount_paid,
            card_last4=environment_config.card_number[-4:] if enroll_autopay else None,
        )
