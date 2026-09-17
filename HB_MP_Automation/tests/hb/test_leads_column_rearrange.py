import allure
from playwright.sync_api import expect

from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_leads_grid_page import HBLeadsGridPage


@allure.title("A rearranged Leads column order holds for the session and Reset restores the default")
@allure.feature("HB Lead Management")
@allure.story("Rearrange columns on leads")
def test_rearranged_columns_hold_for_session_and_reset(
    hb_login_page, app_config, test_data
) -> None:
    # Old Robot Lead_Management/RearrangeLeadColumns 13563 (rearrange by drag
    # and drop), 13613 (kept after a browser refresh), 13615 (seen in a new
    # window) and 13700 (Reset back to the default). Confirmed live
    # 2026-09-14: the layout lives only in this browser session (sessionStorage
    # "vuex", no server save), so even a failed run leaves nothing behind.
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
    expect(grid.reset_link()).to_be_hidden()

    # 13563: drag "Lead Created" past "Name" (the Robot suite's own drag).
    grid.move_column("lead_created", "lead_name")
    moved_ids = list(default_ids)
    moved_ids.remove("lead_created")
    moved_ids.insert(moved_ids.index("lead_name") + 1, "lead_created")
    grid.wait_for_column_ids(moved_ids)
    expect(grid.reset_link()).to_be_visible(timeout=timeout)

    # 13613: a refresh keeps it.
    with allure.step("The rearranged order survives a refresh"):
        page.reload(wait_until="domcontentloaded")
        grid.switch_view("Reservations")
        grid.wait_for_column_ids(moved_ids)

    # 13615: a window opened from this one shows it too.
    popup = grid.open_in_new_window()
    try:
        popup_grid = HBLeadsGridPage(popup, timeout)
        popup_grid.switch_view("Reservations")
        popup_grid.wait_for_column_ids(moved_ids)
    finally:
        popup.close()

    # 13700: Reset brings the default back, and it holds after a refresh.
    with allure.step("Reset restores the default order"):
        grid.reset_link().click()
        grid.wait_for_column_ids(default_ids)
        page.reload(wait_until="domcontentloaded")
        grid.switch_view("Reservations")
        grid.wait_for_column_ids(default_ids)

    grid.switch_view("Active Leads")
