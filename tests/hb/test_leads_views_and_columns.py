import allure

from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_leads_grid_page import HBLeadsGridPage

# Confirmed live 2026-09-14 (uat_storoutlet, Bellflower), in display order.
# The old Robot suite expected 10 columns (Lead Created, Name, Reservation
# Date, Reservation Expires, Email, Phone, Reserved Space Number, Lead Source,
# Category Interest, Lead Created By) - "Lead Source" and "Category Interest"
# no longer exist and the order has changed.
EXPECTED_RESERVATION_COLUMNS = [
    "Lead Created",
    "Reservation Date",
    "Last Follow Up Date",
    "Reservation Expires",
    "Lead Source, Channel and Medium",
    "Lead Platform",
    "Name",
    "Email",
    "Phone",
    "Reserved Space Number",
    "Space Interest Type",
    "Space Size",
    "Features and Amenities",
    "Lead Type",
    "Reservation Code",
    "Lead Created By",
    "Lead Status",
]


@allure.title("Leads offers a Reservations view with its default columns")
@allure.feature("HB Lead Management")
@allure.story("Rearrange columns on leads")
def test_reservations_view_and_default_columns(hb_login_page, app_config, test_data) -> None:
    # Old Robot Lead_Management/RearrangeLeadColumns 13561 (a Reservations
    # view is offered), 13960 (it can be viewed) and 13563 (its default
    # columns). Read-only - only the session's selected view changes, and it
    # is put back to Active Leads.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    property_name = test_data("retire_lead")["property_name"]
    page = hb_login_page.page

    HBLeadManagementPage(page, timeout).open_leads(property_name)
    grid = HBLeadsGridPage(page, timeout)

    with allure.step("The view picker offers Active Leads and Reservations"):
        options = grid.view_options()
        assert {"Active Leads", "Reservations"} <= set(options), f"View options: {options}"

    grid.switch_view("Reservations")
    grid.assert_columns(EXPECTED_RESERVATION_COLUMNS)

    grid.switch_view("Active Leads")
