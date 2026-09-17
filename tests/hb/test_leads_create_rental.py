import allure

from common_utils.hb_quick_launch_lease_setup import complete_lease_from_move_in
from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@allure.title('A reserved lead can be moved in and finalized into a rental from Leads')
@allure.feature("HB Smoke Test")
@allure.story("From Leads create a Rental")
def test_create_rental_from_leads(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    lease_data = test_data("quick_launch_lease")
    property_name = lease_data["property_name"]

    # Precondition: the old Robot suite ran this scenario "Depends On Test
    # Create Reservation - Through Quick Action" - recreated here so this
    # test owns the reserved lead it converts instead of relying on
    # another test's leftover data.
    quick_launch = HBQuickLaunchPage(hb_login_page.page, timeout)
    quick_launch.open_quick_launch_for_property(property_name)
    quick_launch.start_new_contact(hb_lead_guest["email"])
    quick_launch.fill_lead_details(
        hb_lead_guest["first_name"],
        hb_lead_guest["last_name"],
        hb_lead_guest["email"],
        hb_lead_guest["phone_number"],
        lease_data["lead_initiated"],
        lease_data["lead_source"],
    )
    quick_launch.reserve_first_available_space(exclude_number_prefixes=("pa",))

    leads = HBLeadManagementPage(hb_login_page.page, timeout)
    leads.open_leads(property_name)
    leads.open_lead_and_start_move_in(
        hb_lead_guest["first_name"], hb_lead_guest["last_name"]
    )

    # Cash rather than the old Robot suite's card payment: confirmed live
    # (2026-09-11, uat_storoutlet/Bellflower) that property's Credit/Debit
    # form uses the tenant payment gateway's hosted card fields, which show
    # "Tenant Payments form is missing an API key." and never render the
    # card number/CVV inputs - a sandbox configuration gap, not this flow.
    complete_lease_from_move_in(
        quick_launch,
        environment_config,
        lease_data,
        hb_lead_guest,
        payment_method="cash",
    )
