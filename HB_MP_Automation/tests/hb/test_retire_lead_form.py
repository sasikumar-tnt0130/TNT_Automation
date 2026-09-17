import allure

from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_reports_page import HBReportsPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

# Confirmed live 2026-09-13 (uat_storoutlet, Bellflower), in the picker's
# order. The old Robot suite expected "Can't afford storage / Not Interested /
# Not a lead" first - "Not Interested" no longer exists.
EXPECTED_RETIRE_REASONS = [
    "Can't Afford Storage",
    "No Longer Required",
    "Not A Lead",
    "Stored Elsewhere For Free",
    "Stored With Competitor",
    "Stored With Another Property of the Company",
    "Space/Amenities Did Not Meet Requirements",
    "Pricing Not Within Budget",
    "Unspecified",
]


@allure.title("A lead's Retire form shows its options, requires notes, and retires the lead")
@allure.feature("HB Lead Management")
@allure.story("Ability to retire a lead")
def test_retire_lead_form(hb_login_page, app_config, test_data, hb_lead_guest) -> None:
    # Old Robot Lead_Management/RetireLead cases 16890-16894 and 16899 on one
    # lead this test creates itself (Quick Launch "Save Lead"), then really
    # retired as "Not A Lead" - the positive path, which also cleans the lead up.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    retire_data = test_data("retire_lead")
    lease_data = test_data("quick_launch_lease")
    property_name = retire_data["property_name"]
    page = hb_login_page.page

    with allure.step("Create the lead with Save Lead"):
        quick_launch = HBQuickLaunchPage(page, timeout)
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
        quick_launch.save_lead()

    leads = HBLeadManagementPage(page, timeout)
    leads.open_leads(property_name)
    leads.open_active_lead(hb_lead_guest["email"])

    # 16890 + 16891: Retire Lead is offered, and its form shows Reason,
    # Opt-Out and the notes field.
    leads.open_retire_form()
    leads.assert_retire_form_fields()

    # 16892 + 16893: the Reason picker lists today's reasons, in order.
    with allure.step("Retire reasons match the expected list"):
        reasons = leads.read_retire_reasons()
        assert reasons == EXPECTED_RETIRE_REASONS, f"Retire reasons changed: {reasons}"

    # 16894: retiring without notes is refused and the lead stays.
    leads.assert_retire_needs_notes()

    # Positive path: retire as "Not A Lead" and the lead leaves Active Leads.
    leads.retire_open_lead("Not A Lead", retire_data["notes"])
    leads.assert_lead_not_active(hb_lead_guest["email"])

    # 16899: a "Not A Lead" retire is recorded under Retired Leads with its
    # reason and note, and left out of lead reporting (Lead Activity - Created
    # Date). Confirmed live 2026-09-13 - leads retired for other reasons stay
    # listed there as "retired" (see test_cancel_reservation_frees_space).
    reports = HBReportsPage(page, timeout)
    reports.open_reports_library()
    reports.run_report("Occupancy Reports", "Retired Leads")
    retired = reports.find_row(hb_lead_guest["email"])
    with allure.step("Retired Leads records the reason and note"):
        assert retired.get("lead_retire_reason") == "Not A Lead", retired
        assert retired.get("lead_retire_notes") == retire_data["notes"], retired

    reports.open_reports_library()
    reports.run_report("Occupancy Reports", "Lead Activity - Created Date")
    with allure.step("Lead Activity leaves the 'Not A Lead' lead out"):
        listed = reports.listed_emails(hb_lead_guest["first_name"])
        assert hb_lead_guest["email"] not in listed, (
            f"{hb_lead_guest['email']} (retired as Not A Lead) is still in Lead Activity"
        )
