import allure
import pytest

from pages.common.hb_communication_filters_page import HBCommunicationFiltersPage
from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_leads_grid_page import HBLeadsGridPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage

# Old Robot Unified_Communications/Space_Specific. Read-only throughout; the
# tenants are created for the session (hb_two_space_tenant - seeded with an
# email and a text on each space - and hb_comm_tenants, tests/hb/conftest.py).
# Not migrated (confirmed live 2026-09-14, user choices):
# - 13470/13485: a new contact's onboarding drawer has no communication icon.
# - 13481: Task Center's pending move-ins only offer "First Follow Up", which
#   starts HB's follow-up timer on someone else's lead - not reachable.
# Covered without a test of its own: 13698 (a space added to an existing
# tenant is listed on its filter) - the session's two-space tenant gets its
# second space through Add Space (paid in cash, not Robot's card), and
# test_tenant_profile_space_filter checks the filter lists both spaces.


def _login(hb_login_page, app_config) -> HBCommunicationFiltersPage:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    filters = HBCommunicationFiltersPage(hb_login_page.page, app_config.getint("browser", "timeout"))
    filters.close_restored_drawers(wait_seconds=5)
    return filters


@allure.title("A tenant's communications filter by space, for every type")
@allure.feature("HB Unified Communications")
@allure.story("Space specific communications")
def test_tenant_profile_space_filter(hb_login_page, app_config, hb_two_space_tenant, hb_comm_tenants) -> None:
    # 13467/13447 (the tenant profile has the space filter), 13449 (it lists
    # every space), 13448 ("Tenant" shows every space's communications),
    # 13451/13450 (one space at a time, Email and Text filtered to it - Robot
    # left Phone and Notes commented out; notes are covered by
    # test_tenant_notes_add_pin_filter) and 13452 (a single-space tenant's
    # filter is just Tenant and that space).
    filters = _login(hb_login_page, app_config)
    property_name = hb_two_space_tenant["property_name"]
    tenants = HBTenantSpacesPage(hb_login_page.page, filters.timeout)
    two = hb_two_space_tenant["tenant"]
    single = hb_comm_tenants["single"]

    tenants.open_tenants(property_name)
    filters.open_tenant(two["name"])
    filters.reset_filters(two["spaces"])
    with allure.step("13467/13449: the space filter lists the tenant and every space"):
        assert filters.options_of("Tenant") == ["Tenant", *two["spaces"]]
    with allure.step("13448: 'Tenant' shows communications for every space"):
        spaces_listed = {space for _, space in filters.cards()}
        assert set(two["spaces"]) <= spaces_listed, spaces_listed

    showing_type = "All Communications"
    for kind in ("Email", "Text"):
        filters.choose(showing_type, kind)
        showing_type = kind
        showing_space = "Tenant"
        for space in two["spaces"]:
            with allure.step(f"13451/13450: {kind} for space {space} only"):
                filters.choose(showing_space, space)
                showing_space = space
                filters.expect_cards_only(kind, space)
        filters.choose(showing_space, "Tenant")
    filters.choose(showing_type, "All Communications")

    tenants.open_tenants(property_name)
    filters.open_tenant(single["name"])
    filters.reset_filters(single["spaces"])
    with allure.step("13452: a single-space tenant's filter is Tenant and that space"):
        assert filters.options_of("Tenant") == ["Tenant", single["space"]]


@allure.title("The Communication Center filters a tenant by space, also while composing")
@allure.feature("HB Unified Communications")
@allure.story("Space specific communications")
def test_communication_center_space_filter(hb_login_page, app_config, hb_two_space_tenant) -> None:
    # 13466 (the Communication Center shows the space filter for a tenant) and
    # 13649 (the filter while composing - today Send Email's own
    # "Space/Subject" select). The email draft is closed unsent.
    filters = _login(hb_login_page, app_config)
    two = hb_two_space_tenant["tenant"]

    HBTenantSpacesPage(hb_login_page.page, filters.timeout).open_tenants(hb_two_space_tenant["property_name"])
    filters.open_in_communication_center(two["name"])
    with allure.step("13466: the Communication Center's space filter"):
        assert filters.options_of("Tenant") == ["Tenant", *two["spaces"]]
    with allure.step("13649: Send Email offers the tenant's spaces"):
        options = filters.email_compose_space_options()
        assert set(two["spaces"]) <= set(options), options


@allure.title("A lead's communications have the space filter")
@allure.feature("HB Unified Communications")
@allure.story("Space specific communications")
def test_lead_communication_space_filter(hb_login_page, app_config, test_data) -> None:
    # 13482 (the filter in a lead's communications): the first lead in the
    # Reservations view, whose filter must list "Tenant" and exactly the
    # spaces its own cards name.
    lead_property = test_data("communication").get("lead_property")
    if not lead_property:
        pytest.skip("No lead property configured for this environment")
    filters = _login(hb_login_page, app_config)
    page = hb_login_page.page

    HBLeadManagementPage(page, filters.timeout).open_leads(lead_property)
    grid = HBLeadsGridPage(page, filters.timeout)
    grid.switch_view("Reservations")
    try:
        filters.open_first_lead_communication()
        options = filters.options_of("Tenant")
        card_spaces = {space for _, space in filters.cards() if space != "Tenant"}
        with allure.step("13482: the lead's space filter lists Tenant and its spaces"):
            assert card_spaces, "The lead's communications name no space"
            assert options[0] == "Tenant", options
            assert set(options[1:]) == card_spaces, (options, card_spaces)
        filters.close_lead_view()
    finally:
        grid.switch_view("Active Leads")
