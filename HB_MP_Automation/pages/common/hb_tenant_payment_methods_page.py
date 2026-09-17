import re

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_ach_form import fill_ach_details
from common_utils.waits import waits


class HBTenantPaymentMethodsPage:
    """Tenant details "Payment Methods" page: add a saved payment method to
    a tenant's record. Ported from the old Robot Framework smoke suite's
    "Add a payment method" scenario (ACH, per that suite's own "Add New
    Payments Method" keyword default).

    Confirmed live (2026-09-13, uat_storoutlet/Bellflower): the tenant
    header's sidebar toggle lists Tenant Profile / Transaction History /
    Ledger / Documents / Payment Methods / Gate Access. Payment Methods
    (/contacts/<id>/payment-methods) shows "No Payment Methods found." and
    "+ Add New Payment Method" while the tenant has none; that opens an
    "Add New Payment Method" dialog with Credit/Debit and ACH/E-Check
    options (neither pre-selected), the same ACH form as Take a Payment
    (see fill_ach_details) and a Save button. After saving, the page lists
    "Payment Method Checking ending in 6667".

    open_tenants/open_tenant_details are copied from the live-verified
    HBTenantDocumentsPage (2026-09-10, stage)."""

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
    def open_payment_methods_menu(self) -> None:
        with allure.step("Open Payment Methods on tenant details"):
            sidebar_toggle = self.page.locator(
                'button[name="QA-HbHeader-HbIcon-mdi-table-actions-custom-1"]'
            )
            expect(sidebar_toggle).to_be_visible(timeout=self.timeout)
            sidebar_toggle.click()
            payment_methods_link = self.page.get_by_text(
                "Payment Methods", exact=True
            )
            expect(payment_methods_link).to_be_visible(timeout=self.timeout)
            payment_methods_link.click()
            # Not exact: with no saved methods the button reads "+ Add New
            # Payment Method" (an empty-state button); a tenant who already
            # has methods hasn't been seen live yet.
            expect(
                self.page.get_by_role(
                    "button", name="Add New Payment Method"
                )
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def add_ach_payment_method(
        self,
        first_name: str,
        last_name: str,
        account_type: str,
        routing_number: str,
        account_number: str,
    ) -> None:
        with allure.step("Add ACH payment method"):
            self.page.get_by_role(
                "button", name="Add New Payment Method"
            ).click()
            # Scoped to the dialog: a closed Take a Payment drawer's ACH
            # fields carry the same names and can linger in the page.
            dialog = self.page.locator(".v-dialog--active").last
            save_button = dialog.get_by_role("button", name="Save", exact=True)
            expect(save_button).to_be_visible(timeout=self.timeout)

            ach_option = dialog.get_by_role("button", name="ACH/E-Check", exact=True)
            ach_radio = ach_option.get_by_role("radio", name="ACH/E-Check", exact=True)
            for attempt in range(3):
                if ach_radio.is_checked():
                    break
                ach_option.click()
                try:
                    expect(ach_radio).to_be_checked(timeout=waits().short)
                    break
                except AssertionError:
                    if attempt == 2:
                        raise

            fill_ach_details(
                self.page,
                dialog,
                self.timeout,
                first_name,
                last_name,
                account_type,
                routing_number,
                account_number,
            )
            expect(save_button).to_be_enabled(timeout=self.timeout)
            save_button.click()
            expect(dialog).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def assert_payment_method_added(self, account_number: str) -> None:
        last_four_digits = account_number[-4:]
        with allure.step(f"Verify the saved payment method ending in {last_four_digits}"):
            expect(
                self.page.get_by_text(re.compile(rf"ending in\s*{last_four_digits}")).first
            ).to_be_visible(timeout=self.timeout)
