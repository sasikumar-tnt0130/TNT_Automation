import allure
from playwright.sync_api import expect

from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_leads_grid_page import HBLeadsGridPage

NEW_COLUMNS = ["First Name", "Last Name"]


@allure.title("Set Columns adds columns to the Leads view and Reset removes them")
@allure.feature("HB Lead Management")
@allure.story("Rearrange columns on leads")
def test_set_columns_adds_and_reset_removes(hb_login_page, app_config, test_data) -> None:
    # Old Robot Lead_Management/RearrangeLeadColumns 13565 ("we can add/edit
    # new columns for the default view" - it added First Name and Last Name
    # from the Lead group). Confirmed live 2026-09-14 that the added columns
    # go at the end and, like a rearrangement, live only in the browser
    # session until Reset.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    property_name = test_data("retire_lead")["property_name"]
    page = hb_login_page.page

    HBLeadManagementPage(page, timeout).open_leads(property_name)
    grid = HBLeadsGridPage(page, timeout)
    grid.switch_view("Reservations")
    default_ids = grid.column_ids()
    default_titles = grid.column_titles()
    assert not set(NEW_COLUMNS) & set(default_titles), (
        f"{NEW_COLUMNS} are already shown by default: {default_titles}"
    )

    grid.add_columns("Lead Created", NEW_COLUMNS)
    with allure.step("First Name and Last Name are added after the default columns"):
        grid.wait_for_column_titles(default_titles + NEW_COLUMNS)
    expect(grid.reset_link()).to_be_visible(timeout=timeout)

    with allure.step("Reset removes them again"):
        grid.reset_link().click()
        grid.wait_for_column_ids(default_ids)

    grid.switch_view("Active Leads")
