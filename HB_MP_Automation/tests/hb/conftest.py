import logging

import allure
import pytest
from playwright.sync_api import Browser

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from common_utils.hb_session_tenants import (
    create_single_tenant,
    create_two_space_tenant,
    move_out_tenants,
)
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_tenant_notes_page import HBTenantNotesPage

# Fresh test tenants for the Unified Communications tests, created once per
# session instead of fixed names in the test data (user choice 2026-09-14) -
# each only when a test first asks for it, and every space moved out again at
# the end of the session.


@pytest.fixture(scope="session")
def hb_session_setup(browser: Browser, app_config, environment_config, test_data):
    """A logged-in page of its own for creating this session's test tenants
    on the Quick Launch lease property, and moving every one of them out at
    the end - even if creating one failed part-way."""
    lease_data = test_data("quick_launch_lease")
    if not lease_data.get("property_name"):
        pytest.skip("No Quick Launch lease property configured for this environment")
    timeout = app_config.getint("browser", "timeout")
    context = browser.new_context(**desktop_context_options(app_config))
    page = context.new_page()
    prepare_desktop_page(page, app_config, record_artifacts=False)
    login = HBLoginPage(page, environment_config, timeout)
    created: list[dict] = []
    try:
        login.open_login_page()
        login.submit_login_credentials()
        login.assert_login_successful()
        HBTenantNotesPage(page, timeout).close_restored_drawers(wait_seconds=5)
        yield {"page": page, "timeout": timeout, "lease_data": lease_data, "created": created}
    finally:
        problems: list[str] = []
        if created:
            with allure.step("Move out this session's test tenants"):
                page.goto(environment_config.hb_base_url.rstrip("/") + "/dashboard")
                if "/login" in page.url:
                    login.submit_login_credentials()
                    login.assert_login_successful()
                problems = move_out_tenants(
                    page, timeout, environment_config, lease_data["property_name"], created,
                    test_data("move_out")["reason"],
                )
                if problems:
                    logging.warning("Session tenants not moved out: %s", problems)
                    allure.attach(
                        "\n".join(problems), name="Not moved out", attachment_type=allure.attachment_type.TEXT
                    )
        close_context_with_videos(
            context, app_config, name="hb-session-setup-video"
        )
        if problems:
            # A failure, not just a warning: the first run left Space 0040
            # occupied and only a warning said so (2026-09-14).
            pytest.fail(f"Session test tenants not moved out: {problems}")


@pytest.fixture(scope="session")
def hb_comm_tenants(hb_session_setup, environment_config) -> dict:
    """This session's one-space tenant ("single": name, spaces, space, email,
    phone_number, status) and its Alternate contact ("alternate": name,
    designation, email, phone) - see create_single_tenant."""
    setup = hb_session_setup
    with allure.step("Create this session's one-space test tenant"):
        single, alternate = create_single_tenant(
            setup["page"], setup["timeout"], environment_config, setup["lease_data"], setup["created"]
        )
    return {"property_name": setup["lease_data"]["property_name"], "single": single, "alternate": alternate}


@pytest.fixture(scope="session")
def hb_two_space_tenant(hb_session_setup, environment_config) -> dict:
    """This session's two-space tenant ("tenant", as in hb_comm_tenants),
    seeded with an email and a text on each space, a long text and a phone
    log - see create_two_space_tenant."""
    setup = hb_session_setup
    with allure.step("Create this session's two-space test tenant"):
        tenant = create_two_space_tenant(
            setup["page"], setup["timeout"], environment_config, setup["lease_data"], setup["created"]
        )
    return {"property_name": setup["lease_data"]["property_name"], "tenant": tenant}
