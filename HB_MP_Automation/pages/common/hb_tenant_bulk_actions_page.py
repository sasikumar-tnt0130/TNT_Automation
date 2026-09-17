import re

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions


class HBTenantBulkActionsPage:
    """Tenants list "Bulk Edit" actions: select several tenants and send them
    one email or SMS. Ported from the old Robot Framework smoke suite's
    "Email/Text multiple tenants" scenario - confirmed live (2026-09-11,
    uat_storoutlet/Bellflower) that the flow is now: the header's Bulk Edit
    icon -> the grid's select-all checkbox -> a "Bulk Actions (N Tenants)"
    panel -> "Send Email or SMS Communications" -> Send Email / Send SMS ->
    compose -> a "Confirm & Send to Recipients" review -> Confirm & Send.

    That review's "Confirm & Send" button carries the very same name
    attribute (QA-HbBottomActionBar-hb-primary-button-Next) as every "Next"
    before it, so this class always locates those buttons by their visible
    text - locating by name would let a "click Next" silently send the
    message.

    open_tenants is the same live-verified mechanics as
    HBTenantDocumentsPage's."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout
        self._search_term: str | None = None

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
                    close_notification.first.click(timeout=5000)
                except PlaywrightTimeoutError:
                    pass

    @log_method_exceptions
    def open_tenants(self, property_name: str) -> None:
        with allure.step(f"Open Tenants for {property_name}"):
            self._close_live_agent_notification()
            search_box = self.page.locator("#search-box")
            expect(search_box).to_be_visible(timeout=self.timeout)
            search_box.click()
            search_input = search_box.locator("input")
            property_cell = self.page.get_by_role(
                "cell", name=property_name, exact=True
            )
            try:
                expect(property_cell).to_be_visible(timeout=5000)
            except AssertionError:
                search_input.fill(property_name)
                expect(property_cell).to_be_visible(timeout=self.timeout)
            property_cell.click()
            # Same multi-property picker quirk as HBLeadManagementPage.
            # open_leads: only a click on the row selects it there.
            try:
                expect(property_cell).to_be_hidden(timeout=5000)
            except AssertionError:
                property_cell.locator("xpath=ancestor::tr[1]").dispatch_event(
                    "click"
                )
            # Wait until the dashboard header names the property - see
            # HBTenantSpacesPage.open_tenants (a run went on company-wide).
            expect(
                self.page.get_by_role("textbox", name=property_name)
            ).to_be_visible(timeout=self.timeout)
            tenants_link = self.page.get_by_role("complementary").get_by_text(
                "Tenants", exact=True
            )
            expect(tenants_link).to_be_visible(timeout=self.timeout)
            tenants_link.locator(
                "xpath=ancestor::*[@role='listitem'][1]"
            ).dispatch_event("click")
            self._close_live_agent_notification()

    @log_method_exceptions
    def search_tenants(self, search_term: str) -> None:
        with allure.step(f"Search For Tenant: {search_term}"):
            # Kept so select_all_tenants can confirm (and if need be
            # re-apply) the filter before selecting anyone to message.
            self._search_term = search_term
            self._apply_search(search_term)

    @log_method_exceptions
    def _apply_search(self, search_term: str) -> None:
        # Seen 2026-09-13 (Bellflower): the search, typed right after a
        # fresh Tenants load, was gone by the time tenants were selected -
        # select-all took the whole property (the Mailinator check refused
        # the send). One matching cell doesn't prove the filter applied:
        # unfiltered, the lowest space numbers are this suite's own
        # tenants. So re-type until the box keeps the term and every
        # rendered Tenant Name matches it (rows are virtualized - this only
        # sees the rendered ones; select_all_tenants' footer check is the
        # decisive one).
        search_tenants = self.page.get_by_role(
            "textbox", name="Search Tenants", exact=True
        )
        expect(search_tenants).to_be_visible(timeout=self.timeout)
        name_cells = self.page.locator(
            '.ag-center-cols-container .ag-cell[col-id="tenant_name"]'
        )
        for _ in range(3):
            search_tenants.fill(search_term)
            self.page.keyboard.press("Enter")
            expect(
                self.page.get_by_role(
                    "gridcell", name=re.compile(re.escape(search_term))
                ).first
            ).to_be_visible(timeout=self.timeout)
            self.page.wait_for_timeout(1500)
            names = name_cells.all_inner_texts()
            if (
                search_tenants.input_value() == search_term
                and names
                and all(search_term.lower() in name.lower() for name in names)
            ):
                return
        raise AssertionError(
            f"Tenant search for '{search_term}' didn't stick - box: "
            f"{search_tenants.input_value()!r}, rendered names: {names[:5]}"
        )

    @log_method_exceptions
    def _selected_count(self) -> int:
        # The grid footer's "Tenants: 6 of 57 Selected: 6" - its label and
        # number are separate elements, so read them from the page text.
        match = re.search(r"Selected:\s*(\d+)", self.page.locator("body").inner_text())
        return int(match.group(1)) if match else 0

    @log_method_exceptions
    def select_all_tenants(self) -> int:
        with allure.step("Select Bulk Edit And Select All"):
            self._close_live_agent_notification()
            bulk_edit = self.page.locator(
                'button[name="QA-HbHeader-HbIcon-mdi-square-edit-outline"]'
            )
            expect(bulk_edit).to_be_visible(timeout=self.timeout)
            if "hb-button-icon-active" not in (bulk_edit.get_attribute("class") or ""):
                bulk_edit.click()
            filtered_count = self._require_filtered_grid()
            # Clicking select-all again once tenants are selected would
            # deselect them - only click it while nothing is selected.
            if self._selected_count() == 0:
                # Confirmed live: the header select-all is a Vuetify checkbox
                # whose visible icon is overlaid by its own invisible input -
                # the input is what actually takes the click, but
                # Playwright's actionability check reports that overlap as
                # "intercepts pointer events", so the click is forced.
                select_all = self.page.locator(".ag-pinned-left-header i.v-icon").first
                expect(select_all).to_be_visible(timeout=self.timeout)
                select_all.click(force=True)
            # The panel only offers its actions once tenants are selected
            # (before that it just says "Please select the tenants...").
            # Waiting on this button rather than the "Bulk Actions (N
            # Tenants)" heading - confirmed live that the heading's text is
            # split across elements, so no text match on it ever resolves.
            expect(self._communications_button()).to_be_visible(
                timeout=self.timeout
            )
            selected = self._selected_count()
            if filtered_count is not None:
                for _ in range(10):
                    if selected == filtered_count:
                        break
                    self.page.wait_for_timeout(500)
                    selected = self._selected_count()
                else:
                    raise AssertionError(
                        f"Selected {selected} tenants, but the '{self._search_term}' "
                        f"search shows {filtered_count}"
                    )
            return selected

    @log_method_exceptions
    def _wait_for_footer(self, pattern: re.Pattern, seconds: int = 10) -> re.Match | None:
        for _ in range(seconds * 2):
            match = pattern.search(self.page.locator("body").inner_text())
            if match:
                return match
            self.page.wait_for_timeout(500)
        return None

    @log_method_exceptions
    def _require_filtered_grid(self) -> int | None:
        # The tenant count a search_tenants filter shows, or None if no
        # search was made. Confirmed live (2026-09-13, Bellflower): the grid
        # footer ("Tenants: 23 of 73 Selected: 0") only renders in bulk-edit
        # mode, and only reads "N of M" while a search filters the grid. A
        # lost search is re-applied once; if the grid still isn't filtered,
        # stop here - before anyone is selected or messaged - rather than
        # bulk-message every tenant on the property.
        if self._search_term is None:
            return None
        filtered_footer = re.compile(r"Tenants:\s*(\d+)\s*of\s*(\d+)")
        match = self._wait_for_footer(filtered_footer)
        if match is None:
            self._apply_search(self._search_term)
            match = self._wait_for_footer(filtered_footer)
        if match is None:
            raise AssertionError(
                f"Tenant grid isn't filtered by '{self._search_term}' (no "
                "'Tenants: N of M' footer) - refusing to select every tenant"
            )
        return int(match.group(1))

    @log_method_exceptions
    def _communications_button(self):
        return self.page.locator(
            'button[name="QA-BulkEditIndex-hb-accordion-button-'
            'Send-Email-or-SMS-Communications"]'
        )

    @log_method_exceptions
    def _click_next(self) -> None:
        next_button = self.page.get_by_role("button", name="Next", exact=True)
        expect(next_button).to_be_visible(timeout=self.timeout)
        next_button.click()

    @log_method_exceptions
    def start_communication(self, channel: str) -> None:
        # channel: "Send Email" or "Send SMS" - the two radio labels.
        with allure.step(f"Bulk Actions: {channel}"):
            self._communications_button().click()
            channel_option = self.page.locator("label").filter(
                has_text=re.compile(rf"^\s*{re.escape(channel)}\s*$")
            ).first
            expect(channel_option).to_be_visible(timeout=self.timeout)
            channel_option.click()
            self._click_next()

    @log_method_exceptions
    def compose_sms(self, message: str) -> None:
        with allure.step("Compose SMS"):
            # By role, not placeholder - confirmed live: the textarea's
            # wrapper div (.hb-textarea-wrapper) carries the same
            # placeholder attribute, so a placeholder match is ambiguous.
            message_field = self.page.get_by_role(
                "textbox", name="Enter Message", exact=True
            )
            expect(message_field).to_be_visible(timeout=self.timeout)
            message_field.fill(message)
            self._click_next()

    @log_method_exceptions
    def compose_email(self, subject: str, body: str) -> None:
        with allure.step("Compose Email"):
            # By role for the same reason as compose_sms's message field.
            subject_field = self.page.get_by_role(
                "textbox", name="Subject Title", exact=True
            )
            expect(subject_field).to_be_visible(timeout=self.timeout)
            subject_field.fill(subject)
            # Confirmed live: the body is a TinyMCE editor rendered inside
            # its own iframe ("Rich Text Area", #mce_N_ifr) - an empty body
            # is rejected with "Please enter your message".
            editor_body = self.page.frame_locator(
                "iframe.tox-edit-area__iframe"
            ).locator("body")
            editor_body.click()
            self.page.keyboard.type(body)
            self._click_next()

    @log_method_exceptions
    def review_recipients(self) -> tuple[int, list[str]]:
        """Reads the "Confirm & Send to Recipients" review: the Total
        Recipients count, and the recipient email addresses listed (empty
        for SMS, whose review lists phone numbers instead)."""
        with allure.step("Confirm & Send to Recipients: review"):
            heading = self.page.get_by_text("Confirm & Send to Recipients", exact=True)
            expect(heading).to_be_visible(timeout=self.timeout)
            # Confirmed live: the review first renders with "Total
            # Recipients: 0" and fills in the recipient list a moment later
            # - reading it straight away returned 0 for 6 selected tenants.
            total_line = (
                self.page.get_by_text(re.compile(r"Total Recipients"))
                .first.locator("xpath=..")
            )
            expect(total_line).to_contain_text(
                re.compile(r"Total Recipients:\s*[1-9]"), timeout=self.timeout
            )
            review = heading.locator(
                "xpath=ancestor::*[.//*[contains(normalize-space(.),"
                "'Total Recipients')]][1]"
            ).inner_text()
            total = re.search(r"Total Recipients:\s*(\d+)", review)
            if total is None:
                raise AssertionError(f"No 'Total Recipients' count on review: {review!r}")
            emails = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", review)
            return int(total.group(1)), emails

    @log_method_exceptions
    def confirm_and_send(self) -> None:
        with allure.step("Confirm & Send"):
            send_button = self.page.get_by_role(
                "button", name="Confirm & Send", exact=True
            )
            expect(send_button).to_be_visible(timeout=self.timeout)
            send_button.click()
            expect(
                self.page.get_by_text("Messages Sent", exact=True).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def close_bulk_actions(self) -> None:
        with allure.step("Close Bulk Actions without sending"):
            close_button = self.page.locator(
                'button[name="QA-ActionsPanelHeader-HbIcon-mdi-close"]'
            )
            if close_button.count() > 0 and close_button.first.is_visible():
                close_button.first.click()
            expect(
                self.page.get_by_text("Confirm & Send to Recipients", exact=True)
            ).to_be_hidden(timeout=self.timeout)
