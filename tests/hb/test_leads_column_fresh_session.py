import allure

from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_leads_grid_page import HBLeadsGridPage
from pages.common.hb_login_page import HBLoginPage


@allure.title("A rearranged Leads column order stays with its browser session")
@allure.feature("HB Lead Management")
@allure.story("Rearrange columns on leads")
def test_fresh_session_shows_default_column_order(
    hb_login_page, browser, environment_config, app_config, test_data
) -> None:
    # Old Robot Lead_Management/RearrangeLeadColumns 13614 (close and reopen
    # the browser) and 13616 (log out, then log in again as the same user).
    # Robot expected the rearranged order to carry over; confirmed live
    # 2026-09-14 that it lives only in the browser session (sessionStorage
    # "vuex", never saved to the account) - user choice: migrate today's
    # behaviour, so a fresh browser and login must show the default order.
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

    grid.move_column("lead_created", "lead_name")
    moved_ids = list(default_ids)
    moved_ids.remove("lead_created")
    moved_ids.insert(moved_ids.index("lead_name") + 1, "lead_created")
    grid.wait_for_column_ids(moved_ids)

    # A separate browser context is a freshly launched browser with nothing
    # carried over; logging in there is the same user logging in again.
    fresh_context = browser.new_context(no_viewport=True)
    try:
        fresh_page = fresh_context.new_page()
        fresh_page.set_default_timeout(timeout)
        with allure.step("Log in again in a fresh browser"):
            fresh_login = HBLoginPage(fresh_page, environment_config, timeout)
            fresh_login.open_login_page()
            fresh_login.submit_login_credentials()
            fresh_login.assert_login_successful()
        HBLeadManagementPage(fresh_page, timeout).open_leads(property_name)
        fresh_grid = HBLeadsGridPage(fresh_page, timeout)
        fresh_grid.switch_view("Reservations")
        with allure.step("The fresh session shows the default order"):
            fresh_grid.wait_for_column_ids(default_ids)
    finally:
        fresh_context.close()

    # Tidy the first session. Its layout never left this browser, so there's
    # nothing to undo on the server - skip quietly if HB has ended it.
    with allure.step("Reset the first session's layout"):
        if grid.reset_link().is_visible():
            grid.reset_link().click()
            grid.wait_for_column_ids(default_ids)
