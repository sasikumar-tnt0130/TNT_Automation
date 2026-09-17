import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@allure.title('A tenant bill can be paid with ACH')
@allure.feature("HB Smoke Test")
@allure.story("Pay a tenant bill with ACH auth .net")
def test_pay_tenant_bill_with_ach(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    # Old Robot suite's 8640. The ACH form was walked live 2026-09-13
    # (uat_storoutlet/Bellflower): HB rejects routing 110000000, so
    # secrets.ini [payment] carries that suite's 011401533 / 856667.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    lease_data = test_data("quick_launch_lease")
    create_lease_through_quick_action(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
        environment_config,
        lease_data,
        hb_lead_guest,
    )

    quick_launch = HBQuickLaunchPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    quick_launch.open_take_payment_for_property(lease_data["property_name"])
    quick_launch.search_and_select_tenant_for_payment(hb_lead_guest["last_name"])
    quick_launch.ensure_payable_balance()
    quick_launch.pay_by_ach(
        environment_config.ach_routing_number,
        environment_config.ach_account_number,
        environment_config.ach_account_type,
        hb_lead_guest["first_name"],
        hb_lead_guest["last_name"],
    )
    quick_launch.assert_ach_payment_receipt(
        environment_config.ach_account_type, environment_config.ach_account_number
    )
    quick_launch.finish_and_close()
