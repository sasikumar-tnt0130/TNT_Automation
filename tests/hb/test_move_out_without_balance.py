import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.common.hb_move_out_page import HBMoveOutPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.title('A tenant with no balance can be moved out of their space')
@allure.feature("HB Smoke Test")
@allure.story("Move out without balance")
def test_move_out_without_balance(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    lease_data = test_data("quick_launch_lease")

    # Precondition: the old Robot suite ran this "Depends On Test From Quick
    # action Create a lease" - recreated here so this test owns the tenant it
    # moves out. Paying the move-in in cash (see test_leads_create_rental.py
    # for why cash on uat_storoutlet) leaves nothing owed.
    create_lease_through_quick_action(
        hb_login_page.page,
        timeout,
        environment_config,
        lease_data,
        hb_lead_guest,
        payment_method="cash",
    )

    # The old suite started from a Quick Actions "Move-Out" entry, which no
    # longer exists - confirmed live (2026-09-11, Bellflower): Quick Actions
    # only offers Move In/Reserve, Take a Payment and Sell Merchandise. The
    # tenant's own space is the entry point now.
    tenant = HBTenantSpacesPage(hb_login_page.page, timeout)
    tenant.open_tenants(lease_data["property_name"])
    tenant.open_tenant_details(hb_lead_guest["first_name"], hb_lead_guest["last_name"])

    move_out = HBMoveOutPage(hb_login_page.page, timeout)
    move_out.move_out_space(
        move_out.current_space_number(), test_data("move_out")["reason"]
    )
