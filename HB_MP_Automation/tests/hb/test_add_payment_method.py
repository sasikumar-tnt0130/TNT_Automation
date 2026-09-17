import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.common.hb_tenant_payment_methods_page import HBTenantPaymentMethodsPage


@allure.title('A new payment method can be added for a tenant')
@allure.feature("HB Smoke Test")
@allure.story("Add a payment method")
def test_add_payment_method_for_tenant(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    # Old Robot suite's "Add a payment method" (ACH). Walked live 2026-09-13
    # (uat_storoutlet/Bellflower): sidebar -> Payment Methods -> "+ Add New
    # Payment Method" -> ACH -> Save listed "Checking ending in 6667".
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

    payment_methods = HBTenantPaymentMethodsPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    payment_methods.open_tenants(lease_data["property_name"])
    payment_methods.open_tenant_details(
        hb_lead_guest["first_name"], hb_lead_guest["last_name"]
    )
    payment_methods.open_payment_methods_menu()
    payment_methods.add_ach_payment_method(
        hb_lead_guest["first_name"],
        hb_lead_guest["last_name"],
        environment_config.ach_account_type,
        environment_config.ach_routing_number,
        environment_config.ach_account_number,
    )
    payment_methods.assert_payment_method_added(environment_config.ach_account_number)
