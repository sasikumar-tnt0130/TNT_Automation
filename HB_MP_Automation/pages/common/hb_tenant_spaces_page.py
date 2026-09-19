import re
from datetime import date, datetime, timedelta

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


class HBTenantSpacesPage:
    """Tenant details page's space actions: add another space (and lease)
    for an existing tenant. Ported from the old Robot Framework smoke
    suite's "Open Tenant And Add Multiple Space And Lease" keyword -
    confirmed live (2026-09-11, uat_storoutlet/Bellflower) that "Add Space"
    now lives in the tenant page's bottom action bar (that suite's
    expansion-panel button and its separate "Select Space" link are gone)
    and opens the same Tenant Onboarding drawer HBQuickLaunchPage drives,
    already on its Space List.

    open_tenants/open_tenant_details are the same live-verified mechanics
    as HBTenantDocumentsPage's."""

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
    def open_tenants(self, property_name: str) -> None:
        with allure.step(f"Open tenants for {property_name}"):
            self._ensure_main_shell_for_property_nav()
            self._close_live_agent_notification()
            search_box = self.page.locator("#search-box")
            expect(search_box).to_be_visible(timeout=self.timeout)
            search_box.click()
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
                property_cell.locator("xpath=ancestor::tr[1]").dispatch_event(
                    "click"
                )
            # Wait until the dashboard header names the property (as
            # HBQuickLaunchPage._select_property does): seen 2026-09-14, a run
            # went on to Tenants with the picker still on "Company (7
            # Properties Selected)", where HB ignored the communication filters.
            expect(
                self.page.get_by_role(
                    "textbox", name=re.compile(re.escape(property_name))
                )
            ).to_be_visible(timeout=self.timeout)
            tenants_link = self.page.get_by_role("complementary").get_by_text(
                "Tenants", exact=True
            )
            expect(tenants_link).to_be_visible(timeout=self.timeout)
            tenants_link.locator(
                "xpath=ancestor::*[@role='listitem'][1]"
            ).dispatch_event("click")
            self._close_live_agent_notification()

    def _ensure_main_shell_for_property_nav(self) -> None:
        """Leave Settings / active dialogs so ``#search-box`` is clickable.

        Shared ``hb_admin_session`` often remains in Settings after signing;
        ``#search-box`` can still resolve under the overlay and time out on
        click (live 2026-09-18 legacy_superlease HB validation).
        """
        from urllib.parse import urlparse

        dialog = self.page.locator(".v-dialog__content--active").first
        for _ in range(3):
            if dialog.count() == 0 or not dialog.is_visible():
                break
            self.page.keyboard.press("Escape")
            try:
                expect(dialog).to_be_hidden(timeout=waits().short)
            except AssertionError:
                close = dialog.locator(
                    'button[name="QA-v-card-HbIcon-mdi-close"]'
                )
                if close.count() > 0 and close.first.is_visible():
                    close.first.click(force=True)
        settings_open = False
        try:
            settings_open = self.page.get_by_role(
                "textbox", name="Filter"
            ).is_visible(timeout=500)
        except Exception:
            settings_open = False
        if settings_open or (
            dialog.count() > 0 and dialog.is_visible()
        ):
            parsed = urlparse(self.page.url or "")
            if parsed.scheme and parsed.netloc:
                self.page.goto(
                    f"{parsed.scheme}://{parsed.netloc}/dashboard",
                    wait_until="domcontentloaded",
                )

    @log_method_exceptions
    def open_tenant_details(self, first_name: str, last_name: str) -> None:
        full_name = f"{first_name} {last_name}"
        with allure.step(f"Open tenant details for {full_name}"):
            search_tenants = self.page.get_by_role(
                "textbox", name="Search Tenants", exact=True
            )
            expect(search_tenants).to_be_visible(timeout=self.timeout)
            search_tenants.fill(full_name)
            self.page.keyboard.press("Enter")
            tenant_cell = self.page.get_by_role(
                "gridcell", name=full_name, exact=True
            )
            expect(tenant_cell).to_be_visible(timeout=self.timeout)
            tenant_cell.click()
            expect(
                self.page.get_by_text(full_name, exact=True).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_web_rental_tenant(
        self,
        guest_name: str,
        space_number: str,
        move_in_date: date,
        amount_paid: float,
        card_last4: str | None = None,
        ach_last4: str | None = None,
        no_autopay: bool = False,
    ) -> None:
        """Old Robot suite's 8885 "Verify rental in HB PMS". The autopay note
        reads "Payment Method ach ****6667 was set as default autopay method"
        for an ACH autopay (confirmed live 2026-09-14, Bellflower); with
        no_autopay, no such note may show. Confirmed live
        (2026-09-13, uat_storoutlet/Chula Vista): Search Tenants matches
        names, not emails; a storefront rental's row reads "#<space> <name>
        <phone> <Move In> ... Current ... $0.00 (Total Past Due) Website
        Application (Moved In By) ..."; the tenant page shows "Prepaid
        Balance $<paid>" and, with autopay, the communication "Payment
        Method card ****<last4> was set as default autopay method". Every
        storefront guest shares one name, so the row is matched on the
        space number too."""
        date_pattern = rf"{move_in_date:%b} 0?{move_in_date.day}, {move_in_date.year}"
        with allure.step(f"Verify tenant row: {guest_name}, space {space_number}"):
            self._close_live_agent_notification()
            row = self._tenant_row_by_space(space_number, guest_name)
            expect(row).to_contain_text("Current")
            expect(row).to_contain_text(re.compile(date_pattern))
            # Stage's Tenants grid has no "Moved In By" column (2026-09-15:
            # "#BGed51 Auto Tester ... Current $0.00 ... 213 Barre Paxton Rd")
            # - the origin is checked only where the grid shows it.
            if self.page.get_by_role("columnheader", name=re.compile(r"Moved In By", re.I)).count() > 0:
                expect(row).to_contain_text("Website Application")
            else:
                allure.attach(
                    "This Tenants grid has no 'Moved In By' column - 'Website Application' not checked",
                    name="moved in by", attachment_type=allure.attachment_type.TEXT,
                )
            expect(row).to_contain_text("$0.00")

        with allure.step("Verify tenant page: prepaid rental and autopay"):
            self._open_tenant_from_row(row, space_number, guest_name)
            self._assert_payment_landed(amount_paid, min_paid_through=move_in_date)
            body = self.page.locator("body")
            for method, last4 in (("card", card_last4), ("ach", ach_last4)):
                if not last4:
                    continue
                # \s+, not single spaces: to_contain_text matches textContent,
                # where this note reads "card  ****1111 was set..." (two
                # spaces - confirmed from a 2026-09-13 run's failure output).
                expect(body).to_contain_text(
                    re.compile(
                        rf"{method}\s+\*+{re.escape(last4)}\s+was set as default autopay method"
                    ),
                    timeout=self.timeout,
                )
            if no_autopay:
                expect(body).not_to_contain_text(
                    re.compile(r"was set as default autopay method")
                )

    @log_method_exceptions
    def _tenant_row_by_space(self, space_number: str, guest_name: str):
        """The Tenants row of a storefront rental, found by its space number
        (user suggestion 2026-09-15): every storefront guest is "Auto Tester"
        ("Auto Tester Business" when renting as a business), the space is
        unique. The search matches space numbers as substrings ("0010" also
        listed #0010C - confirmed live 2026-09-15), so the row is pinned by
        its exact "#space" cell, and the guest's name is then checked as the
        row's content - never another tenant's space. The list can reload
        after the search and wipe it (see HBTenantNotesPage.open_tenant),
        hence the re-searches."""
        search_tenants = self.page.get_by_role("textbox", name="Search Tenants", exact=True)
        expect(search_tenants).to_be_visible(timeout=self.timeout)
        row = (
            self.page.get_by_role("row")
            .filter(has=self.page.get_by_text(f"#{space_number}", exact=True))
            .first
        )
        for attempt in range(3):
            search_tenants.fill(space_number)
            self.page.keyboard.press("Enter")
            try:
                expect(row).to_be_visible(timeout=waits().long)
                break
            except AssertionError:
                if attempt == 2:
                    raise
        expect(row).to_contain_text(guest_name)
        return row

    @log_method_exceptions
    def _open_tenant_from_row(self, row, space_number: str, guest_name: str) -> None:
        """Clicks the row's "#space" cell, which opens the tenant page
        (confirmed live 2026-09-15), re-finding the row once if the list
        reloaded under the click."""
        for attempt in range(2):
            try:
                row.get_by_role("gridcell").filter(
                    has=self.page.get_by_text(f"#{space_number}", exact=True)
                ).first.click(timeout=waits().long)
                expect(self.page).to_have_url(re.compile(r"/contacts/[^/?#]+"), timeout=waits().long)
                return
            except Exception:
                if attempt == 1:
                    raise
                row = self._tenant_row_by_space(space_number, guest_name)

    @log_method_exceptions
    def open_take_payment(self) -> None:
        """Old Robot suite's "Take A Payment From Tenants Page" (8916).
        Confirmed live (2026-09-13, uat_storoutlet/Bellflower): the button
        now sits in the tenant page's bottom action bar (Robot's
        expansion-panel button is gone) and opens the same Take a Payment
        drawer as Quick Launch - drive the drawer with HBQuickLaunchPage."""
        with allure.step("Take a payment from the tenants page"):
            self._close_live_agent_notification()
            take_payment = self.page.locator(
                'button[name="QA-HbBottomActionBar-hb-primary-button-Take-a-Payment"]'
            )
            expect(take_payment).to_be_visible(timeout=self.timeout)
            take_payment.click()
            expect(
                self.page.get_by_role("button", name="Process Payment", exact=True)
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _parse_lease_balance(self) -> dict:
        text = self.page.locator("body").inner_text()
        prepaid = re.search(r"Prepaid Balance\s*\$([\d,]+\.\d{2})", text)
        due = re.search(r"Total Balance Due\s*\$([\d,]+\.\d{2})", text)
        through = re.search(r"Paid Through Date\s*([A-Z][a-z]{2} \d{1,2}, \d{4})", text)
        return {
            "prepaid": float(prepaid.group(1).replace(",", "")) if prepaid else None,
            "balance_due": float(due.group(1).replace(",", "")) if due else None,
            "paid_through": (
                datetime.strptime(through.group(1), "%b %d, %Y").date() if through else None
            ),
        }

    @log_method_exceptions
    def read_lease_balance(self, changed_from: dict | None = None) -> dict:
        """The tenant page's space figures (Prepaid Balance, Total Balance
        Due, Paid Through Date) once they've rendered and held for 3 s - the
        page first shows "Loading..." and interim figures. Pass the reading
        taken before a payment as changed_from to wait for the page to show
        new figures, rather than settle on the pre-payment ones (confirmed
        live 2026-09-13: they update within about a second of the receipt's
        Finish and Close)."""
        with allure.step("Read the tenant page balance"):
            readings: list[dict] = []
            for _ in range(int(self.timeout / 500)):
                current = self._parse_lease_balance()
                readings.append(current)
                if (
                    current["prepaid"] is not None
                    and current["paid_through"] is not None
                    and current != changed_from
                    and len(readings) >= 6
                    and all(earlier == current for earlier in readings[-6:])
                ):
                    allure.attach(
                        repr(current), name="tenant balance", attachment_type=allure.attachment_type.TEXT
                    )
                    return current
                self.page.wait_for_timeout(waits().poll_interval)
            raise AssertionError(
                f"Tenant page balance never settled"
                f"{' on new figures' if changed_from else ''}: {readings[-1] if readings else None}"
            )

    @log_method_exceptions
    def _assert_payment_landed(self, amount: float, min_paid_through: date) -> None:
        """Passes on either state HB shows a storefront payment in (user
        choice 2026-09-13, after a uat_storoutlet run found the $36.80
        rental already applied to rent - Paid Through Sep 30, Prepaid
        $0.00): still held as credit ("Prepaid Balance $<amount>"), or
        already applied ("Total Balance Due $0.00" and a "Paid Through Date"
        on or after min_paid_through). The tenant page first shows
        "Loading..." and interim figures, so it's re-read until a state holds
        and nothing has changed for 3 s. Attaches which state it was."""
        with allure.step(f"Verify HB shows the ${amount:,.2f} payment"):
            readings: list[dict] = []
            for _ in range(int(self.timeout / 500)):
                current = self._parse_lease_balance()
                readings.append(current)
                held = current["prepaid"] == round(amount, 2)
                applied = (
                    current["balance_due"] == 0
                    and current["paid_through"] is not None
                    and current["paid_through"] >= min_paid_through
                )
                if (held or applied) and len(readings) >= 6 and all(
                    earlier == current for earlier in readings[-6:]
                ):
                    state = "held as prepaid credit" if held else "already applied to rent"
                    allure.attach(
                        f"${amount:,.2f} {state}: {current}",
                        name="HB payment state",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    return
                self.page.wait_for_timeout(waits().poll_interval)
            raise AssertionError(
                f"HB shows neither Prepaid Balance ${amount:,.2f} nor a $0.00 balance paid "
                f"through {min_paid_through:%b %d, %Y} or later: {readings[-1] if readings else None}"
            )

    @log_method_exceptions
    def assert_autopay_cancelled_and_reenrolled(
        self, guest_name: str, space_number: str, prepaid_balance: float, card_last4: str
    ) -> None:
        """HB evidence for the storefront My Account 8862/8860/8861 flow -
        confirmed live (2026-09-13, uat_storoutlet/Chula Vista): the
        tenant's Communication log gets "Payment Method card ****<last4>
        was removed as default autopay method." on cancel and another
        "...was set as default autopay method." on re-enrolment (the first
        is from the rental itself), and Prepaid Balance includes the My
        Account payment (live: $112.40 rental + $170.00 = $282.40)."""
        with allure.step(f"Open tenant {guest_name}, space {space_number}"):
            self._close_live_agent_notification()
            self._open_tenant_from_row(
                self._tenant_row_by_space(space_number, guest_name), space_number, guest_name
            )

        with allure.step("Verify prepaid balance and autopay cancel/re-enrol notes"):
            # With a month paid ahead, rent that HB has already applied runs
            # past this month's end - so at least into next month.
            next_month = (date.today().replace(day=1) + timedelta(days=32)).replace(day=1)
            self._assert_payment_landed(prepaid_balance, min_paid_through=next_month)
            body = self.page.locator("body")
            last4 = re.escape(card_last4)
            expect(body).to_contain_text(
                re.compile(rf"card\s+\*+{last4}\s+was removed as default autopay method"),
                timeout=self.timeout,
            )
            set_notes = self.page.get_by_text(
                re.compile(rf"card\s+\*+{last4}\s+was set as default autopay method")
            )
            for _ in range(int(self.timeout / 1000)):
                if set_notes.count() >= 2:
                    break
                self.page.wait_for_timeout(1000)
            assert set_notes.count() >= 2, (
                f"Expected the rental's and the re-enrolment's 'was set as default autopay "
                f"method' notes, found {set_notes.count()}"
            )

    @log_method_exceptions
    def gate_access_code(self, guest_name: str, space_number: str) -> str:
        """The old Robot suite's Gate Access read (part of 8885, used by
        8907's "Link a space"). Confirmed live (2026-09-13, uat_storoutlet):
        a storefront rental gets an active access code straight away, even
        with ID verified later - the tenant's Gate Access page
        (/contacts/<id>/gate-access) lists "<facility address> | <space> |
        Default Area | <code> | Active | <date>"; the code is the cell
        that's only digits (the address cell also starts with a number)."""
        with allure.step(f"Read the gate access code for {guest_name}, space {space_number}"):
            self._close_live_agent_notification()
            self._open_tenant_from_row(
                self._tenant_row_by_space(space_number, guest_name), space_number, guest_name
            )
            origin = re.match(r"https?://[^/]+", self.page.url).group(0)
            contact_id = re.search(r"/contacts/([^/?#]+)", self.page.url).group(1)
            gate_access_url = f"{origin}/contacts/{contact_id}/gate-access"
            access_row = self.page.locator("tbody tr").filter(has_text=space_number).first
            # Confirmed live (2026-09-13): some rentals show "Access not yet
            # active" / "Pre-Access" with no code at first (space O16), while
            # others (BGAT_ spaces) had an Active code from the rental's own
            # time - so the row is re-read for a while before giving up
            # (user choice: wait, then fail clearly).
            wait_seconds = 300
            row_text = ""
            for attempt in range(wait_seconds // 15 + 1):
                if attempt:
                    self.page.wait_for_timeout(15000)
                self.page.goto(gate_access_url, wait_until="domcontentloaded")
                expect(access_row).to_be_visible(timeout=self.timeout)
                row_text = re.sub(r"\s+", " ", access_row.inner_text()).strip()
                codes = [
                    cell.strip()
                    for cell in access_row.locator("td").all_inner_texts()
                    if re.fullmatch(r"\d{4,8}", cell.strip())
                ]
                if codes and re.search(r"\bActive\b", row_text):
                    allure.attach(row_text, name="gate access row", attachment_type=allure.attachment_type.TEXT)
                    return codes[0]
            raise AssertionError(
                f"No active gate access code for space {space_number} after {wait_seconds}s "
                f"(Gate Access row: {row_text!r}) - HB hasn't activated this space's access"
            )

    @log_method_exceptions
    def open_storefront_tenant(self, guest_name: str, space_number: str) -> None:
        """Opens a storefront rental's tenant page. Every storefront guest
        shares one name, so the Tenants row is matched on the space number
        too - exactly, via the space cell's own "#<space>" text (a plain
        substring "#OP1" also hits "#OP12", and a row's textContent runs the
        cells together - "#OP1Auto Tester" - so a word-boundary regex on the
        row misses it; confirmed 2026-09-13)."""
        with allure.step(f"Open tenant {guest_name}, space {space_number}"):
            self._close_live_agent_notification()
            self._open_tenant_from_row(
                self._tenant_row_by_space(space_number, guest_name), space_number, guest_name
            )
            expect(
                self.page.get_by_text(f"Space {space_number}", exact=True).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_business_holds_spaces(
        self, business_name: str, space_numbers: list[str]
    ) -> None:
        """C64723 / C66593. Confirmed live (2026-09-16, stage/Hamilton County):
        a second storefront RAB rental with the same business email adds another
        Current Tenants row under the business name (email search finds nothing;
        business-name search lists one row per space). Opening either contact
        shows every `Space <n>` heading on the same tenant page - one contact,
        one lease per space, same business profile."""
        if len(space_numbers) < 2:
            raise AssertionError("assert_business_holds_spaces needs at least two spaces")
        with allure.step(f"Verify tenants grid: {business_name} has rows for {', '.join(space_numbers)}"):
            self._close_live_agent_notification()
            for space_number in space_numbers:
                row = self._tenant_row_by_space(space_number, business_name)
                expect(row).to_contain_text("Current")
                expect(row).to_contain_text(business_name)

        anchor = space_numbers[0]
        with allure.step(
            f"Verify tenant contact opened from {anchor} lists every rented space"
        ):
            self.open_storefront_tenant(business_name, anchor)
            body = self.page.locator("body")
            expect(body).to_contain_text(business_name)
            for space_number in space_numbers:
                expect(
                    self.page.get_by_text(f"Space {space_number}", exact=True).first
                ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def remove_autopay(self, space_number: str) -> None:
        """Old Robot Mariposa ReservationAndRentals suite's "Remove Card
        Details". Confirmed live (2026-09-13, uat_storoutlet/Chula Vista,
        OP1): Space Settings & Information -> Billing shows "AutoPay <name>
        VISA *1111 ..." with a menu button whose only entry is "Remove from
        AutoPay" (Robot's trash icon is gone) -> "Are you sure you want to
        remove the AutoPay payment method?" -> Remove -> "AutoPay payment
        method has been successfully removed.", after which the block reads
        "AutoPay Click to Add"."""
        with allure.step(f"Remove the AutoPay card for space {space_number}"):
            self._close_live_agent_notification()
            heading = self.page.get_by_text(f"Space {space_number}", exact=True).first
            expect(heading).to_be_visible(timeout=self.timeout)
            billing = self.page.locator("button").filter(
                has_text=re.compile(r"^\s*Billing\s*(keyboard_arrow_down)?\s*$")
            ).first
            if not billing.is_visible():
                heading.locator(
                    "xpath=following::button"
                    "[contains(normalize-space(.), 'Space Settings & Information')][1]"
                ).click()
            expect(billing).to_be_visible(timeout=self.timeout)
            autopay_label = self.page.locator("span, div, p").filter(
                has_text=re.compile(r"^\s*AutoPay\s*$")
            ).first
            if not autopay_label.is_visible():
                billing.click()
            expect(autopay_label).to_be_visible(timeout=self.timeout)
            billing_panel = autopay_label.locator(
                "xpath=ancestor::*[contains(@class,'v-expansion-panel')][1]"
            )
            autopay_block = autopay_label.locator(
                "xpath=ancestor::*[.//button[@name='QA-v-menu-HbIcon-mdi-dots-vertical']][1]"
            )
            autopay_block.locator('button[name="QA-v-menu-HbIcon-mdi-dots-vertical"]').first.click()
            self.page.locator(
                ".v-menu__content.menuable__content__active [role=menuitem]"
            ).filter(has_text="Remove from AutoPay").first.click()
            remove = self.page.locator(
                '.v-dialog--active button[name="QA-HbBottomActionBar-hb-destructive-button-Remove"]'
            ).last
            expect(remove).to_be_visible(timeout=self.timeout)
            remove.click()
            expect(
                self.page.get_by_text("AutoPay payment method has been successfully removed").first
            ).to_be_visible(timeout=self.timeout)
            expect(billing_panel).to_contain_text(
                re.compile(r"AutoPay\s*Click to Add"), timeout=self.timeout
            )

    @log_method_exceptions
    def start_add_space(self) -> None:
        with allure.step("Add space"):
            add_space = self.page.get_by_role("button", name="Add Space", exact=True)
            expect(add_space).to_be_visible(timeout=self.timeout)
            add_space.click()
            # Lands directly on the onboarding drawer's Space List (same grid
            # HBQuickLaunchPage._select_first_available_space picks from).
            expect(
                self.page.get_by_role(
                    "row", name="Press SPACE to select this row."
                ).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def start_transfer(self) -> None:
        # Old Robot suite's "Select Transfer Menu On Space". Confirmed live
        # (2026-09-11, Bellflower): the tenant page has several identical
        # "⋮" buttons (QA-v-menu-HbIcon-mdi-dots-vertical) - the tenant's own
        # menu, the space's menu and the grid's Download/Filter one - and only
        # the space's offers "Transfer". Each is opened in turn until that
        # item shows; the others are toggled closed again.
        with allure.step("Select transfer menu on space"):
            transfer_item = self.page.get_by_role(
                "menuitem", name="Transfer", exact=True
            )
            menus = self.page.locator(
                'button[name="QA-v-menu-HbIcon-mdi-dots-vertical"]'
            )
            expect(menus.first).to_be_visible(timeout=self.timeout)
            for index in range(menus.count()):
                menu = menus.nth(index)
                if not menu.is_visible():
                    continue
                menu.click()
                try:
                    expect(transfer_item).to_be_visible(timeout=waits().tiny)
                except AssertionError:
                    menu.click()
                    self.page.wait_for_timeout(waits().poll_interval)
                    continue
                transfer_item.click()
                expect(self.page.locator("input#reason")).to_be_attached(
                    timeout=self.timeout
                )
                return
            raise AssertionError("No space menu offering 'Transfer' was found")

    @log_method_exceptions
    def setup_transfer(self, reason: str = "Space is too far away") -> str:
        # Old Robot suite's "Setup Transfer": a reason, then the space to
        # transfer into. Returns that space's number (e.g. "#0020").
        with allure.step(f"Set up transfer: {reason}"):
            # Same Vuetify select as HBQuickLaunchPage.
            # select_all_spaces_for_payment's Add Additional Time: clicking
            # the enclosing .v-select__slot is what opens it.
            self.page.locator("input#reason").locator(
                "xpath=ancestor::*[contains(@class,'v-select__slot')][1]"
            ).first.click()
            reason_option = self.page.get_by_role("option", name=reason, exact=True)
            expect(reason_option).to_be_visible(timeout=self.timeout)
            reason_option.click()

            rows = self.page.get_by_role("row", name="Press SPACE to select this row.")
            expect(rows.first).to_be_visible(timeout=self.timeout)
            space_number = None
            for index in range(rows.count()):
                row = rows.nth(index)
                number = row.locator("[role='gridcell']").first.inner_text().split()[0]
                # Parking spaces ("Pa..."), same exclusion as
                # HBQuickLaunchPage.move_in_first_available_space.
                if number.lstrip("#").lower().startswith("pa"):
                    continue
                row.click()
                space_number = number
                break
            if space_number is None:
                raise AssertionError("No non-parking space available to transfer into")
            expect(
                self.page.get_by_role("button", name="Take Payment", exact=True)
            ).to_be_enabled(timeout=self.timeout)
            return space_number

    @log_method_exceptions
    def _drawer_text(self) -> str:
        return self.page.locator(
            ".v-navigation-drawer--temporary.v-navigation-drawer--open"
        ).first.inner_text()

    @log_method_exceptions
    def _amount_after(self, label: str) -> float:
        match = re.search(
            re.escape(label) + r"\s*-?\(?\$([\d,]+\.\d{2})\)?", self._drawer_text()
        )
        if match is None:
            raise AssertionError(f"No amount found after {label!r}")
        return float(match.group(1).replace(",", ""))

    @log_method_exceptions
    def take_transfer_payment(self) -> float:
        # Old Robot suite's "Payment For Transfer". Confirmed live: when the
        # credit left on the old space covers the new one (Transfer Out
        # Balance -$237.50 vs Transfer In Balance $116.00) Total Payment is
        # $0.00 and the transfer confirms with no payment at all. When
        # something is due, Cash is selected - same reason as the other HB
        # tests on uat_storoutlet (its card form is missing its payment
        # gateway API key); that branch follows pay_by_cash's radio
        # handling and hasn't been seen live on this screen yet.
        with allure.step("Make payment for transfer"):
            self.page.get_by_role("button", name="Take Payment", exact=True).click()
            expect(
                self.page.get_by_role("button", name="Confirm Transfer", exact=True)
            ).to_be_visible(timeout=self.timeout)
            # Confirmed live: Confirm Transfer is already in the bottom bar
            # while the Payment step's own panel is still loading (spinner,
            # no totals yet) - wait for the totals themselves before reading.
            expect(self.page.get_by_text("Total Payment:").first).to_be_visible(
                timeout=self.timeout
            )
            total_payment = self._amount_after("Total Payment:")
            if total_payment > 0:
                cash_option = self.page.get_by_role("radiogroup").get_by_role(
                    "button", name="Cash", exact=True
                )
                cash_radio = cash_option.get_by_role("radio", name="Cash", exact=True)
                expect(cash_option).to_be_visible(timeout=self.timeout)
                if not cash_radio.is_checked():
                    cash_option.click()
                    expect(cash_radio).to_be_checked(timeout=self.timeout)
            return total_payment

    @log_method_exceptions
    def confirm_transfer(self) -> None:
        with allure.step("Confirm transfer"):
            self.page.get_by_role("button", name="Confirm Transfer", exact=True).click()
            # Confirmed live: an "Execute Transfer" dialog ("...you will be
            # executing the transfer and the space your tenant is going to
            # transfer out of will be immediately put back...") is where the
            # transfer actually happens - nothing moves until it's confirmed.
            execute_dialog = self.page.locator(".v-dialog--active").filter(
                has_text="Execute Transfer"
            )
            finalize_transfer = self.page.get_by_role(
                "button", name="Finalize Transfer", exact=True
            )
            expect(execute_dialog.or_(finalize_transfer).first).to_be_visible(
                timeout=self.timeout
            )
            if execute_dialog.count() > 0 and execute_dialog.first.is_visible():
                execute_dialog.get_by_role("button", name="Confirm", exact=True).click()
            expect(finalize_transfer).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _receipt_finish_button(self):
        return self.page.locator(
            'button[name="QA-TransferReceipt-hb-primary-button-Finish-and-Close"]'
        )

    @log_method_exceptions
    def finalize_transfer(self) -> None:
        # End of the old suite's "Sign Lease For Transfer". Its "Please select
        # which document(s) need to be signed..." prompt is gone - confirmed
        # live that the step now shows the regular lease Document Signing
        # panel, so callers sign with HBQuickLaunchPage.
        # sign_documents_on_this_device first; Finalize Transfer stays
        # disabled until that's done.
        with allure.step("Finalize transfer"):
            finalize = self.page.get_by_role(
                "button", name="Finalize Transfer", exact=True
            )
            expect(finalize).to_be_enabled(timeout=self.timeout)
            finalize.click()
            expect(self._receipt_finish_button()).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def transfer_receipt(self, expected_space: str | None = None) -> dict:
        """Old Robot suite's "Verify Transfer Invoice" (its own balance
        assertions were already commented out there): the Transfer
        Receipt's amounts, plus its full text for the caller's checks.
        expected_space (e.g. "#0020"), when given, is also waited for."""
        with allure.step("Verify transfer invoice"):
            expect(self.page.get_by_text("Transfer Receipt").first).to_be_visible(
                timeout=self.timeout
            )
            # Confirmed live: the receipt first renders as an empty shell
            # ("Transfer Date:" with no date, "Charges N/A", every amount
            # $0.00) and fills in a moment later. The amounts can't signal
            # readiness ($0.00 is a legitimate value), so wait for the
            # transfer date - and the new space, if known - instead.
            drawer = self.page.locator(
                ".v-navigation-drawer--temporary.v-navigation-drawer--open"
            ).first
            expect(drawer).to_contain_text(
                re.compile(r"Transfer Date:\s*[A-Z][a-z]{2} \d{1,2}, \d{4}"),
                timeout=self.timeout,
            )
            if expected_space:
                expect(drawer).to_contain_text(
                    expected_space.lstrip("#"), timeout=self.timeout
                )
            receipt = {
                label: self._amount_after(label)
                for label in (
                    "Total Due",
                    "Transfer Out Balance Applied",
                    "Payment Amount",
                    "Balance Remaining",
                )
            }
            receipt["text"] = self._drawer_text()
            return receipt

    @log_method_exceptions
    def finish_transfer(self) -> None:
        # Old Robot suite's "Finalize Transfer" keyword.
        with allure.step("Finalize transfer screen: finish and close"):
            self._receipt_finish_button().click()
            expect(self._receipt_finish_button()).to_be_hidden(timeout=self.timeout)
