import uuid

import allure

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_leads_grid_page import HBLeadsGridPage
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_reports_page import HBReportsPage


@allure.title("A Leads view saved as the default report opens by default until it's deleted")
@allure.feature("HB Lead Management")
@allure.story("Rearrange columns on leads")
def test_saved_report_opens_as_default_view(
    hb_login_page, browser, environment_config, app_config, test_data
) -> None:
    # Old Robot Lead_Management/RearrangeLeadColumns 13564 ("we can create a
    # new view and it can be saved as default view"). Unlike the column
    # layout, a saved report and "Make my default report" are stored on the
    # server for the shared login, so the test deletes its report ("Delete for
    # Everyone", user choice 2026-09-14) whatever happens, and checks the
    # default goes back to Active Leads. The name is unique per run so a
    # leftover from an interrupted run can't clash.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    property_name = test_data("retire_lead")["property_name"]
    page = hb_login_page.page
    report_name = f"QA automation view {uuid.uuid4().hex[:6]}"

    def open_leads_after_fresh_login():
        # A new browser context = a new browser; the view it opens on is the
        # login's default (a session remembers the last view picked).
        context = browser.new_context(**desktop_context_options(app_config))
        fresh_page = context.new_page()
        prepare_desktop_page(fresh_page, app_config)
        fresh_login = HBLoginPage(fresh_page, environment_config, timeout)
        fresh_login.open_login_page()
        fresh_login.submit_login_credentials()
        fresh_login.assert_login_successful()
        HBLeadManagementPage(fresh_page, timeout).open_leads(property_name)
        return context, HBLeadsGridPage(fresh_page, timeout)

    HBLeadManagementPage(page, timeout).open_leads(property_name)
    grid = HBLeadsGridPage(page, timeout)
    grid.switch_view("Active Leads")

    grid.save_report(
        report_name, "QA automation - temporary default view, deleted by the test", make_default=True
    )
    try:
        with allure.step("The saved report is offered and opened"):
            assert report_name in grid.view_options(), f"{report_name} not offered"
            grid.expect_current_view(report_name)

        context, fresh_grid = open_leads_after_fresh_login()
        try:
            with allure.step("A fresh login opens the saved report as the default view"):
                fresh_grid.expect_current_view(report_name)
        finally:
            close_context_with_videos(context, app_config, name="fresh-login-video")
    finally:
        reports = HBReportsPage(page, timeout)
        reports.open_reports_library()
        reports.delete_custom_report(report_name, for_everyone=True)

    context, fresh_grid = open_leads_after_fresh_login()
    try:
        with allure.step("After deleting it, a fresh login opens Active Leads again"):
            fresh_grid.expect_current_view("Active Leads")
            assert report_name not in fresh_grid.view_options(), f"{report_name} still offered"
    finally:
        close_context_with_videos(
            context, app_config, name="fresh-login-after-delete-video"
        )
