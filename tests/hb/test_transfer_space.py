import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.title("A tenant's space can be transferred, its new lease signed and the transfer finalized")
@allure.feature("HB Smoke Test")
@allure.story("Sign Lease during transfer screen / Finalize Transfer screen")
def test_transfer_space_and_finalize(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    lease_data = test_data("quick_launch_lease")

    # Precondition: the old Robot suite ran both transfer scenarios "Depends
    # On Test From Quick action Create a lease" - recreated here so this test
    # owns the tenant it transfers. Cash for the same reason as the other
    # uat_storoutlet tests (its card form is missing its gateway API key).
    quick_launch = create_lease_through_quick_action(
        hb_login_page.page,
        timeout,
        environment_config,
        lease_data,
        hb_lead_guest,
        payment_method="cash",
    )

    tenant = HBTenantSpacesPage(hb_login_page.page, timeout)
    tenant.open_tenants(lease_data["property_name"])
    tenant.open_tenant_details(hb_lead_guest["first_name"], hb_lead_guest["last_name"])

    # "Sign Lease during transfer screen - Sign documents for Single spaces"
    tenant.start_transfer()
    new_space = tenant.setup_transfer()
    tenant.take_transfer_payment()
    tenant.confirm_transfer()
    initials = f"{hb_lead_guest['first_name'][0]}{hb_lead_guest['last_name'][0]}".upper()
    quick_launch.sign_documents_on_this_device(initials)
    tenant.finalize_transfer()

    # "Finalize Transfer screen"
    receipt = tenant.transfer_receipt(new_space)
    assert new_space.lstrip("#") in receipt["text"]
    assert hb_lead_guest["last_name"] in receipt["text"]
    # The first lease's move-in was paid, so the old space always carries
    # some credit into the transfer.
    assert receipt["Transfer Out Balance Applied"] > 0
    tenant.finish_transfer()
