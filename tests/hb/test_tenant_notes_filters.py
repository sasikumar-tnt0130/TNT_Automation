import allure

from pages.common.hb_tenant_notes_page import (
    COMMUNICATION_TYPES,
    NOTE_CATEGORIES,
    HBTenantNotesPage,
)
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.title("A tenant's communication filters and Add Note offer today's categories and spaces")
@allure.feature("HB Unified Communications")
@allure.story("Notes categories")
def test_tenant_note_filters_and_options(hb_login_page, app_config, hb_two_space_tenant) -> None:
    # Old Robot Unified_Communications/Categories_notes 14307 (the tenant's
    # space filter and notes category filter, with their options), 14309 (the
    # categories - today's 13 in order; Robot iterated 11) and 14460 (Add Note
    # offers the categories, the tenant and its spaces). Read-only, on the
    # session's two-space tenant (tests/hb/conftest.py): the Add Note draft is
    # closed unsaved.
    tenant = hb_two_space_tenant["tenant"]
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    page = hb_login_page.page
    notes = HBTenantNotesPage(page, timeout)
    notes.close_restored_drawers(wait_seconds=5)
    HBTenantSpacesPage(page, timeout).open_tenants(hb_two_space_tenant["property_name"])
    notes.open_tenant(tenant["name"])
    notes.reset_filters(tenant["spaces"])
    space_options = ["Tenant", *tenant["spaces"]]

    with allure.step("14307: type and space filters"):
        assert notes.options_of("All Communications") == COMMUNICATION_TYPES
        assert notes.options_of("Tenant") == space_options

    notes.choose("All Communications", "Notes")
    with allure.step("14307/14309: the notes category filter"):
        assert notes.options_of("All Notes") == ["All Notes", *NOTE_CATEGORIES]
    notes.choose("Notes", "All Communications")

    with allure.step("14460: Add Note offers the categories, the tenant and its spaces"):
        assert notes.note_form_options() == {"category": NOTE_CATEGORIES, "space": space_options}
