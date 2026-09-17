import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@allure.title('A tenant can pay several months at once with cash')
@allure.feature("HB Smoke Test")
@allure.story("Make payment for several months")
def test_pay_several_months_with_cash(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
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
    quick_launch.select_number_of_months("3 Months")
    quick_launch.pay_by_cash()
    quick_launch.assert_payment_receipt("Cash")
    quick_launch.finish_and_close()
