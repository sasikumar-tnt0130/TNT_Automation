import allure

from pages.common.hb_lead_management_page import HBLeadManagementPage


@allure.title('All active leads can be retired')
@allure.feature("HB Lead Management")
@allure.story("Retire all active leads")
def test_all_active_leads_can_be_retired(
    hb_login_page, app_config, test_data
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    retire_lead_data = test_data("retire_lead")
    lead_management = HBLeadManagementPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    lead_management.retire_all_active_leads(
        retire_lead_data["property_name"],
        retire_lead_data["notes"],
    )
