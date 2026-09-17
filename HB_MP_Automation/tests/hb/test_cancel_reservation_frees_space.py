import allure

from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_reports_page import HBReportsPage
from pages.common.hb_spaces_page import HBSpacesPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

CANCEL_NOTES = "QA automation test - cancel reservation"


@allure.title("A reservation lead offers Cancel Reservation, and cancelling frees its space")
@allure.feature("HB Lead Management")
@allure.story("Ability to retire a lead")
def test_cancel_reservation_frees_space(
    hb_login_page, app_config, test_data, hb_lead_guest
) -> None:
    # Replaces old Robot RetireLead 16895 ("if the lead is a reservation lead,
    # retire lead should also cancel the reservation"). Confirmed live
    # 2026-09-13 (Bellflower) that a reservation lead no longer offers Retire
    # Lead at all - user choice: check that it offers Cancel Reservation
    # instead, cancel, and confirm the space goes Reserved -> Available, as
    # the Robot case did.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    reservation_data = test_data("quick_launch_reservation")
    property_name = reservation_data["property_name"]
    page = hb_login_page.page

    with allure.step("Reserve a space for a new lead"):
        quick_launch = HBQuickLaunchPage(page, timeout)
        quick_launch.open_quick_launch_for_property(property_name)
        quick_launch.start_new_contact(hb_lead_guest["email"])
        quick_launch.fill_lead_details(
            hb_lead_guest["first_name"],
            hb_lead_guest["last_name"],
            hb_lead_guest["email"],
            hb_lead_guest["phone_number"],
            reservation_data["lead_initiated"],
            reservation_data["lead_source"],
        )
        # The picked row's first cell also carries the space size on a
        # second line ("#0040\n8' x 8'") - keep just the number.
        space_number = (
            quick_launch.reserve_first_available_space(exclude_number_prefixes=("pa",))
            .splitlines()[0]
            .strip()
            .lstrip("#")
        )
        quick_launch.assert_reservation_active(
            hb_lead_guest["first_name"], hb_lead_guest["last_name"]
        )

    spaces = HBSpacesPage(page, timeout)
    spaces.open_spaces()
    spaces.assert_space_status(space_number, "Reserved")

    leads = HBLeadManagementPage(page, timeout)
    leads.open_leads(property_name)
    leads.assert_reservation_lead_offers_cancel_only(hb_lead_guest["email"])
    leads.cancel_reservation_for_lead(hb_lead_guest["email"], CANCEL_NOTES)
    leads.assert_lead_not_active(hb_lead_guest["email"])

    spaces.open_spaces()
    spaces.assert_space_status(space_number, "Available")

    # The other side of RetireLead 16899's rule (user choice): cancelling a
    # reservation retires the lead as "No Longer Required" (confirmed live
    # 2026-09-13), and such a lead stays in Lead Activity as "retired" - only
    # a "Not A Lead" retire is left out (test_retire_lead_form).
    reports = HBReportsPage(page, timeout)
    reports.open_reports_library()
    reports.run_report("Occupancy Reports", "Retired Leads")
    retired = reports.find_row(hb_lead_guest["email"])
    with allure.step("Retired Leads records the cancel as No Longer Required"):
        assert retired.get("lead_retire_reason") == "No Longer Required", retired
        assert retired.get("lead_retire_notes") == CANCEL_NOTES, retired

    reports.open_reports_library()
    reports.run_report("Occupancy Reports", "Lead Activity - Created Date")
    activity = reports.find_row(hb_lead_guest["email"])
    with allure.step("Lead Activity still lists the lead as retired"):
        assert (activity.get("lead_status") or "").lower() == "retired", activity
