import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


class HBTransactionHistoryPage:
    """A tenant's Transaction History (/contacts/<id>/transaction-history):
    void a payment and void an invoice - the old Robot Mariposa
    ReservationAndRentals suite's "Void the Payment and Invoice".

    Confirmed live (2026-09-13, uat_storoutlet/Chula Vista, space OP1): the
    tenant header's sidebar toggle opens Transaction History; its rows are
    tr.row-payment ("Payment : Visa **** 1111", $56.00) and tr.row-invoice
    ("Invoice # 42842 - OP1", Paid). A payment's link opens "Payment
    Details" with Void -> "Are you sure you want to continue?" -> Confirm ->
    "The payment has been voided successfully.", a new tr.row-refund
    "Void : Visa **** 1111" row, and the invoice turning Open. An invoice's
    link opens it with Void -> "Provide Reason*" (required) -> Confirm; HB
    shows no message, but the invoice's row becomes tr.row-void, status Void.
    """

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def open(self) -> None:
        with allure.step("Open Transaction History"):
            self.page.locator(
                'button[name="QA-HbHeader-HbIcon-mdi-table-actions-custom-1"]'
            ).click()
            self.page.get_by_text("Transaction History", exact=True).first.click()
            expect(self.page).to_have_url(re.compile(r"/transaction-history"), timeout=self.timeout)
            expect(
                self.page.locator("tr.row-payment, tr.row-invoice").first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _close_open_dialogs(self) -> None:
        close_buttons = self.page.locator('.v-dialog--active [name="QA-v-card-HbIcon-mdi-close"]')
        for _ in range(3):
            visible = [button for button in close_buttons.all() if button.is_visible()]
            if not visible:
                return
            visible[-1].click()
            self.page.wait_for_timeout(1000)

    @log_method_exceptions
    def void_payment(self, amount: float) -> None:
        formatted = f"${amount:,.2f}"
        with allure.step(f"Void the {formatted} payment"):
            row = self.page.locator("tr.row-payment").filter(has_text=formatted).first
            expect(row).to_be_visible(timeout=self.timeout)
            row.locator("a").first.click()
            expect(self.page.locator(".v-dialog--active").last).to_contain_text(
                "Payment Details", timeout=self.timeout
            )
            self.page.locator(
                '.v-dialog--active button[name="QA-HbBottomActionBar-hb-secondary-button-Void"]'
            ).last.click()
            confirm = self.page.locator(
                '.v-dialog--active button[name="QA-HbBottomActionBar-hb-primary-button-Confirm"]'
            ).last
            expect(confirm).to_be_visible(timeout=self.timeout)
            confirm.click()
            expect(
                self.page.get_by_text("The payment has been voided successfully").first
            ).to_be_visible(timeout=self.timeout)
            self._close_open_dialogs()
            expect(
                self.page.locator("tr.row-refund").filter(has_text="Void").first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def void_open_invoice(self, reason: str) -> str:
        """Voids the tenant's Open invoice (the one a voided payment had
        paid) and returns its number."""
        with allure.step("Void the open invoice"):
            invoice_rows = self.page.locator("tbody tr").filter(
                has=self.page.get_by_text(re.compile(r"Invoice\s*#"))
            )
            # By its "Open" status cell, not a row class: a future-dated
            # invoice (below) renders without tr.row-invoice (confirmed live
            # 2026-09-14), and a row-level has_text "Open" can't use word
            # boundaries - the cells' text runs together ("...OP10Open").
            row = invoice_rows.filter(
                has=self.page.get_by_role("cell", name="Open", exact=True)
            ).first
            # A charge dated after the property's own "today" is filed under
            # "Show Future Charges (N)" - seen 2026-09-14 when a run crossed
            # midnight (storefront move-in the next day, property still on the
            # previous one). Open it first, as the old Robot suite's "Void the
            # Invoice" keyword did.
            future_charges = self.page.get_by_text(
                re.compile(r"^\s*Show Future Charges \(\d+\)\s*$")
            ).first
            expect(row.or_(future_charges)).to_be_visible(timeout=self.timeout)
            if not row.is_visible() and future_charges.is_visible():
                future_charges.click()
            expect(row).to_be_visible(timeout=self.timeout)
            link = row.locator("a").first
            number = re.search(r"Invoice\s*#\s*(\S+)", link.inner_text()).group(1)
            link.click()
            void = self.page.locator(
                '.v-dialog--active button[name="QA-HbBottomActionBar-hb-secondary-button-Void"]'
            ).last
            expect(void).to_be_visible(timeout=self.timeout)
            void.click()
            reason_box = self.page.get_by_role("textbox", name="Provide Reason*", exact=True)
            expect(reason_box).to_be_visible(timeout=self.timeout)
            # Same pause as the ACH form: a Tab straight after typing lets
            # HB validate before it has taken the value (see hb_ach_form).
            reason_box.fill(reason)
            self.page.wait_for_timeout(waits().poll_interval)
            self.page.keyboard.press("Tab")
            self.page.wait_for_timeout(waits().poll_interval)
            self.page.locator(
                '.v-dialog--active button[name="QA-HbBottomActionBar-hb-primary-button-Confirm"]'
            ).last.click()
            expect(reason_box).to_be_hidden(timeout=self.timeout)
            self._close_open_dialogs()
            expect(
                invoice_rows.filter(has_text=re.compile(rf"Invoice\s*#\s*{re.escape(number)}\b"))
                .filter(has=self.page.get_by_role("cell", name="Void", exact=True))
                .first
            ).to_be_visible(timeout=self.timeout)
            allure.attach(
                f"Invoice #{number} voided", name="voided invoice",
                attachment_type=allure.attachment_type.TEXT,
            )
            return number
