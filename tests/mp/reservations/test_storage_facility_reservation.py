import re
from datetime import date, timedelta

import allure
import pytest

from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from config.config_reader import load_property
from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_lead_follow_up_page import HBLeadFollowUpPage


@allure.title("A guest reservation shows its reservation code and emails a matching confirmation")
@allure.feature("MP Storage Facility Smoke")
@allure.story("Show Reservation Code + Validate Tenant email for Reservation")
def test_show_reservation_code_and_email(page, environment_config, app_config, mp_guest) -> None:
    # Old Robot suite's 8884 ("Show Reservation Code") and 10603
    # ("Validate Tenant email for Reservation") - one reservation covers
    # both, since 10603 only checks the email 8884's reservation sends.
    # Deliberately no settings fixture (unlike test_legacy_reservation.py,
    # whose class fixture rewrites the property's lease configuration):
    # this relies on the default property already serving Legacy (confirmed
    # live 2026-09-12, uat_storoutlet: Bellflower, "Reserve This Space"),
    # and reserve_unit fails clearly if the storefront serves Two-Step.
    if not (environment_config.mp_city and environment_config.mp_state):
        pytest.skip(
            f"No storefront property (mp_city/mp_state) configured for "
            f"{environment_config.name} in environments.ini"
        )
    reservation = MPLegacyReservationSetup(page, environment_config, app_config)

    with allure.step("8884: reservation code is shown on confirmation"):
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert re.fullmatch(r"[A-Z0-9]{4,}", reservation_code), (
            f"Unexpected reservation code {reservation_code!r}"
        )

    with allure.step("10603: confirmation email received with the reservation code"):
        reservation.assert_confirmation_email(mp_guest, reservation_code)


@allure.title(
    "A Two-Step guest reservation shows its code, emails a matching confirmation, "
    "appears as a web reservation lead in HB and bills consistently"
)
@allure.feature("MP Storage Facility Smoke")
@allure.story(
    "Show Reservation Code + Validate Tenant email for Reservation + "
    "Complete Storage Unit Reservation + Validate bill section details (Two-Step)"
)
def test_show_reservation_code_and_email_two_step(
    page,
    environment,
    environment_config,
    app_config,
    mp_guest,
    property_landing_page_url,
    hb_login_page,
) -> None:
    # Same 8884/10603 checks against the environment's Two-Step property
    # (environments.ini `two_step_property`, e.g. uat_storoutlet/chula_vista
    # - confirmed live 2026-09-12 serving "Reserve Now"), plus 8881 and 8900
    # in HB on the same reservation. Added after Bellflower's Legacy
    # reservations failed server-side (2026-09-13: POST /reservations ->
    # 400 UnableToReadPMSResponse).
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

    with allure.step("8884: reservation code is shown on confirmation"):
        reservation_code = reservation.reserve_unit(mp_guest, renting_as_business=False)
        assert re.fullmatch(r"[A-Z0-9]{4,}", reservation_code), (
            f"Unexpected reservation code {reservation_code!r}"
        )

    with allure.step("10603: confirmation email received with the reservation code"):
        email_web_rate = reservation.assert_confirmation_email(
            mp_guest,
            reservation_code,
            property_name=two_step_property.lease_configuration_property_name,
        )

    with allure.step("8881: reservation shows as a New Web Reservation lead in HB"):
        if hb_login_page.open_login_page():
            hb_login_page.submit_login_credentials()
        hb_login_page.assert_login_successful()
        leads_page = HBLeadManagementPage(page, timeout)
        leads_page.open_leads(two_step_property.hb_property_name)
        # MPTwoStepReservationFormPage.select_move_in_date picks tomorrow by
        # this machine's date - HB shows exactly that as the Reservation
        # Date (confirmed live 2026-09-13: picked Sep 14, HB "Sep 14, 2026").
        leads_page.assert_web_reservation_lead(
            mp_guest["email"], reservation_code, date.today() + timedelta(days=1)
        )

    with allure.step("8900: storefront bill section agrees with HB Lead Follow-Up"):
        bill = reservation.open_rental_from_email(mp_guest)
        charges_total = round(sum(bill["charges"].values()), 2)
        # pay_now is None on a form that signs the lease before payment
        # ("Sign Agreements" - stage Rutland), so only the sidebar is checked.
        expected = [bill["total"]] if bill["pay_now"] is None else [bill["total"], bill["pay_now"]]
        assert all(charges_total == amount for amount in expected), (
            f"Lease Summary doesn't add up: charges {bill['charges']} = {charges_total}, "
            f"Total Cost to Move-in {bill['total']}, Pay Now {bill['pay_now']}"
        )

        if hb_login_page.open_login_page():
            hb_login_page.submit_login_credentials()
        hb_login_page.assert_login_successful()
        # Opened from the lead's own "Manage Reservation", not Task Center
        # (user choice 2026-09-13): stage's Task Center lists ~12,000
        # due-today tasks, 20 per page, oldest first.
        leads_page.open_leads(two_step_property.hb_property_name)
        leads_page.open_reservation_follow_up(mp_guest["email"], bill["space_number"])
        follow_up = HBLeadFollowUpPage(page, timeout)
        try:
            hb_lease = follow_up.read_lease_details()
        finally:
            follow_up.close()

        # Like-for-like fields only (user choice 2026-09-13): the two
        # totals differ by design - the resumed storefront rental charges
        # rent from today plus a pre-selected protection plan, while HB's
        # Move-In Cost runs from the reserved move-in date with no plan
        # (live: $112.40 vs $101.60) - so they're attached, not compared.
        # The rental form's Lease Summary shows the web rate on
        # uat_storoutlet but not on stage/Rutland - there the reservation
        # email's "Web Rental Rate" is used instead (user choice 2026-09-13).
        storefront_rate, rate_source = bill["rates"].get("WEB RATE"), "rental form WEB RATE"
        if storefront_rate is None:
            storefront_rate, rate_source = email_web_rate, "confirmation email Web Rental Rate"
        allure.attach(
            f"{rate_source}: {storefront_rate}",
            name="storefront web rate",
            attachment_type=allure.attachment_type.TEXT,
        )
        assert hb_lease["monthly_rent"] == storefront_rate, (
            f"HB Monthly Rent {hb_lease['monthly_rent']} != storefront {rate_source} "
            f"{storefront_rate}"
        )
        storefront_deposit = next(
            (amount for label, amount in bill["charges"].items() if "deposit" in label.lower()),
            None,
        )
        assert hb_lease["security_deposit"] == storefront_deposit, (
            f"HB Security Deposit {hb_lease['security_deposit']} != storefront "
            f"{storefront_deposit}"
        )
        storefront_promotion = next(
            (label for label, amount in bill["charges"].items() if amount < 0), None
        )
        assert hb_lease["promotion"] == storefront_promotion, (
            f"HB promotion {hb_lease['promotion']!r} != storefront {storefront_promotion!r}"
        )
        allure.attach(
            f"Storefront Total Cost to Move-in: ${bill['total']:.2f}\n"
            f"HB Move-In Cost: ${hb_lease['move_in_cost']:.2f}\n"
            "Not compared - storefront charges from today plus a protection "
            "plan, HB from the reserved move-in date.",
            name="move-in totals",
            attachment_type=allure.attachment_type.TEXT,
        )
