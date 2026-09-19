import logging
import re
import time
from datetime import date

import allure
from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


class HBLeadManagementPage:
    """HB Leads page: the Active Leads (retire) and Reservations (cancel)
    views share the same grid/drawer, switched via the page's own view
    dropdown - see HBMoveOutPage for the analogous Tenants sweep this
    mirrors."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def _close_live_agent_notification(self) -> None:
        live_agent_notification = self.page.get_by_text(
            "Need to talk to a live agent?", exact=True
        )
        # Scoped to the banner's own tooltip: an unscoped ".mdi-close" .first
        # can be an open drawer's or dialog's own close X (confirmed live
        # 2026-09-13 - it closed the move-out drawer, see HBMoveOutPage).
        close_notification = (
            self.page.locator(".v-tooltip__content.custom-tooltip-popup")
            .filter(has_text="Need to talk to a live agent?")
            .locator(".mdi-close")
        )
        if live_agent_notification.count() > 0 and live_agent_notification.first.is_visible():
            if close_notification.count() > 0 and close_notification.first.is_visible():
                try:
                    close_notification.first.click(timeout=waits().short)
                except PlaywrightTimeoutError:
                    pass

    @log_method_exceptions
    def open_leads(self, property_name: str) -> None:
        with allure.step(f"Open leads for {property_name}"):
            # Same Settings-overlay issue as HBTenantSpacesPage.open_tenants.
            from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage

            HBTenantSpacesPage(
                self.page, self.timeout
            )._ensure_main_shell_for_property_nav()
            self._close_live_agent_notification()
            search_box = self.page.locator("#search-box")
            expect(search_box).to_be_visible(timeout=self.timeout)
            search_box.click()
            property_cell = self.page.get_by_role(
                "cell", name=property_name, exact=True
            )
            # Same as HBMoveOutPage.open_tenants: the picker's default list
            # isn't guaranteed to already show the target property, so type
            # the name to filter down to it explicitly instead of hoping.
            try:
                expect(property_cell).to_be_visible(timeout=waits().short)
            except AssertionError:
                # #search-box is a wrapper <div> (stage's multi-property
                # picker: "facility-search-multiple-properties"), not the
                # input itself - same as HBTenantSpacesPage.open_tenants.
                search_box.locator("input").fill(property_name)
                expect(property_cell).to_be_visible(timeout=self.timeout)
            property_cell.click()
            # Confirmed live (2026-09-11, stage): with several properties
            # under the company, the picker ignores a click on the cell -
            # only a click event on its row selects it (a single-property
            # account like uat_storoutlet's selects on the cell click). The
            # row click is only sent if the picker is still open.
            try:
                expect(property_cell).to_be_hidden(timeout=waits().short)
            except AssertionError:
                property_cell.locator("xpath=ancestor::tr[1]").dispatch_event(
                    "click"
                )
            # Wait until the dashboard header names the property - see
            # HBTenantSpacesPage.open_tenants (a run went on company-wide).
            expect(
                self.page.get_by_role("textbox", name=property_name)
            ).to_be_visible(timeout=self.timeout)
            leads_link = self.page.get_by_role("complementary").get_by_text(
                "Leads", exact=True
            )
            expect(leads_link).to_be_visible(timeout=self.timeout)
            leads_link.locator(
                "xpath=ancestor::*[@role='listitem'][1]"
            ).dispatch_event("click")
            self._close_live_agent_notification()
            # The row/drawer accordion expansion is CSS-transition driven;
            # disabling transitions keeps a click from landing mid-transition
            # (same approach as HBMoveOutPage.filter_move_in_date).
            self.page.add_style_tag(
                content="*, *::before, *::after { transition: none !important; animation: none !important; }"
            )

    @log_method_exceptions
    def open_lead_and_start_move_in(self, first_name: str, last_name: str) -> None:
        # Old Robot suite's "Search Given Lead And Open Details" + "Reserve
        # Or Move-in". Confirmed live (2026-09-11, uat_storoutlet): the
        # drawer no longer has that suite's "Reserve Or Move-In" toolbar
        # button - a lead holding a reservation instead shows a
        # "Reservation for #<space>" card whose "Manage Reservation" opens
        # Lead Follow-Up, and that panel's bottom-bar "Move In" goes
        # straight to the same Lease step HBQuickLaunchPage.
        # move_in_first_available_space lands on (the suite's intermediate
        # "Check Rental Details And Movein" lease-period/bill-day screen
        # no longer exists).
        full_name = f"{first_name} {last_name}"
        with allure.step(f"Open lead details for {full_name}"):
            self._close_live_agent_notification()
            search_leads = self.page.get_by_role(
                "textbox", name="Search Leads", exact=True
            )
            expect(search_leads).to_be_visible(timeout=self.timeout)
            search_leads.fill(full_name)
            self.page.keyboard.press("Enter")
            # Same grid as HBQuickLaunchPage.assert_reservation_active: rows
            # carry a fixed aria-label, so the lead is matched by its own
            # name gridcell rather than the row.
            name_cell = self.page.get_by_role(
                "gridcell", name=full_name, exact=True
            )
            expect(name_cell).to_be_visible(timeout=self.timeout)
            name_cell.click()

        with allure.step("Reserve or move in"):
            manage_reservation = self.page.get_by_role(
                "button", name="Manage Reservation", exact=True
            )
            # Confirmed live (2026-09-11, stage): a move-in that was started
            # but abandoned (the drawer's "Incomplete Lease Set Up" prompt ->
            # "Save as Pending", which a page reload mid-lease also leaves
            # behind) turns the card into "Pending for #<space>" with a
            # "Finish Move-in" button instead - that one skips Lead Follow-
            # Up and opens the Lease step directly (address/license fields
            # blank again, so the same fill-in still applies).
            finish_move_in = self.page.get_by_role(
                "button", name="Finish Move-in", exact=True
            )
            expect(manage_reservation.or_(finish_move_in)).to_be_visible(
                timeout=self.timeout
            )
            if finish_move_in.count() > 0 and finish_move_in.is_visible():
                start_button = finish_move_in
            else:
                manage_reservation.click()
                start_button = self.page.get_by_role(
                    "button", name="Move In", exact=True
                )
                expect(start_button).to_be_visible(timeout=self.timeout)
            # Same distinctive Lease-step heading move_in_first_available_
            # space waits on, so callers never race the form's render.
            date_of_birth = self.page.get_by_text("Date of Birth", exact=True)
            # Confirmed live (2026-09-11, uat_storoutlet/Bellflower): a click
            # on "Move In" landed while Lead Follow-Up was still rendering
            # (its call timer had just started at 00:01) was silently
            # ignored - the drawer stayed on the Lead step with the button
            # still there. Retry the click, but only while the button is
            # still showing, so a slow-but-successful first click isn't
            # followed by a stray second one.
            for attempt in range(3):
                if start_button.count() > 0 and start_button.is_visible():
                    start_button.click()
                try:
                    expect(date_of_birth).to_be_visible(
                        timeout=self.timeout if attempt == 2 else 20000
                    )
                    break
                except AssertionError:
                    if attempt == 2:
                        raise

    @log_method_exceptions
    def assert_web_reservation_lead(
        self,
        email: str,
        reservation_code: str,
        reservation_date: date,
        business_name: str | None = None,
    ) -> None:
        """Old Robot suite's 8881 "Verify the reservation is showing as lead
        in HB PMS" + "Verify reservation date in website and in HB PMS".
        Confirmed live (2026-09-13, uat_storoutlet/Chula Vista): a storefront
        reservation lands as an Active lead whose row carries Lead Type "New
        Web Reservation", the Reserved Space Number, Reservation Date (= the
        storefront move-in date), Reservation Expires and Reservation Code,
        and whose drawer shows a "Reservation for #<space>" card with
        "Probable Move-In" on that same date. Checked as row/drawer text,
        not per column - the grid's cell order doesn't follow its header
        order. Searched by email since every storefront guest shares the
        name "Auto Tester". Read-only: "Manage Reservation" (Lead Follow-Up)
        isn't opened - that starts the lead's follow-up call timer."""
        # HB renders "Sep 14, 2026"; single-digit days weren't seen live, so
        # a zero-padded "Sep 04" (the Robot suite's %d format) passes too.
        date_pattern = (
            rf"{reservation_date:%b} 0?{reservation_date.day}, {reservation_date.year}"
        )
        with allure.step(f"Find the web reservation lead: {email}"):
            self._close_live_agent_notification()
            search_leads = self.page.get_by_role(
                "textbox", name="Search Leads", exact=True
            )
            expect(search_leads).to_be_visible(timeout=self.timeout)
            search_leads.fill(email)
            self.page.keyboard.press("Enter")
            row = self.page.get_by_role("row").filter(has_text=email).first
            expect(row).to_be_visible(timeout=self.timeout)

        with allure.step(
            f"Verify lead row shows reservation {reservation_code} for {reservation_date:%b %d, %Y}"
        ):
            expect(row).to_contain_text("New Web Reservation")
            expect(row).to_contain_text(reservation_code)
            expect(row).to_contain_text(re.compile(date_pattern))
            if business_name:
                expect(row).to_contain_text(business_name)

        with allure.step("Verify lead drawer shows the reservation card and move-in date"):
            if not self._open_row_overview(row):
                raise AssertionError(f"Lead drawer didn't open for {email}")
            expect(
                self.page.get_by_text(re.compile(r"Reservation for #\S+")).first
            ).to_be_visible(timeout=self.timeout)
            expect(self.page.locator("body")).to_contain_text(
                re.compile(rf"Probable Move-In\s*{date_pattern}")
            )

    @log_method_exceptions
    def open_reservation_follow_up(self, email: str, space_number: str) -> None:
        """Opens Lead Follow-Up from this lead's drawer: the "Reservation
        for #<space>" card's "Manage Reservation" (same panel Task Center's
        "First Follow Up" opens - see open_lead_and_start_move_in). Used
        instead of Task Center (user choice 2026-09-13): stage's lists
        ~12,000 due-today tasks, 20 per page, oldest first. Searched by
        email since every storefront guest shares the name "Auto Tester".
        Starts the lead's follow-up call timer; nothing is logged or saved
        here - read and close it with HBLeadFollowUpPage."""
        with allure.step(f"Open lead follow-up via manage reservation: {email}, space {space_number}"):
            self._close_live_agent_notification()
            search_leads = self.page.get_by_role(
                "textbox", name="Search Leads", exact=True
            )
            expect(search_leads).to_be_visible(timeout=self.timeout)
            search_leads.fill(email)
            self.page.keyboard.press("Enter")
            row = self.page.get_by_role("row").filter(has_text=email).first
            expect(row).to_be_visible(timeout=self.timeout)
            if not self._open_row_overview(row):
                raise AssertionError(f"Lead drawer didn't open for {email}")
            expect(
                self.page.get_by_text(
                    re.compile(rf"Reservation for #{re.escape(space_number)}\b")
                ).first
            ).to_be_visible(timeout=self.timeout)
            self.page.get_by_role("button", name="Manage Reservation", exact=True).first.click()
            expect(
                self.page.get_by_text(re.compile(r"Move-In Cost:")).first
            ).to_be_visible(timeout=self.timeout)
            # Guard against having opened some other lead's Follow-Up.
            expect(
                self.page.get_by_text(f"Space #{space_number}", exact=False).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def cancel_reservation_for_lead(self, email: str, reason: str) -> None:
        """The migrated form of the old Robot Mariposa ReservationAndRentals
        suite's "Retire a Lead From HummingBird": confirmed live
        (2026-09-13, uat_storoutlet/Chula Vista, CHFT23) that a lead holding
        a storefront reservation offers no "Retire Lead" - neither its drawer
        nor its Lead Follow-Up - only "Cancel Reservation" (user choice:
        migrate as that). Same steps as _process_reservation_row. Searched
        by email since every storefront guest shares the name "Auto Tester"."""
        with allure.step(f"Cancel the reservation on lead {email}"):
            self._close_live_agent_notification()
            search_leads = self.page.get_by_role("textbox", name="Search Leads", exact=True)
            expect(search_leads).to_be_visible(timeout=self.timeout)
            search_leads.fill(email)
            self.page.keyboard.press("Enter")
            row = self.page.get_by_role("row").filter(has_text=email).first
            expect(row).to_be_visible(timeout=self.timeout)
            if not self._open_row_overview(row):
                raise AssertionError(f"Lead drawer didn't open for {email}")
            cancel_link = self.page.get_by_text("Cancel Reservation", exact=True).first
            expect(cancel_link).to_be_visible(timeout=self.timeout)
            cancel_link.click()
            notes_field = self.page.get_by_role(
                "textbox", name="Why are you cancelling this reservation?", exact=True
            )
            expect(notes_field).to_be_visible(timeout=self.timeout)
            notes_field.fill(reason)
            self.page.get_by_role("button", name="Cancel Reservation", exact=True).click()
            if not self._wait_for_confirm_outcome("Successfully cancelled reservation"):
                raise AssertionError(f"HB didn't confirm cancelling the reservation for {email}")

    @log_method_exceptions
    def assert_reservation_lead_offers_cancel_only(self, email: str) -> None:
        # Old Robot RetireLead 16895 expected "Retire Lead" on a reservation
        # lead to also cancel its reservation. Confirmed live 2026-09-13
        # (Bellflower): such a lead now offers "Cancel Reservation" and
        # "Manage Reservation" instead - no "Retire Lead" at all.
        with allure.step(f"Verify reservation lead {email} offers cancel reservation, not retire lead"):
            self.open_active_lead(email)
            expect(
                self.page.get_by_text("Cancel Reservation", exact=True).first
            ).to_be_visible(timeout=self.timeout)
            expect(
                self.page.get_by_text("Manage Reservation", exact=True).first
            ).to_be_visible(timeout=self.timeout)
            # Only visible matches count - the DOM can keep hidden copies.
            retire_links = self.page.get_by_text("Retire Lead", exact=True)
            visible_retire_links = [
                index for index in range(retire_links.count())
                if retire_links.nth(index).is_visible()
            ]
            assert not visible_retire_links, (
                f"Reservation lead {email} unexpectedly offers Retire Lead"
            )
            # Close the drawer so cancel_reservation_for_lead opens it afresh.
            close_button = self.page.locator('button[name="QA-HbHeader-HbIcon-mdi-close"]')
            if close_button.count() > 0 and close_button.first.is_visible():
                close_button.first.click()

    @log_method_exceptions
    def assert_lead_not_active(self, email: str) -> None:
        with allure.step(f"Verify lead {email} is no longer in active leads"):
            # Already the default view (confirmed live 2026-09-13) - only
            # switch when it isn't, so a still-open lead drawer can't sit
            # over the view selector.
            view_selector = self.page.get_by_role("textbox", name="Select", exact=True)
            if view_selector.input_value() != "Active Leads":
                self._select_view("Active Leads")
            search_leads = self.page.get_by_role("textbox", name="Search Leads", exact=True)
            search_leads.fill(email)
            self.page.keyboard.press("Enter")
            self._wait_for_grid_loading_to_finish()
            expect(self.page.get_by_role("row").filter(has_text=email)).to_have_count(
                0, timeout=self.timeout
            )

    @log_method_exceptions
    def open_active_lead(self, email: str) -> None:
        with allure.step(f"Open active lead {email}"):
            view_selector = self.page.get_by_role("textbox", name="Select", exact=True)
            expect(view_selector).to_be_visible(timeout=self.timeout)
            if view_selector.input_value() != "Active Leads":
                self._select_view("Active Leads")
            search_leads = self.page.get_by_role("textbox", name="Search Leads", exact=True)
            search_leads.fill(email)
            self.page.keyboard.press("Enter")
            self._wait_for_grid_loading_to_finish()
            row = self.page.get_by_role("row").filter(has_text=email).first
            expect(row).to_be_visible(timeout=self.timeout)
            if not self._open_row_overview(row):
                raise AssertionError(f"Lead {email}'s drawer never showed its Overview tab")

    @log_method_exceptions
    def _retire_notes_field(self) -> Locator:
        # By name attribute, not the "Why are you retiring this lead?" label:
        # confirmed live 2026-09-13 that HB removes that <label> as soon as
        # the notes hold text, so a role/name match stops resolving right
        # after fill() - and the confirm click anchored on it timed out.
        return self.page.locator('textarea[name="retire_reason"]')

    @log_method_exceptions
    def _retire_form(self) -> Locator:
        return self._retire_notes_field().locator(
            "xpath=ancestor::*[.//button[normalize-space(.)='Retire Lead']][1]"
        )

    @log_method_exceptions
    def open_retire_form(self) -> None:
        # Old Robot RetireLead 16890/16891, confirmed live 2026-09-13
        # (Bellflower): the lead drawer's Overview tab has a "Retire Lead"
        # link opening an inline form (not a dialog) - Reason picker, Opt-Out
        # checkbox, "Notes for Retiring Lead*" and a Retire Lead button.
        with allure.step("Retire lead: open the form"):
            retire_link = self.page.get_by_text("Retire Lead", exact=True).first
            expect(retire_link).to_be_visible(timeout=self.timeout)
            retire_link.click()
            expect(self._retire_notes_field()).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_retire_form_fields(self) -> None:
        with allure.step("Verify retire lead form shows reason, opt-out and notes"):
            form = self._retire_form()
            for text in (
                "Reason",
                "Opt-Out",
                "Remove tenant from all future communication.",
                "Notes for Retiring Lead",
            ):
                expect(form).to_contain_text(text, timeout=self.timeout)
            expect(form.locator("#lead_reason")).to_be_attached()
            # Opting out stops all future communication with the contact -
            # it must start unticked.
            expect(form.get_by_role("checkbox")).not_to_be_checked()

    @log_method_exceptions
    def _open_reason_menu(self) -> Locator:
        # The Reason picker (input#lead_reason) isn't a role=combobox and its
        # items aren't role=option (confirmed live 2026-09-13): open it via
        # its v-select__slot and use the active menu's list items.
        self._retire_form().locator("#lead_reason").locator(
            "xpath=ancestor::*[contains(@class,'v-select__slot')][1]"
        ).click()
        items = self.page.locator(
            ".v-menu__content.menuable__content__active .v-list-item"
        )
        expect(items.first).to_be_visible(timeout=self.timeout)
        return items

    @log_method_exceptions
    def read_retire_reasons(self) -> list[str]:
        with allure.step("Retire lead: read the reasons"):
            items = self._open_reason_menu()
            reasons = [text.strip() for text in items.all_inner_texts()]
            self.page.keyboard.press("Escape")
            expect(items.first).to_be_hidden(timeout=self.timeout)
            return reasons

    @log_method_exceptions
    def assert_retire_needs_notes(self) -> None:
        # Old Robot 16894, confirmed live 2026-09-13: Retire Lead with empty
        # notes is refused with "There are errors in your form, correct them
        # before continuing. The Notes field is required" and the form stays
        # open (Robot's wording was "The retire reason field is required").
        with allure.step("Verify retire lead without notes is refused"):
            notes_field = self._retire_notes_field()
            expect(notes_field).to_have_value("")
            self._retire_form().get_by_role(
                "button", name="Retire Lead", exact=True
            ).click()
            expect(
                self.page.get_by_text(re.compile(r"There are errors in your form")).first
            ).to_be_visible(timeout=self.timeout)
            expect(
                self.page.get_by_text(re.compile(r"The Notes field is required")).first
            ).to_be_visible(timeout=self.timeout)
            expect(notes_field).to_be_visible()
            expect(
                self.page.get_by_text("Lead retired successfully", exact=True)
            ).to_have_count(0)

    @log_method_exceptions
    def retire_open_lead(self, reason: str, notes: str) -> None:
        with allure.step(f"Retire lead with reason: {reason}"):
            items = self._open_reason_menu()
            reason_item = items.filter(
                has_text=re.compile(rf"^\s*{re.escape(reason)}\s*$")
            )
            expect(reason_item).to_be_visible(timeout=self.timeout)
            reason_item.click()
            expect(
                self._retire_form().locator(".v-select__selections")
            ).to_contain_text(reason, timeout=self.timeout)
            self._retire_notes_field().fill(notes)
            self._retire_form().get_by_role(
                "button", name="Retire Lead", exact=True
            ).click()
            if not self._wait_for_confirm_outcome("Lead retired successfully"):
                raise AssertionError(
                    "HB refused to retire the lead (reported it as already converted)"
                )

    @log_method_exceptions
    def _select_view(self, view_name: str) -> None:
        with allure.step(f"Switch leads view to: {view_name}"):
            # The combobox div's own text is just the dropdown-arrow icon
            # ligature - the selected view name is the nested input's value
            # instead, exposed as this "Select"-named textbox.
            view_selector = self.page.get_by_role(
                "textbox", name="Select", exact=True
            )
            expect(view_selector).to_be_visible(timeout=self.timeout)
            # This Vuetify select can silently no-op a click landed mid
            # open/close animation, leaving the grid on the previous view -
            # verify the switch actually took and retry if it didn't, same
            # spirit as HBMoveOutPage's retries around its own pickers.
            for attempt in range(3):
                view_selector.click()
                option = self.page.get_by_role("option", name=view_name, exact=True)
                expect(option).to_be_visible(timeout=self.timeout)
                option.click()
                try:
                    expect(view_selector).to_have_value(view_name, timeout=waits().short)
                    return
                except AssertionError:
                    if attempt == 2:
                        raise

    @log_method_exceptions
    def _open_row_overview(self, row: Locator) -> bool:
        self._close_live_agent_notification()
        row.locator("[role='gridcell']").first.click()
        # The drawer can land on a tab other than Overview - the retire/
        # cancel actions only render once Overview is the active tab.
        overview_tab = self.page.get_by_role("tab", name="Overview", exact=True)
        try:
            expect(overview_tab).to_be_visible(timeout=waits().medium)
        except (PlaywrightTimeoutError, AssertionError):
            return False
        overview_tab.click()
        return True

    @log_method_exceptions
    def _wait_for_grid_loading_to_finish(self) -> None:
        # Same ag-grid virtual row model as HBMoveOutPage: several "Loading"
        # placeholders can render at once for pending rows, so a single-
        # match to_be_hidden() assertion isn't usable here. A confirm that
        # refreshes the grid in place needs this settle before the next
        # row is indexed, or the next click can land on a row mid-transition.
        loading_row = self.page.get_by_text("Loading", exact=True)
        deadline = time.monotonic() + self.timeout / 1000
        while time.monotonic() < deadline and loading_row.count() > 0:
            self.page.wait_for_timeout(waits().poll_interval)

    @log_method_exceptions
    def _wait_for_confirm_outcome(self, success_text: str) -> bool:
        # Some leads have already been converted (moved into an actual
        # tenancy) and the application refuses to retire/cancel them,
        # surfacing a transient "already ... converted" warning toast
        # instead of the success one. That's a legitimate application
        # response, not a broken interaction, so it's treated as a normal
        # skip (like every other known-issue row) rather than a crash.
        success_toast = self.page.get_by_text(success_text, exact=True)
        already_converted_warning = self.page.get_by_text(
            re.compile(r"already.*convert", re.IGNORECASE)
        )
        deadline = time.monotonic() + self.timeout / 1000
        while time.monotonic() < deadline:
            if success_toast.count() > 0 and success_toast.first.is_visible():
                return True
            if (
                already_converted_warning.count() > 0
                and already_converted_warning.first.is_visible()
            ):
                return False
            self.page.wait_for_timeout(waits().poll_interval)
        raise AssertionError(
            f"Neither {success_text!r} nor an 'already converted' warning "
            "appeared after confirming"
        )

    @log_method_exceptions
    def _find_next_processable_row(
        self, rows: Locator, known_issue_keys: set[str]
    ) -> tuple[Locator, str] | None:
        # Identifies rows by their Lead Created cell (gridcell 1), which is
        # timestamped to the minute and so unique per entry - same role as
        # HBMoveOutPage._find_next_movable_row's space_number.
        for index in range(rows.count()):
            row = rows.nth(index)
            key = row.locator("[role='gridcell']").nth(1).inner_text().strip()
            if key not in known_issue_keys:
                return row, key
        return None

    @log_method_exceptions
    def _retire_all_leads_in_drawer(self, trigger_button: Locator, notes: str) -> bool:
        # Only present when the opened person has 2+ active leads/
        # reservations - retires every one of them in a single confirm
        # instead of looping per entry.
        with allure.step("Retire all leads: select every active lead"):
            trigger_button.click()
            # Same as _select_view: the combobox div itself has no
            # accessible name - "Select leads" is the nested textbox's.
            select_leads = self.page.get_by_role(
                "textbox", name="Select leads", exact=True
            )
            expect(select_leads).to_be_visible(timeout=self.timeout)
            select_leads.click()
            select_all = self.page.get_by_role(
                "menuitem", name="Select All", exact=True
            )
            expect(select_all).to_be_visible(timeout=self.timeout)
            select_all.click()
            # Clicking a neutral label closes the open dropdown so the
            # Notes field beneath it becomes reachable.
            self.page.get_by_text("Reason", exact=True).click()

        with allure.step("Retire all leads: confirm with reason"):
            notes_field = self.page.get_by_role(
                "textbox", name="Why are you retiring these leads?", exact=True
            )
            expect(notes_field).to_be_visible(timeout=self.timeout)
            notes_field.fill(notes)
            # The entry's original "Retire All Leads" trigger can still be
            # present in the DOM alongside the now-open form's own button
            # of the same name - the form's is the one appearing after the
            # Notes field, i.e. last in DOM order.
            self.page.get_by_role(
                "button", name="Retire All Leads", exact=True
            ).last.click()
            return self._wait_for_confirm_outcome("Leads retired successfully")

    @log_method_exceptions
    def _retire_single_lead(self, action_link: Locator, notes: str) -> bool:
        action_link.click()
        notes_field = self.page.get_by_role(
            "textbox", name="Why are you retiring this lead?", exact=True
        )
        try:
            expect(notes_field).to_be_visible(timeout=waits().medium)
        except (PlaywrightTimeoutError, AssertionError):
            return False

        with allure.step("Retire lead: confirm with reason"):
            notes_field.fill(notes)
            self.page.get_by_role("button", name="Retire Lead", exact=True).click()
            return self._wait_for_confirm_outcome("Lead retired successfully")

    @log_method_exceptions
    def _process_active_lead_row(self, row: Locator, notes: str) -> bool:
        if not self._open_row_overview(row):
            return False

        # Prefer the bulk action when this person has multiple active
        # leads/reservations; it only renders in that case, so fall back to
        # the single-entry link otherwise. Only the existence check is
        # guarded here - once the bulk button is confirmed present, a
        # failure partway through actually retiring must propagate as a
        # real failure, not get silently swallowed into the single-entry
        # fallback (which would find nothing, since the bulk form is
        # already open, and the row would wrongly end up marked "no action
        # available" instead of "the retire itself broke").
        retire_all_button = self.page.get_by_role(
            "button", name="Retire All Leads", exact=True
        ).first
        try:
            expect(retire_all_button).to_be_visible(timeout=waits().short)
            has_bulk_action = True
        except (PlaywrightTimeoutError, AssertionError):
            has_bulk_action = False

        if has_bulk_action:
            return self._retire_all_leads_in_drawer(retire_all_button, notes)

        # A lead holding a reservation offers only "Cancel Reservation" /
        # "Manage Reservation" here, no "Retire Lead" (confirmed live
        # 2026-09-13 on Bellflower and Chula Vista), so such rows fall
        # through to the not-found skip below.
        retire_link = self.page.get_by_text("Retire Lead", exact=True).first
        try:
            expect(retire_link).to_be_visible(timeout=waits().medium)
        except (PlaywrightTimeoutError, AssertionError):
            return False
        return self._retire_single_lead(retire_link, notes)

    @log_method_exceptions
    def _process_reservation_row(self, row: Locator, notes: str) -> bool:
        if not self._open_row_overview(row):
            return False

        cancel_link = self.page.get_by_text("Cancel Reservation", exact=True).first
        try:
            expect(cancel_link).to_be_visible(timeout=waits().medium)
        except (PlaywrightTimeoutError, AssertionError):
            return False
        cancel_link.click()

        notes_field = self.page.get_by_role(
            "textbox", name="Why are you cancelling this reservation?", exact=True
        )
        try:
            expect(notes_field).to_be_visible(timeout=waits().medium)
        except (PlaywrightTimeoutError, AssertionError):
            return False

        with allure.step("Cancel reservation: confirm with reason"):
            notes_field.fill(notes)
            self.page.get_by_role(
                "button", name="Cancel Reservation", exact=True
            ).click()
            return self._wait_for_confirm_outcome(
                "Successfully cancelled reservation"
            )

    @log_method_exceptions
    def _sweep(self, property_name: str, view_name: str, process_row, label: str) -> int:
        rows = self.page.locator(".ag-center-cols-viewport [role='row']")
        processed_count = 0
        known_issue_keys: set[str] = set()

        self.open_leads(property_name)
        self._select_view(view_name)

        while True:
            try:
                expect(rows.first).to_be_visible(timeout=waits().short)
            except (PlaywrightTimeoutError, AssertionError):
                break

            next_row = self._find_next_processable_row(rows, known_issue_keys)
            if next_row is None:
                logging.warning(
                    "Stopping %s sweep: every remaining row (%s) hit a "
                    "known application issue and could not be processed",
                    label,
                    ", ".join(sorted(known_issue_keys)),
                )
                break

            row, key = next_row
            if process_row(row):
                # A successful retire/cancel refreshes the grid in place on
                # the same view - no need to re-navigate for the next row,
                # but the next row must not be indexed until that refresh
                # actually settles.
                processed_count += 1
                self._wait_for_grid_loading_to_finish()
            else:
                known_issue_keys.add(key)
                # Whatever left this row unprocessable may have left stray
                # UI state behind - reopen for a clean state before the
                # next attempt, same recovery HBMoveOutPage uses for its
                # own picker stalls.
                self.open_leads(property_name)
                self._select_view(view_name)

        if known_issue_keys:
            allure.attach(
                f"Could not process these rows (identified by their Lead "
                f"Created timestamp) after opening them - see the warning "
                f"logged for each: {', '.join(sorted(known_issue_keys))}",
                name=f"Known-issue {label} skips",
                attachment_type=allure.attachment_type.TEXT,
            )
        return processed_count

    @log_method_exceptions
    def retire_all_active_leads(self, property_name: str, notes: str) -> int:
        retired_count = self._sweep(
            property_name,
            "Active Leads",
            lambda row: self._process_active_lead_row(row, notes),
            "retire-lead",
        )
        if retired_count == 0:
            logging.info("No active leads to retire")
        return retired_count

    @log_method_exceptions
    def cancel_all_reservations(self, property_name: str, notes: str) -> int:
        cancelled_count = self._sweep(
            property_name,
            "Reservations",
            lambda row: self._process_reservation_row(row, notes),
            "cancel-reservation",
        )
        if cancelled_count == 0:
            logging.info("No reservations to cancel")
        return cancelled_count
