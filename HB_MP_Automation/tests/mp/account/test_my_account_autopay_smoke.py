import allure

from common_utils.mp_my_account_setup import MPMyAccountSetup
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.title(
    "A storefront tenant creates an online account, cancels autopay, pays a month "
    "ahead and re-enrols in autopay"
)
@allure.feature("MP Storage Facility Smoke")
@allure.story(
    "Complete Pay Bill + Enroll in Autopay + Cancel Autopay + Autopay emails from "
    "My Account (Two-Step)"
)
def test_my_account_pay_bill_and_autopay(
    page,
    environment_config,
    app_config,
    mp_guest,
    two_step_property,
    property_landing_page_url,
    hb_login_page,
    test_data,
) -> None:
    # Old Robot suite's 8860, 8861, 8862 and 10605, on a tenant rented in
    # this same test (user choice 2026-09-13: fresh tenant each run) on the
    # environment's Two-Step property. Walked live 2026-09-13 on
    # uat_storoutlet/Chula Vista. Each run creates a tenant, an online
    # account and two sandbox card charges (the rental and one month ahead).
    property_url = property_landing_page_url(
        environment_config.mp_base_url, two_step_property.mp_state, two_step_property.mp_city
    )
    rental_data = test_data("mp_rental")
    guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
    card_last4 = environment_config.card_number[-4:]
    rental = MPTwoStepReservationSetup(
        page,
        environment_config,
        app_config,
        property_url=property_url,
        property_config=two_step_property,
    )
    # Billing address = the address the tenant gave at rental (Get Access).
    account = MPMyAccountSetup(page, environment_config, app_config, billing_address=rental_data)

    with allure.step("Setup: reserve and rent a unit with autopay"):
        rental.reserve_unit(mp_guest, renting_as_business=False)
        bill = rental.rent_reserved_unit(mp_guest, {**rental_data, "enroll_autopay": True})
    space_number = bill["space_number"]

    with allure.step("Create the tenant's online account with the emailed code"):
        account.create_account_and_log_in(
            mp_guest,
            rental_data["account_password"],
            two_step_property.mp_state,
            two_step_property.mp_city,
        )
        account.account_page.assert_space_listed(space_number)

    with allure.step("8862: cancel autopay"):
        account.account_page.cancel_autopay()

    with allure.step("8860: pay the bill one month ahead"):
        payment = account.pay_bill(mp_guest, months=1)
        assert payment["amount_paid"] == payment["total_to_be_charged"], (
            f"Amount paid {payment['amount_paid']} != Total To Be Charged "
            f"{payment['total_to_be_charged']}"
        )
        assert payment["card"] and payment["card"].endswith(card_last4), (
            f"Payment confirmation card {payment['card']!r} doesn't end in {card_last4}"
        )
        account.assert_payment_email(mp_guest, space_number, payment["amount_paid"])

    # The rental already sent one "Auto Payment Confirmation" - only one
    # arriving after this point proves the re-enrolment's email.
    inbox_baseline = account.email_baseline(mp_guest)
    with allure.step("8861: re-enrol in autopay"):
        enrollment = account.enroll_autopay(mp_guest)
        assert enrollment["payment_schedule"] == "1st of each month", (
            f"Unexpected payment schedule {enrollment['payment_schedule']!r}"
        )

    with allure.step("10605: autopay enrolment email"):
        account.assert_autopay_enrollment_email(mp_guest, inbox_baseline)

    with allure.step("HB: prepaid balance and autopay cancel/re-enrol notes"):
        if hb_login_page.open_login_page():
            hb_login_page.submit_login_credentials()
        hb_login_page.assert_login_successful()
        tenants = HBTenantSpacesPage(page, app_config.getint("browser", "timeout"))
        tenants.open_tenants(two_step_property.hb_property_name)
        tenants.assert_autopay_cancelled_and_reenrolled(
            guest_name,
            space_number,
            round(bill["pay_now"] + payment["amount_paid"], 2),
            card_last4,
        )
