import re

import allure
from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_ach_form import fill_ach_details
from common_utils.waits import waits


class HBQuickLaunchPage:
    """Dashboard "Quick Actions -> Move In/Reserve" flow: create a brand
    new lead and either reserve a space or move them straight into a
    lease, without leaving the dashboard. Ported from the old Robot
    Framework smoke suite's "Create Reservation - Through Quick Action"
    and "From Quick action Create a lease" scenarios - confirmed live
    (2026-09-10, stage) that the app has since replaced that suite's own
    "Open Quick Launch" button-then-panel and separate "Property
    Interested" field with a single-property dashboard where Quick
    Actions is always visible and the lead is scoped to whichever
    property is already selected."""

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
    def _mouse_click(self, locator: Locator) -> None:
        # A real move+down+up at the element's own coordinates, rather
        # than Locator.click()'s actionability-checked click (or a
        # force=True click, which still dispatches its event on the
        # locator itself) - confirmed live (2026-09-10, stage) that this
        # app's Vuetify radios bind their click handler to a sibling
        # ripple/selection-control div rather than the radio input
        # itself, so a click scoped to the input can report success
        # while leaving aria-checked unchanged. Same root cause as
        # HBMoveOutPage._mouse_click.
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if box is None:
            locator.click()
            return
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.up()

    @log_method_exceptions
    def _select_property(self, property_name: str) -> None:
        self._close_live_agent_notification()
        search_box = self.page.locator("#search-box")
        expect(search_box).to_be_visible(timeout=self.timeout)
        search_box.click()
        # Same picker widget as HBLeadManagementPage.open_leads/
        # HBMoveOutPage.open_tenants - the target property isn't
        # guaranteed to already be on top, so type the name to filter
        # down to it explicitly instead of hoping.
        search_input = search_box.locator("input")
        property_cell = self.page.get_by_role(
            "cell", name=property_name, exact=True
        )
        try:
            expect(property_cell).to_be_visible(timeout=waits().short)
        except AssertionError:
            search_input.fill(property_name)
            expect(property_cell).to_be_visible(timeout=self.timeout)
        property_cell.click()
        # Same multi-property picker quirk as HBLeadManagementPage.
        # open_leads: only a click on the row selects it there.
        try:
            expect(property_cell).to_be_hidden(timeout=waits().short)
        except AssertionError:
            property_cell.locator("xpath=ancestor::tr[1]").dispatch_event("click")
        # Confirms the single-property dashboard actually switched
        # before Quick Actions is used - the banner textbox is
        # re-rendered with the new property's name once it lands.
        expect(
            self.page.get_by_role(
                "textbox", name=re.compile(re.escape(property_name))
            )
        ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def select_property(self, property_name: str) -> None:
        # Also what Settings' own property pickers follow - e.g. Lead
        # Management's Property Settings only offers the dashboard's property
        # (see HBLeadScriptsPage.select_property).
        with allure.step(f"Select the dashboard property: {property_name}"):
            self._select_property(property_name)

    @log_method_exceptions
    def open_quick_launch_for_property(self, property_name: str) -> None:
        with allure.step(f"Open Quick Launch (Move In/Reserve) for {property_name}"):
            self._select_property(property_name)

            move_in_reserve_button = self.page.get_by_role(
                "button", name="Move In/Reserve", exact=True
            )
            expect(move_in_reserve_button).to_be_visible(timeout=self.timeout)
            move_in_reserve_button.click()

            search_for_tenant = self.page.get_by_role(
                "textbox", name="Search for Tenant", exact=True
            )
            expect(search_for_tenant).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def open_take_payment_for_property(self, property_name: str) -> None:
        with allure.step(f"Open Quick Launch (Take a Payment) for {property_name}"):
            self._select_property(property_name)

            take_payment_button = self.page.get_by_role(
                "button", name="Take a Payment", exact=True
            )
            expect(take_payment_button).to_be_visible(timeout=self.timeout)
            take_payment_button.click()

            search_for_tenant = self.page.get_by_role(
                "textbox", name="Search for Tenant", exact=True
            )
            expect(search_for_tenant).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def search_and_select_tenant_for_payment(self, search_term: str) -> None:
        # Confirmed live (2026-09-10, stage): searching this combobox by
        # the full "First Last" name can return "No Tenants found" even
        # for a tenant that genuinely exists - matching on a single,
        # sufficiently unique token (e.g. just the last name) is what
        # actually works, mirroring the old Robot suite's own "Search
        # And Select A Tenant To Take Payment" keyword, which likewise
        # searched on ${lead_firstname} alone rather than the full name.
        with allure.step(f"Search and select a tenant to take payment: {search_term}"):
            search_for_tenant = self.page.get_by_role(
                "textbox", name="Search for Tenant", exact=True
            )
            search_for_tenant.fill(search_term)
            tenant_option = self.page.get_by_role("option").first
            expect(tenant_option).to_be_visible(timeout=self.timeout)
            tenant_option.click()

    @log_method_exceptions
    def _add_additional_time(self, months: str) -> None:
        add_time_dropdown = self.page.get_by_role(
            "textbox", name="Add Additional Time", exact=True
        )
        # Confirmed live (2026-09-11, Bellflower): this readonly input is
        # covered by its own .v-select__selections div, which swallows a
        # click on the input - clicking the enclosing .v-select__slot is
        # what opens the menu (same as select_all_spaces_for_payment).
        add_time_dropdown.locator(
            "xpath=ancestor::*[contains(@class,'v-select__slot')][1]"
        ).first.click()
        month_option = self.page.get_by_role(
            "option", name=months, exact=True
        )
        expect(month_option).to_be_visible(timeout=self.timeout)
        month_option.click()

    @log_method_exceptions
    def ensure_payable_balance(self, months: str = "1 Month") -> None:
        # Confirmed live: a tenant moved in the same day can have a
        # $0.00 balance with no open invoices yet - same situation the
        # old Robot suite's "Check For Due Amount or Future Payments"
        # keyword handled by adding time to the lease to generate a
        # payable invoice when the balance was already zero.
        with allure.step("Check for due amount or future payments"):
            # Read from "Total Payment:" rather than the first "Total Due:" -
            # confirmed live (2026-09-11, Bellflower, one-space tenant): that
            # label's own text didn't carry its amount, so a $0.00 balance
            # read as "something due", no time was added, and Take a Payment
            # was left at Total Payment $0.00 with Process Payment disabled.
            expect(self.page.get_by_text("Total Payment:").first).to_be_visible(
                timeout=self.timeout
            )
            zero_payment = re.compile(r"Total Payment:\s*\$0\.00")
            if not zero_payment.search(self.page.locator("body").inner_text()):
                return
            self._add_additional_time(months)
            expect(self.page.locator("body")).not_to_contain_text(
                zero_payment, timeout=self.timeout
            )

    @log_method_exceptions
    def select_number_of_months(self, months: str) -> None:
        # Old Robot suite's "Select Number of Months" keyword - unlike
        # ensure_payable_balance, this always adds the given number of
        # months regardless of the current Total Due, since the "Make
        # payment for several months" scenario specifically wants a
        # multi-month invoice to pay off in one go.
        with allure.step(f"Select number of months: {months}"):
            self._add_additional_time(months)
            # Same as ensure_payable_balance: let the new invoice reach Total
            # Payment before a payment method is picked - with nothing to pay
            # yet, Cash was seen staying unchecked (2026-09-11, Bellflower).
            expect(self.page.locator("body")).not_to_contain_text(
                re.compile(r"Total Payment:\s*\$0\.00"), timeout=self.timeout
            )

    @log_method_exceptions
    def select_all_spaces_for_payment(self, months: str = "1 Month") -> float:
        # Old Robot suite's "Select Multiple Spaces For Payment" + "Check For
        # Due Amount or Future Payments". Confirmed live (2026-09-11,
        # Bellflower): Take a Payment lists one expansion panel per space
        # ("0010 (BELL - Bellflower) Total Due:$0.00"), each with its own
        # checkbox in the header, and a space with nothing due only becomes
        # payable after Add Additional Time on its own panel. Returns the
        # combined Total Due across every space, for checking the receipt.
        with allure.step("Select multiple spaces for payment"):
            space_panels = self.page.locator(".v-expansion-panel").filter(
                has=self.page.get_by_role("checkbox"),
                has_text="Total Due:",
            )
            expect(space_panels.first).to_be_visible(timeout=self.timeout)
            space_count = space_panels.count()
            if space_count < 2:
                raise AssertionError(
                    "Tenant does not have multiple spaces to proceed with test "
                    f"scenario (found {space_count})"
                )

            total_due = 0.0
            for index in range(space_count):
                panel = space_panels.nth(index)
                checkbox = panel.get_by_role("checkbox").first
                # Ripple locator click, same reason as
                # complete_move_in_checklist_and_finalize's checklist items.
                ripple = checkbox.locator(
                    "xpath=ancestor::*[contains(@class,"
                    "'v-input--selection-controls__input')][1]"
                    "//*[contains(@class,'v-input--selection-controls__ripple')]"
                ).first
                for attempt in range(3):
                    if checkbox.is_checked():
                        break
                    ripple.click()
                    try:
                        expect(checkbox).to_be_checked(timeout=waits().short)
                        break
                    except AssertionError:
                        if attempt == 2:
                            raise

                due = self._space_total_due(panel)
                if due == 0:
                    if "v-expansion-panel--active" not in (
                        panel.get_attribute("class") or ""
                    ):
                        panel.locator(".v-expansion-panel-header").first.click()
                    # Confirmed live: the readonly "Add Additional Time" input
                    # itself is covered by its own .v-select__selections div
                    # (which swallows a click on the input) - clicking the
                    # enclosing .v-select__slot is what opens the menu.
                    panel.get_by_role(
                        "textbox", name="Add Additional Time", exact=True
                    ).locator(
                        "xpath=ancestor::*[contains(@class,'v-select__slot')][1]"
                    ).first.click()
                    month_option = self.page.get_by_role(
                        "option", name=months, exact=True
                    )
                    expect(month_option).to_be_visible(timeout=self.timeout)
                    month_option.click()
                    expect(panel).not_to_contain_text(
                        re.compile(r"Total Due:\s*\$0\.00"), timeout=self.timeout
                    )
                    due = self._space_total_due(panel)
                total_due += due
            return round(total_due, 2)

    @log_method_exceptions
    def _space_total_due(self, panel: Locator) -> float:
        match = re.search(r"Total Due:\s*\$([\d,]+\.\d{2})", panel.inner_text())
        if match is None:
            raise AssertionError(
                f"No 'Total Due' amount found on space panel: {panel.inner_text()!r}"
            )
        return float(match.group(1).replace(",", ""))

    @log_method_exceptions
    def pay_by_cash(self) -> None:
        # Confirmed live: unlike the card-payment form, Cash Amount
        # Tendered and Reference Name both come pre-filled (from the
        # invoice total and tenant name respectively) - nothing else to
        # enter before processing.
        with allure.step("Make cash payment"):
            # Confirmed live: matching "Cash" by button role/name alone
            # is ambiguous - this page can have an unrelated element
            # (e.g. a charges/history expansion panel) that also reduces
            # to a "button" named "Cash" - scoping to the payment-method
            # radiogroup avoids that collision. Clicking the radio input
            # itself (even via _mouse_click's raw coordinates) doesn't
            # register here - confirmed live: unlike the Notice Delivery
            # radio, this option's click handler is bound to the whole
            # wrapping button (icon + label), not the input, so _mouse_
            # click needs to target that wrapping button instead.
            cash_option = self.page.get_by_role("radiogroup").get_by_role(
                "button", name="Cash", exact=True
            )
            cash_radio = cash_option.get_by_role("radio", name="Cash", exact=True)
            expect(cash_option).to_be_visible(timeout=self.timeout)
            # Up to 3 tries, the later ones with a plain locator click (which
            # scrolls and checks for obscuring elements first). Seen live
            # (2026-09-11, Bellflower, Take a Payment): Cash stayed unchecked
            # for a full minute - but with Total Payment at $0.00 (nothing to
            # pay yet), which ensure_payable_balance now prevents. The extra
            # tries are a cheap guard, not a confirmed fix for that case.
            for attempt in range(3):
                if cash_radio.is_checked():
                    break
                if attempt == 0:
                    self._mouse_click(cash_option)
                else:
                    cash_option.click()
                try:
                    expect(cash_radio).to_be_checked(timeout=waits().short)
                    break
                except AssertionError:
                    if attempt == 2:
                        raise
            process_payment_button = self.page.get_by_role(
                "button", name="Process Payment", exact=True
            )
            expect(process_payment_button).to_be_visible(timeout=self.timeout)
            process_payment_button.click()

    @log_method_exceptions
    def skip_payment(self) -> None:
        # Old Robot suite's "Skip Payments", used when adding another space
        # for an existing tenant so a later payment can cover every space
        # at once. Confirmed live (2026-09-11, Bellflower): Skip Payment
        # starts disabled on the Finalize & Take Payment step and enables a
        # moment later; once processed, the payment buttons give way to the
        # bottom-bar "Finalize" (see complete_move_in_checklist_and_finalize).
        with allure.step("Skip payments"):
            skip_button = self.page.get_by_role(
                "button", name="Skip Payment", exact=True
            )
            expect(skip_button).to_be_enabled(timeout=self.timeout)
            skip_button.click()
            expect(skip_button).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def assert_amount_paid(self, amount: float) -> None:
        # Old Robot suite's "Verify The Amount Paid in Invoice". Confirmed
        # live (2026-09-11, Bellflower): the receipt's Payment Info shows
        # "Amount Paid", the payment date, then the amount (e.g. $475.00
        # for two spaces paid together).
        formatted = f"${amount:,.2f}"
        with allure.step(f"Verify the amount paid in the invoice: {formatted}"):
            expect(
                self.page.get_by_text("Amount Paid", exact=True).first
            ).to_be_visible(timeout=self.timeout)
            expect(
                self.page.get_by_text(formatted, exact=True).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_payment_receipt(self, payment_method: str) -> None:
        with allure.step(f"Verify the payment method in the invoice: {payment_method}"):
            expect(
                self.page.get_by_text("Customer Receipt", exact=True)
            ).to_be_visible(timeout=self.timeout)
            expect(
                self.page.get_by_text(payment_method, exact=True).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def start_new_contact(self, email: str) -> None:
        with allure.step(f"Create new contact: {email}"):
            search_for_tenant = self.page.get_by_role(
                "textbox", name="Search for Tenant", exact=True
            )
            search_for_tenant.fill(email)
            create_new_contact = self.page.get_by_text(
                "Create New Contact", exact=True
            )
            expect(create_new_contact).to_be_visible(timeout=self.timeout)
            create_new_contact.click()

    @log_method_exceptions
    def fill_lead_details(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
        lead_initiated: str,
        lead_source: str,
    ) -> None:
        with allure.step(f"Fill lead details for {first_name} {last_name}"):
            self.page.get_by_role("textbox", name="First", exact=True).fill(
                first_name
            )
            self.page.get_by_role("textbox", name="Last", exact=True).fill(
                last_name
            )
            self.page.get_by_role("textbox", name="Enter Email", exact=True).fill(
                email
            )
            self.page.get_by_role(
                "textbox", name="Phone Number", exact=True
            ).fill(phone_number)

            # Confirmed live: both are required to Reserve/Move In, even
            # though they weren't part of the old Robot suite's "Fill
            # Lead details" keyword - the app rejects the next step with
            # "There are errors in your form" (Lead Initiated/Lead
            # Source both required) without them.
            self.select_lead_source(lead_initiated, lead_source)

    @log_method_exceptions
    def select_lead_source(self, lead_initiated: str, lead_source: str) -> None:
        # Also needed on its own for Add Space on an existing tenant (see
        # HBTenantSpacesPage.start_add_space) - confirmed live (2026-09-11,
        # Bellflower): name/email/phone/address come pre-filled there, but
        # these two start blank and "Move In" is silently rejected until
        # they're set.
        with allure.step(f"Set lead source: {lead_initiated} / {lead_source}"):
            self._select_dropdown_option(
                "How was the lead initiated?", lead_initiated
            )
            self._select_dropdown_option(
                "Where did the lead come from?", lead_source
            )

    @log_method_exceptions
    def _select_dropdown_option(self, dropdown_name: str, option_name: str) -> None:
        dropdown = self.page.get_by_role("textbox", name=dropdown_name, exact=True)
        dropdown.click()
        option = self.page.get_by_role("option", name=option_name, exact=True)
        expect(option).to_be_visible(timeout=self.timeout)
        option.click()

    @log_method_exceptions
    def _select_dropdown_option_via_button(
        self, button_name: str, option_name: str
    ) -> None:
        # Some dropdowns (Month/Year on both the coverage-policy-
        # expiration and card-expiry fields) wrap their combobox in an
        # extra button element, unlike the plain combobox>textbox
        # structure _select_dropdown_option targets - confirmed live
        # (2026-09-10, stage): clicking the inner (readonly) textbox
        # directly on these can get intercepted by an overlapping
        # sibling element instead of opening the menu, where clicking
        # the wrapping button does not.
        button = self.page.get_by_role("button", name=button_name, exact=True)
        button.click()
        option = self.page.get_by_role("option", name=option_name, exact=True)
        expect(option).to_be_visible(timeout=self.timeout)
        option.click()

    @log_method_exceptions
    def _select_first_available_space(
        self, exclude_number_prefixes: tuple[str, ...] = ()
    ) -> str:
        spaces_tab = self.page.get_by_role("tab", name="Spaces", exact=True)
        rows = self.page.get_by_role(
            "row", name="Press SPACE to select this row."
        )
        # HB's async duplicate check (contacts/check on the phone, ~2 s
        # after it's typed) switches the drawer to its "Similar Contacts"
        # tab when the number matches an existing contact - and with only
        # 100 fictional 555-01xx numbers, repeats happen (confirmed live
        # 2026-09-13, Bellflower, (707) 555-0108). Clicking back to Spaces
        # restores the grid, HB doesn't switch it again, and the lead is
        # still created as a new contact (no similar one is picked). Poll
        # rather than click once, since the switch can land after an early
        # click, and only go on once the rows have stayed up ~1.5 s.
        stable_polls = 0
        for _ in range(int(self.timeout / 500)):
            if (
                spaces_tab.count() > 0
                and spaces_tab.first.is_visible()
                and spaces_tab.first.get_attribute("aria-selected") != "true"
            ):
                spaces_tab.first.click()
                stable_polls = 0
            elif rows.count() > 0 and rows.first.is_visible():
                stable_polls += 1
                if stable_polls >= 3:
                    break
            self.page.wait_for_timeout(waits().poll_interval)
        expect(rows.first).to_be_visible(timeout=self.timeout)
        # Confirmed live (2026-09-11, stage): filtering the Space List's
        # own "Type" picker down to just Storage is fragile in practice -
        # this sandbox's per-type inventory is uneven and can leave a
        # property with zero currently-available Storage spaces (while
        # still having plenty of Parking ones), so the filtered list can
        # come back genuinely empty rather than just loading slowly.
        # The row's own text never actually contains the word "parking"
        # (that only appears in the lease form's summary *after*
        # selecting a space) - the only signal available in the list
        # itself is the space number's own prefix, which this sandbox's
        # data consistently uses to mark type (confirmed live across
        # multiple runs: every "Pa<digits>K" space number opened into a
        # Parking-type lease form). Scanning the unfiltered list and
        # skipping only the excluded prefix(es) draws from the full
        # pool instead of one (possibly empty) filtered slice. The grid
        # virtualizes rows (only a scrolled-into-view batch is actually
        # mounted at once), so if every currently-mounted row happens to
        # be excluded, scroll the grid to mount the next batch and try
        # again rather than giving up.
        for _ in range(10):
            row_count = rows.count()
            for index in range(row_count):
                row = rows.nth(index)
                space_number = row.locator(
                    "[role='gridcell']"
                ).first.inner_text().strip()
                normalized_number = space_number.lstrip("#").lower()
                if any(
                    normalized_number.startswith(prefix.lower())
                    for prefix in exclude_number_prefixes
                ):
                    continue
                row.click()
                return space_number
            if row_count == 0:
                break
            rows.last.scroll_into_view_if_needed()
            self.page.wait_for_timeout(300)
        raise AssertionError(
            f"No available space found excluding number prefixes: "
            f"{exclude_number_prefixes}"
        )

    @log_method_exceptions
    def reserve_first_available_space(
        self, exclude_number_prefixes: tuple[str, ...] = ()
    ) -> str:
        # exclude_number_prefixes: see move_in_first_available_space - a
        # reservation that's later moved in (e.g. "From Leads create a
        # Rental") needs the same Parking exclusion, since the Lease step
        # it reaches is filled by the same storage-only form methods.
        with allure.step("Select space and reserve"):
            space_number = self._select_first_available_space(
                exclude_number_prefixes
            )

            reserve_button = self.page.get_by_role(
                "button", name="Reserve", exact=True
            )
            expect(reserve_button).to_be_visible(timeout=self.timeout)
            reserve_button.click()

            make_reservation_button = self.page.get_by_role(
                "button", name="Make Reservation", exact=True
            )
            expect(make_reservation_button).to_be_visible(timeout=self.timeout)
            make_reservation_button.click()
            return space_number

    @log_method_exceptions
    def save_lead(self) -> None:
        # Confirmed live (2026-09-13, Bellflower): with the lead details and
        # lead source filled, "Save Lead" needs no space - it creates a plain
        # active lead, shows "Lead created successfully." after a few
        # seconds and closes the onboarding drawer by itself.
        with allure.step("Save lead"):
            save_button = self.page.get_by_role("button", name="Save Lead", exact=True)
            expect(save_button).to_be_enabled(timeout=self.timeout)
            save_button.click()
            expect(
                self.page.get_by_text("Lead created successfully.").first
            ).to_be_visible(timeout=self.timeout)
            expect(
                self.page.locator("aside.new_lead.v-navigation-drawer--open")
            ).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def assert_reservation_active(self, first_name: str, last_name: str) -> None:
        with allure.step(f"Verify reservation for {first_name} {last_name}"):
            expect(self.page).to_have_url(re.compile(r"/leads"), timeout=self.timeout)
            search_leads = self.page.get_by_role(
                "textbox", name="Search Leads", exact=True
            )
            expect(search_leads).to_be_visible(timeout=self.timeout)
            search_leads.fill(f"{first_name} {last_name}")
            self.page.keyboard.press("Enter")

            # This grid's row role carries a fixed aria-label ("Press
            # SPACE to select this row.") rather than its cells' text -
            # confirmed live (2026-09-10, stage) - so the row can't be
            # found by matching the lead's name against the row itself,
            # only against one of its individual gridcells (each of
            # which does expose its own text as its accessible name).
            name_cell = self.page.get_by_role(
                "gridcell", name=f"{first_name} {last_name}", exact=True
            )
            expect(name_cell).to_be_visible(timeout=self.timeout)
            lead_row = name_cell.locator("xpath=ancestor::*[@role='row'][1]")
            # The Lead Status cell's underlying text is lowercase "active"
            # - confirmed live (2026-09-10, stage) - and only rendered
            # capitalized via CSS (text-capitalize), same as the status
            # cells HBLeadManagementPage reads elsewhere in this app.
            status_cell = lead_row.locator("[role='gridcell']").first
            expect(status_cell).to_have_text(
                re.compile(r"^\s*active\s*$", re.IGNORECASE), timeout=self.timeout
            )

    @log_method_exceptions
    def move_in_first_available_space(self) -> str:
        with allure.step("Select space and move in"):
            # Excludes space numbers prefixed "Pa" (Parking, confirmed
            # live) - this flow's fill_lease_address_and_identity/
            # decline_coverage_with_expiration only know how to complete
            # a storage-style unit's fields, not Parking's vehicle/
            # license-plate/insurance ones.
            space_number = self._select_first_available_space(
                exclude_number_prefixes=("pa",)
            )

            move_in_button = self.page.get_by_role(
                "button", name="Move In", exact=True
            )
            expect(move_in_button).to_be_visible(timeout=self.timeout)
            # Let the picked space's lease details settle before pressing
            # Move In: seen 2026-09-13 (Bellflower #0031) a click made the
            # instant the button showed register nothing - the drawer sat on
            # the Lead step for the full timeout - while a live walk that
            # paused ~1.5 s first reached the Lease step. Non-fatal, in case
            # a flow reaching this (e.g. Add Space) doesn't show the cost.
            try:
                expect(self.page.locator("body")).to_contain_text(
                    re.compile(r"Move-In Cost:\s*\$[\d,]+\.\d{2}"), timeout=waits().long
                )
            except AssertionError:
                pass
            self.page.wait_for_timeout(1000)
            move_in_button.click()
            # Confirmed live: the Lease step's own form (Address,
            # Driver's License, ...) can take a moment to render after
            # this click - waiting for a distinctive, single-purpose
            # heading here (rather than the "Street" textbox, whose role
            # query can otherwise resolve to an unrelated stale element
            # elsewhere on the page) means callers never race it.
            date_of_birth = self.page.get_by_text("Date of Birth", exact=True)
            lead_step_complete = self.page.locator(
                ".v-stepper__step.v-stepper__step--complete"
            ).filter(
                has=self.page.locator(
                    ".v-stepper__label", has_text=re.compile(r"^\s*Lead\s*$")
                )
            )
            try:
                expect(date_of_birth).to_be_visible(timeout=waits().extra_long)
            except AssertionError:
                # One guarded retry, only when the first click visibly never
                # registered: Move In still showing and the Lead step not yet
                # marked complete. A registered click marks it complete
                # (v-stepper__step--complete) before the Lease form renders -
                # ~10 s and 12.6 s respectively in the 2026-09-13 walk - so a
                # slow but registered click is never pressed twice.
                if lead_step_complete.count() == 0 and move_in_button.is_visible():
                    move_in_button.click()
            expect(date_of_birth).to_be_visible(timeout=self.timeout)
            return space_number

    @log_method_exceptions
    def fill_lease_address_and_identity(
        self,
        street: str,
        zip_code: str,
        state: str,
        city: str,
        date_of_birth: str,
        license_number: str,
        license_expiry: str,
        license_state: str,
    ) -> None:
        # Confirmed live: this whole Lease-step form is local/unsaved
        # draft state - navigating away (even just to check another
        # page) resets every field here back to blank, so callers must
        # fill this in the same uninterrupted pass as the rest of the
        # lease before advancing to Payments.
        with allure.step("Fill in mandatory lease details"):
            self.page.get_by_role("textbox", name="Street", exact=True).fill(street)
            self.page.get_by_role("textbox", name="Zip", exact=True).fill(zip_code)
            self._select_dropdown_option_first_match("State", state)
            self._type_and_select_option("City", city)

            self.page.get_by_role(
                "textbox", name="MM/DD/YYYY", exact=True
            ).fill(date_of_birth)

            self.page.get_by_role(
                "textbox", name="License Number", exact=True
            ).fill(license_number)
            # Confirmed live: a second, readonly "Expiration Date" field
            # (a derived summary elsewhere on this step) can already be
            # in the DOM by this point - .first targets the editable
            # Driver's License one, which is first in DOM order.
            self.page.get_by_role(
                "textbox", name="Expiration Date", exact=True
            ).first.fill(license_expiry)
            # The address State combobox above is also named "State" -
            # this is deliberately the *second* one (the Driver's
            # License section's own State field).
            self._select_dropdown_option_first_match(
                "State", license_state, index=1
            )

    @log_method_exceptions
    def _select_dropdown_option_first_match(
        self, dropdown_name: str, option_name: str, index: int = 0
    ) -> None:
        dropdown = self.page.get_by_role("textbox", name=dropdown_name, exact=True).nth(
            index
        )
        dropdown.fill(option_name)
        option = self.page.get_by_role("option", name=option_name, exact=True)
        expect(option).to_be_visible(timeout=self.timeout)
        option.click()

    @log_method_exceptions
    def _type_and_select_option(self, field_name: str, value: str) -> None:
        field = self.page.get_by_role("textbox", name=field_name, exact=True)
        field.fill(value)
        option = self.page.get_by_role("option", name=value, exact=True)
        expect(option).to_be_visible(timeout=self.timeout)
        option.click()

    @log_method_exceptions
    def decline_coverage_with_expiration(self) -> None:
        # Confirmed live: "Tenant has their own coverage" (this app's
        # decline option) only satisfies validation once its own policy
        # expiration Month/Year are also picked - the old Robot suite's
        # "Select Services Applicable" keyword didn't need this because
        # that field didn't exist yet. Both dropdowns only ever offer a
        # short, "today"-anchored window of choices (e.g. the 4 nearest
        # months, ~7 nearest years) rather than a full calendar - picking
        # the furthest-out option in each is the only choice that stays
        # valid regardless of which day this runs, since any fixed
        # month/year eventually ages out of that window.
        with allure.step("Select applicable services: decline coverage"):
            decline_label = self.page.locator("label").filter(
                has_text="Tenant has their own coverage"
            )
            month_field = self.page.get_by_role(
                "textbox", name="Month", exact=True
            )
            # A plain click can land on this radio's ripple/overlay div
            # instead of registering the selection - same class of
            # issue HBMoveOutPage._mouse_click exists for elsewhere in
            # this app - and even once it registers, the policy
            # expiration Month/Year fields it reveals can take a moment
            # to render. Retry the label click until they actually show.
            for attempt in range(3):
                decline_label.click()
                try:
                    expect(month_field).to_be_visible(timeout=waits().short)
                    break
                except AssertionError:
                    if attempt == 2:
                        raise

            self._select_last_dropdown_option("Month")
            self._select_last_dropdown_option("Year")

    @log_method_exceptions
    def _select_last_dropdown_option(self, button_name: str) -> None:
        # See _select_dropdown_option_via_button: clicking the wrapping
        # button, not the inner readonly textbox, is what reliably opens
        # this style of dropdown.
        button = self.page.get_by_role("button", name=button_name, exact=True)
        button.click()
        options = self.page.get_by_role("option")
        expect(options.first).to_be_visible(timeout=self.timeout)
        options.last.click()

    @log_method_exceptions
    def confirm_notice_delivery_method(self) -> None:
        # Confirmed live: this accordion section must actually be
        # expanded for its default selection ("Electronic Mail") to
        # register with the form - Payments/Move-In rejects the lease
        # with "The Notice Delivery Method field is required" if it's
        # left collapsed, even though a default appears pre-selected
        # once opened.
        with allure.step("Confirm notice delivery method"):
            header = self.page.get_by_role(
                "button", name="Notice Delivery Method", exact=True
            )
            notice_radio = self.page.get_by_role(
                "radio", name=re.compile(r"^Electronic Mail")
            )
            # Confirmed live (2026-09-11, uat_storoutlet/Bellflower): not
            # every property's lease form has this section at all -
            # Bellflower's goes straight from Coverage to Merchandise/Fees
            # and Payments accepts the lease without it. Only enforced
            # where the section actually exists.
            try:
                expect(header).to_be_visible(timeout=waits().medium)
            except AssertionError:
                return
            # Confirmed live: the header's first click can register as
            # merely scrolling it into view rather than expanding the
            # accordion, and the accordion can also collapse again by
            # itself shortly after opening - retry the whole expand+click
            # pair (not just the initial expand) until the radio is both
            # visible and actually ends up checked. _mouse_click, not
            # check()/click() - confirmed live: this radio's click
            # handler lives on a sibling ripple div, not the input
            # itself, so even a force=True click on the input can report
            # success while leaving aria-checked unchanged.
            for attempt in range(3):
                header.click()
                try:
                    expect(notice_radio).to_be_visible(timeout=waits().short)
                    if not notice_radio.is_checked():
                        self._mouse_click(notice_radio)
                        expect(notice_radio).to_be_checked(timeout=waits().short)
                    break
                except (AssertionError, PlaywrightTimeoutError):
                    if attempt == 2:
                        raise

    @log_method_exceptions
    def confirm_vehicle_information(
        self, has_vehicle: bool = False, vehicle_type: str = "Car"
    ) -> None:
        # Confirmed live (2026-09-11, stage): a failed run's captured page
        # snapshot showed this section's radio already reading "No" yet
        # its full vehicle sub-form (Type*, Make, Model, VIN, ...) still
        # rendered and Payments unable to proceed - a stale/inconsistent
        # DOM state (most likely left over from an earlier retry attempt
        # toggling this answer) rather than "No" itself being invalid; an
        # explicit, freshly-registered click (not just trusting whatever
        # "No" already shows) is what actually clears it.
        # Also confirmed live: selecting "Yes" instead reveals a required
        # "Type*" field ("Select Type") that Payments rejects if left
        # empty - handled below by picking vehicle_type once "Yes" is
        # confirmed checked.
        # "Yes"/"No" radio labels aren't unique on this page - Additional
        # Contact and Active Duty Military use the same two labels - so
        # the target radio is scoped to the radiogroup immediately
        # following this section's own question text rather than matched
        # by role/name alone. The accordion appeared already expanded in
        # that failed run (unlike Notice Delivery Method, which starts
        # collapsed), so the header is only clicked if the question isn't
        # already visible, to avoid accidentally collapsing it instead.
        with allure.step("Confirm vehicle information"):
            header = self.page.get_by_role(
                "button", name="Vehicle Information", exact=True
            )
            question = self.page.get_by_text(
                "Are you storing a vehicle?", exact=True
            )
            target_label = "Yes" if has_vehicle else "No"
            for attempt in range(3):
                if question.count() == 0 or not question.first.is_visible():
                    header.click()
                try:
                    expect(question).to_be_visible(timeout=waits().short)
                    radiogroup = question.locator(
                        "xpath=following::*[@role='radiogroup'][1]"
                    )
                    target_radio = radiogroup.get_by_role(
                        "radio", name=target_label, exact=True
                    )
                    expect(target_radio).to_be_visible(timeout=waits().short)
                    if not target_radio.is_checked():
                        self._mouse_click(target_radio)
                        expect(target_radio).to_be_checked(timeout=waits().short)
                    break
                except (AssertionError, PlaywrightTimeoutError):
                    if attempt == 2:
                        raise

            if has_vehicle:
                type_dropdown = self.page.get_by_role(
                    "textbox", name="Select Type", exact=True
                )
                if type_dropdown.count() > 0:
                    self._select_dropdown_option_via_button(
                        "Select Type", vehicle_type
                    )

    @log_method_exceptions
    def proceed_to_payments(self) -> None:
        with allure.step("Proceed to payments"):
            payments_button = self.page.get_by_role(
                "button", name="Payments", exact=True
            )
            expect(payments_button).to_be_visible(timeout=self.timeout)
            payments_button.click()
            process_payment = self.page.get_by_role(
                "button", name="Process Payment", exact=True
            )
            # Confirmed live (2026-09-11, Bellflower, Add Space for a tenant
            # who already has a space): Payments first raises a "Confirm
            # Access Hours" dialog - the tenant's existing space(s) in the
            # same access area get their hours changed - and nothing advances
            # until it's confirmed. Only answered when it actually appears.
            access_hours_dialog = self.page.locator(".v-dialog--active").filter(
                has_text="Confirm Access Hours"
            )
            expect(process_payment.or_(access_hours_dialog).first).to_be_visible(
                timeout=self.timeout
            )
            if access_hours_dialog.count() > 0 and access_hours_dialog.first.is_visible():
                access_hours_dialog.get_by_role(
                    "button", name="Confirm", exact=True
                ).click()
            expect(process_payment).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def pay_by_credit_card(
        self,
        card_number: str,
        cvv: str,
        expiry_month: str,
        expiry_year: str,
        billing_zip: str,
    ) -> None:
        # Uses the "Same as Tenant" / "Default Address" shortcuts rather
        # than filling cardholder name and billing address by hand where
        # available - confirmed live (2026-09-10, stage) that this
        # billing form isn't identical everywhere: on one property
        # (Tustin) checking "Default Address" auto-filled the full
        # street/city/zip and the expiry Month/Year dropdowns came
        # pre-selected; on another (Hamilton County) neither shortcut
        # nor prefill was present at all, only a bare Zip* field and
        # blank MM/YY dropdowns. expiry_month/expiry_year/billing_zip
        # are only actually used as a fallback when the corresponding
        # field is still blank after the shortcuts are tried.
        with allure.step("Make card payment"):
            self.page.get_by_role(
                "button", name="Credit/Debit", exact=True
            ).click()

            same_as_tenant = self.page.locator("label").filter(
                has_text="Same as Tenant"
            )
            same_as_tenant.click()
            default_address = self.page.locator("label").filter(
                has_text="Default Address"
            )
            if default_address.count() > 0 and default_address.first.is_visible():
                default_address.first.click()
            else:
                billing_zip_field = self.page.get_by_role(
                    "textbox", name="Zip*", exact=True
                )
                if billing_zip_field.count() > 0:
                    billing_zip_field.fill(billing_zip)

            self.page.locator('input[name="card-number"]').fill(card_number)
            self.page.locator('input[name="card-cvv"]').fill(cvv)

            month_field = self.page.get_by_role("button", name="MM", exact=True)
            if month_field.count() > 0 and month_field.first.is_visible():
                self._select_dropdown_option_via_button("MM", expiry_month)
                self._select_dropdown_option_via_button("YY", expiry_year)

            process_payment_button = self.page.get_by_role(
                "button", name="Process Payment", exact=True
            )
            process_payment_button.click()

    @log_method_exceptions
    def read_total_payment(self) -> float:
        """Take a Payment's "Total Payment:" once it has settled - confirmed
        live (2026-09-13, Bellflower): after Add Additional Time it moves
        from the open invoice's amount ($110.50) to the new total ($574.50
        for 4 more months at $116) within a second or two."""
        readings: list[str | None] = []
        for _ in range(int(self.timeout / 500)):
            match = re.search(
                r"Total Payment:\s*\$([\d,]+\.\d{2})", self.page.locator("body").inner_text()
            )
            readings.append(match.group(1) if match else None)
            if (
                readings[-1]
                and readings[-1] != "0.00"
                and len(readings) >= 6
                and len(set(readings[-6:])) == 1
            ):
                total = float(readings[-1].replace(",", ""))
                allure.attach(
                    f"${total:,.2f}", name="Total Payment", attachment_type=allure.attachment_type.TEXT
                )
                return total
            self.page.wait_for_timeout(waits().poll_interval)
        raise AssertionError(f"Take a Payment's Total Payment never settled: {readings[-6:]}")

    @log_method_exceptions
    def assert_ach_payment_receipt(self, account_type: str, account_number: str) -> None:
        # Confirmed live (2026-09-13, Bellflower): an ACH payment's receipt
        # names the account, not the method ("Checking**** 6667"), so it
        # can't use assert_payment_receipt's exact method label.
        last4 = account_number[-4:]
        with allure.step(f"Verify the ACH receipt: {account_type} ****{last4}"):
            expect(
                self.page.get_by_text("Customer Receipt", exact=True)
            ).to_be_visible(timeout=self.timeout)
            expect(
                self.page.get_by_text(
                    re.compile(rf"{re.escape(account_type)}\s*\*+\s*{last4}")
                ).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def pay_by_ach(
        self,
        routing_number: str,
        account_number: str,
        account_type: str,
        first_name: str,
        last_name: str,
    ) -> None:
        # Confirmed live (2026-09-13, uat_storoutlet/Bellflower, the tenant
        # page's Take a Payment - the same drawer Quick Launch opens):
        # "ACH/E-Check" is a button-wrapped radio in the payment-method
        # radiogroup, like Cash, and the account form is the one Add
        # Payment Method also shows (see fill_ach_details). A $574.50
        # payment went through with routing 011401533 (POST .../payments/
        # bulk 200, receipt "Checking**** 6667").
        with allure.step("Make ACH payment"):
            ach_option = self.page.get_by_role("radiogroup").get_by_role(
                "button", name="ACH/E-Check", exact=True
            )
            ach_radio = ach_option.get_by_role(
                "radio", name="ACH/E-Check", exact=True
            )
            expect(ach_option).to_be_visible(timeout=self.timeout)
            # Same retry as pay_by_cash's payment-method radio.
            for attempt in range(3):
                if ach_radio.is_checked():
                    break
                if attempt == 0:
                    self._mouse_click(ach_option)
                else:
                    ach_option.click()
                try:
                    expect(ach_radio).to_be_checked(timeout=waits().short)
                    break
                except AssertionError:
                    if attempt == 2:
                        raise

            fill_ach_details(
                self.page,
                self.page,
                self.timeout,
                first_name,
                last_name,
                account_type,
                routing_number,
                account_number,
            )

            process_payment_button = self.page.get_by_role(
                "button", name="Process Payment", exact=True
            )
            process_payment_button.click()

    @log_method_exceptions
    def _signing_frame(self):
        # Scoped by src rather than a bare "iframe" - confirmed live
        # (2026-09-11, stage, Honolulu): once the lead has an email
        # interaction, its Communication panel renders a second iframe
        # (the email preview, .mail-container-iframe) and a bare "iframe"
        # frame locator fails on a strict-mode violation.
        return self.page.frame_locator('iframe[src*="document-signing"]')

    @log_method_exceptions
    def sign_documents_on_this_device(self, initials: str = "XX") -> None:
        # Confirmed live (2026-09-11, stage): the document-signing widget
        # behind "Sign on This Device" is NOT one fixed flow - it depends
        # on which document(s) the lease actually requires, which varies
        # by property/unit/coverage even within the same property:
        # - A single simple document (seen live: Rutland's "Superlease")
        #   shows one plain "I Agree" button - the original assumption
        #   this whole method used to make.
        # - Multiple documents (seen live: Honolulu's "Lease Agreement" +
        #   "Insurance-Protection Enrollment" [+ "Vehicle Addendum" when
        #   storing a vehicle]) use a click-to-sign widget instead, with
        #   a "X of Y Documents" counter, and each document can have more
        #   than one signature/initials field (Lease Agreement had 2: an
        #   initials field partway through, then a full signature at the
        #   end).
        # Both can occur on the very same property depending on what the
        # specific lease pulled in, so this checks for "I Agree" first
        # and only falls through to the multi-field flow if that never
        # appears.
        with allure.step("Sign the documents"):
            sign_button = self.page.get_by_role(
                "button", name="Sign on This Device", exact=True
            )
            expect(sign_button).to_be_visible(timeout=self.timeout)
            sign_button.click()

            agreement_frame = self._signing_frame()
            i_agree_button = agreement_frame.get_by_role(
                "button", name="I Agree", exact=True
            )
            start_button = agreement_frame.get_by_role(
                "button", name="Start Signing", exact=True
            )
            try:
                expect(i_agree_button.or_(start_button)).to_be_visible(
                    timeout=self.timeout
                )
            except AssertionError:
                # Neither ever showed up - re-check each individually so
                # the resulting error names whichever locator's wait this
                # actually was, instead of the ambiguous combined one.
                expect(start_button).to_be_visible(timeout=waits().short)

            if i_agree_button.count() > 0 and i_agree_button.is_visible():
                i_agree_button.click()
                return

            # Confirmed live (2026-09-11, stage, Hamilton County's 6-document
            # set): a document with no fields of its own (A2 - just a "This
            # document has been signed. Continue" screen) can be stepped past
            # without Hummingbird recording it - it stays "Ready to sign" in
            # the Document Signing list with "Sign on This Device" offered
            # again, and a second pass through just that document is what
            # actually registers it.
            for sign_pass in range(3):
                if sign_pass > 0:
                    if not self._documents_left_to_sign(sign_button):
                        return
                    sign_button.click()
                self._sign_documents_in_widget(initials)

    @log_method_exceptions
    def _documents_left_to_sign(self, sign_button: Locator) -> bool:
        ready_to_sign = self.page.get_by_text("Ready to sign")
        return (
            ready_to_sign.count() > 0
            and ready_to_sign.first.is_visible()
            and sign_button.is_visible()
        )

    @log_method_exceptions
    def _click_within(self, locator: Locator, timeout: float = 5000) -> bool:
        # Confirmed live (2026-09-11, stage): right after a document is
        # finalized, the next one can stay non-interactable for a while -
        # a click that had just passed its own actionability check still
        # sat out Playwright's full default timeout. A short timeout plus a
        # fresh look on the caller's next loop iteration recovers from that
        # instead of failing the whole signing flow.
        try:
            locator.click(timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False

    @log_method_exceptions
    def _sign_next_field(self, initials: str) -> bool:
        # Confirmed live (2026-09-11, stage): a signed field keeps its
        # "signature"/"initials" class and only gains "signed" - matching
        # on "signature" alone kept re-signing the first, already-signed
        # field forever and never reached an initials one. Only the first
        # unsigned field that's clickable right now is taken: one scrolled
        # out of the widget's own (non-page) scroll area isn't, and "Start
        # Signing"/"Next" (see _sign_documents_in_widget) is what brings it
        # into view instead.
        agreement_frame = self._signing_frame()
        unsigned_field = agreement_frame.locator(
            "img.replaced-text:not(.signed)"
        )
        if unsigned_field.count() == 0:
            return False
        try:
            unsigned_field.first.click(trial=True, timeout=waits().tiny)
        except PlaywrightTimeoutError:
            return False
        field_id = unsigned_field.first.get_attribute("data-id")
        signed_field = agreement_frame.locator(
            f'img.replaced-text.signed[data-id="{field_id}"]'
        )
        if not self._click_within(
            agreement_frame.locator(f'img.replaced-text[data-id="{field_id}"]')
        ):
            return False

        signature_input = agreement_frame.locator("input.signature-input")
        accept_button = agreement_frame.get_by_role(
            "button", name="Accept and sign", exact=True
        )
        # Confirmed live: the adopt-signature modal only opens for some
        # fields (seen on the first field of most documents) - the rest
        # sign straight away on click with no modal at all, so wait for
        # whichever of the two actually happens.
        for _ in range(40):
            if signed_field.count() > 0:
                return True
            if signature_input.count() > 0 and signature_input.first.is_visible():
                if not signature_input.first.input_value():
                    signature_input.first.fill(initials)
                for attempt in range(5):
                    self._click_within(accept_button)
                    try:
                        expect(signature_input).to_be_hidden(timeout=waits().tiny)
                        break
                    except AssertionError:
                        if attempt == 4:
                            raise
                expect(signed_field).to_have_count(1, timeout=self.timeout)
                return True
            self.page.wait_for_timeout(waits().poll_interval)
        return False

    @log_method_exceptions
    def _sign_documents_in_widget(self, initials: str) -> None:
        agreement_frame = self._signing_frame()
        # Only tried when no field is signable right now, in this order.
        # "Start Signing" goes last: it stays on screen until the
        # document's first field is signed (confirmed live), so preferring
        # it re-clicked it forever. "Continue" is the whole UI of a
        # document with no fields (see sign_documents_on_this_device).
        navigation_buttons = [
            agreement_frame.get_by_role("button", name="Next", exact=True),
            agreement_frame.get_by_role("button", name="Finalize Document"),
            agreement_frame.get_by_role("button", name="Continue", exact=True),
            agreement_frame.get_by_role("button", name="Start Signing", exact=True),
        ]
        # Same completion text as assert_lease_completed.
        lease_completed = self.page.get_by_text(
            re.compile(
                r"Success! The lease has been completed\.|"
                r"Your lease has been finalized!"
            )
        )
        idle_checks = 0
        # Safety cap, not a real count - Hamilton County's 6-document set
        # took roughly 25 actions in total.
        for _ in range(300):
            if lease_completed.count() > 0:
                return
            if self._sign_next_field(initials):
                idle_checks = 0
                continue
            if any(
                button.count() > 0
                and button.first.is_visible()
                and self._click_within(button.first)
                for button in navigation_buttons
            ):
                idle_checks = 0
                self.page.wait_for_timeout(1000)
                continue
            # Nothing actionable: either the next document (a large
            # base64-rendered page) is still loading, or the widget has
            # closed - only the latter lasts this long.
            idle_checks += 1
            if idle_checks >= 15:
                return
            self.page.wait_for_timeout(1000)

    @log_method_exceptions
    def complete_move_in_checklist_and_finalize(self) -> None:
        # Old Robot suite's "Complete Movein Checklist" + "Complete Finalize
        # Step". Confirmed live (2026-09-11, uat_storoutlet/Bellflower): once
        # documents are signed and payment taken, that property still waits
        # on a "Move-In Checklist" section (one checkbox per configured item)
        # and a bottom-bar "Finalize" button that stays disabled until every
        # item is checked - no completion message until then. Stage's
        # properties complete right after signing instead, so this only
        # acts when a Finalize button shows up before the completion text.
        with allure.step("Complete move-in checklist and finalize"):
            finalize_button = self.page.get_by_role(
                "button", name="Finalize", exact=True
            )
            # Same completion text as assert_lease_completed.
            lease_completed = self.page.get_by_text(
                re.compile(
                    r"Success! The lease has been completed\.|"
                    r"Your lease has been finalized!"
                )
            )
            expect(finalize_button.or_(lease_completed).first).to_be_visible(
                timeout=self.timeout
            )
            if lease_completed.count() > 0 and lease_completed.first.is_visible():
                return

            checklist_items = (
                self.page.locator(".v-expansion-panel")
                .filter(
                    has=self.page.get_by_role(
                        "button", name="Move-In Checklist", exact=True
                    )
                )
                .get_by_role("checkbox")
            )
            for index in range(checklist_items.count()):
                item = checklist_items.nth(index)
                # Confirmed live (2026-09-11, Bellflower): the checklist sits
                # at the bottom of the drawer, and a raw mouse click at the
                # checkbox's own coordinates (_mouse_click, as the Notice
                # Delivery radio uses) landed on the bottom action bar
                # (.hb-bab-wrapper) overlapping it instead. A locator click on
                # the control's ripple div - where Vuetify binds the handler -
                # gets Playwright's scroll-into-view and obscured-element
                # checks, and is what actually ticked it.
                ripple = item.locator(
                    "xpath=ancestor::*[contains(@class,"
                    "'v-input--selection-controls__input')][1]"
                    "//*[contains(@class,'v-input--selection-controls__ripple')]"
                ).first
                for attempt in range(3):
                    if item.is_checked():
                        break
                    ripple.click()
                    try:
                        expect(item).to_be_checked(timeout=waits().short)
                        break
                    except AssertionError:
                        if attempt == 2:
                            raise

            expect(finalize_button).to_be_enabled(timeout=self.timeout)
            # Confirmed live (2026-09-11, uat_storoutlet/Bellflower): by the
            # time this click was attempted, Finalize was already showing its
            # loading spinner (v-btn--loading), whose inner span swallowed
            # the click for the full timeout - yet the lease went on to
            # complete. A click that can't land isn't a failure by itself;
            # assert_lease_completed, which callers run next, is the check
            # that actually matters.
            try:
                finalize_button.click(timeout=waits().medium)
            except PlaywrightTimeoutError:
                pass

            # The old suite's Complete Finalize Step also confirmed an
            # optional warning for a move-in date outside the invoice
            # threshold period (its button name was "...-Contine") - not
            # seen live yet, so only answered if it actually appears.
            threshold_warning = self.page.get_by_text(
                re.compile("outside the invoice threshold period")
            )
            try:
                expect(threshold_warning.or_(lease_completed).first).to_be_visible(
                    timeout=waits().medium
                )
            except AssertionError:
                return
            if threshold_warning.count() > 0 and threshold_warning.first.is_visible():
                self.page.get_by_role(
                    "button", name=re.compile(r"^Contin")
                ).first.click()

    @log_method_exceptions
    def finish_and_close(self) -> None:
        with allure.step("Finish and close"):
            finish_button = self.page.get_by_role(
                "button", name="Finish and Close", exact=True
            )
            expect(finish_button).to_be_visible(timeout=self.timeout)
            finish_button.click()

    @log_method_exceptions
    def assert_lease_completed(self) -> None:
        # Confirmed live (2026-09-11, stage): the completion message text
        # itself varies with which document-signing path was taken (see
        # sign_documents_on_this_device) - the multi-field widget shows
        # "Success! The lease has been completed.", the single "I Agree"
        # path (e.g. Rutland's "Superlease") instead shows "Your lease
        # has been finalized!".
        with allure.step("Verify the lease was finalized"):
            expect(
                self.page.get_by_text(
                    re.compile(
                        r"Success! The lease has been completed\.|"
                        r"Your lease has been finalized!"
                    )
                )
            ).to_be_visible(timeout=self.timeout)
