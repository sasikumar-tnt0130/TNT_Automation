import allure

from common_utils.hb_quick_launch_lease_setup import (
    add_space_and_lease_for_tenant,
    create_lease_through_quick_action,
)
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@allure.title('A tenant with two leases can pay for both spaces in one cash payment')
@allure.feature("HB Smoke Test")
@allure.story("Make payments for multiple leases")
def test_pay_multiple_leases_with_cash(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    lease_data = test_data("quick_launch_lease")

    # Precondition: the old Robot suite ran this scenario "Depends On Test
    # From Quick action Create a lease" - recreated here so this test owns
    # the tenant it adds a second lease to. Cash for the same reason as
    # test_leads_create_rental.py: uat_storoutlet/Bellflower's card form is
    # missing its tenant payment gateway API key.
    create_lease_through_quick_action(
        hb_login_page.page,
        timeout,
        environment_config,
        lease_data,
        hb_lead_guest,
        payment_method="cash",
    )
    add_space_and_lease_for_tenant(
        hb_login_page.page, timeout, lease_data, hb_lead_guest
    )

    # add_space_and_lease_for_tenant finishes on the tenant's own page, whose
    # bottom bar has its own "Take a Payment" button - a fresh navigation
    # back to the dashboard (open_login_page redirects there once logged
    # in) leaves only the Quick Actions one.
    hb_login_page.open_login_page()

    quick_launch = HBQuickLaunchPage(hb_login_page.page, timeout)
    quick_launch.open_take_payment_for_property(lease_data["property_name"])
    quick_launch.search_and_select_tenant_for_payment(hb_lead_guest["last_name"])
    total_due = quick_launch.select_all_spaces_for_payment()
    quick_launch.pay_by_cash()
    quick_launch.assert_payment_receipt("Cash")
    quick_launch.assert_amount_paid(total_due)
    quick_launch.finish_and_close()
