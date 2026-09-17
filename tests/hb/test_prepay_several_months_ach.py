import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@allure.title("A tenant can prepay several months by ACH from the tenant page")
@allure.feature("HB Smoke Test")
@allure.story("Prepay several months in Tenants")
def test_prepay_several_months_by_ach(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    # Old Robot suite's 8916 "Prepay several months in Tenants - Attempt to
    # pay with an Auth Card" - despite the name its steps pay by ACH: the
    # tenant page's Take a Payment, 4 months ahead, ACH, then the receipt.
    # Walked live 2026-09-13 on uat_storoutlet/Bellflower: $574.50 moved
    # Paid Through from Oct 31, 2026 to Mar 31, 2027 with $0.00 due.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    lease_data = test_data("quick_launch_lease")
    create_lease_through_quick_action(
        hb_login_page.page, timeout, environment_config, lease_data, hb_lead_guest
    )

    tenant = HBTenantSpacesPage(hb_login_page.page, timeout)
    tenant.open_tenants(lease_data["property_name"])
    tenant.open_tenant_details(hb_lead_guest["first_name"], hb_lead_guest["last_name"])
    before = tenant.read_lease_balance()
    tenant.open_take_payment()

    payment = HBQuickLaunchPage(hb_login_page.page, timeout)
    payment.select_number_of_months("4 Months")
    total = payment.read_total_payment()
    payment.pay_by_ach(
        environment_config.ach_routing_number,
        environment_config.ach_account_number,
        environment_config.ach_account_type,
        hb_lead_guest["first_name"],
        hb_lead_guest["last_name"],
    )
    payment.assert_ach_payment_receipt(
        environment_config.ach_account_type, environment_config.ach_account_number
    )
    payment.assert_amount_paid(total)
    payment.finish_and_close()

    with allure.step("The tenant is paid at least 4 more months ahead, with nothing due"):
        after = tenant.read_lease_balance(changed_from=before)
        months_added = (after["paid_through"].year - before["paid_through"].year) * 12 + (
            after["paid_through"].month - before["paid_through"].month
        )
        assert months_added >= 4, (
            f"Paid Through moved only {months_added} month(s): "
            f"{before['paid_through']} -> {after['paid_through']}"
        )
        assert after["balance_due"] == 0, (
            f"Total Balance Due after prepaying is ${after['balance_due']:,.2f}, not $0.00"
        )
