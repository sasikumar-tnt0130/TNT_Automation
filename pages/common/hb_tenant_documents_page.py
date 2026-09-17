import re

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions


class HBTenantDocumentsPage:
    """Tenant details "Documents" panel: upload a file against a
    tenant's record. Ported from the old Robot Framework smoke suite's
    "For tenants upload files" scenario - confirmed live (2026-09-10,
    stage) that uploading no longer requires picking which of the
    tenant's spaces to attach the file to (a dropdown with scrolling-
    list search the old suite's Upload File keyword had to handle) - a
    single upload now applies straight to the tenant."""

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
            # Same picker widget as HBMoveOutPage.open_tenants/
            # HBLeadManagementPage.open_leads - the target property
            # isn't guaranteed to already be on top, so type the name to
            # filter down to it explicitly instead of hoping.
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
    def open_tenant_details(self, first_name: str, last_name: str) -> None:
        full_name = f"{first_name} {last_name}"
        with allure.step(f"Search Given Tenant And Open Details: {full_name}"):
            search_tenants = self.page.get_by_role(
                "textbox", name="Search Tenants", exact=True
            )
            expect(search_tenants).to_be_visible(timeout=self.timeout)
            search_tenants.fill(full_name)
            self.page.keyboard.press("Enter")

            # Unlike the Leads grid (see HBLeadManagementPage), this
            # Tenants grid's rows do expose their cell text as their own
            # accessible name - confirmed live (2026-09-10, stage) - so
            # the tenant name cell can be matched directly.
            tenant_cell = self.page.get_by_role(
                "gridcell", name=full_name, exact=True
            )
            expect(tenant_cell).to_be_visible(timeout=self.timeout)
            tenant_cell.click()
            expect(
                self.page.get_by_text(full_name, exact=True).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def open_documents_menu(self) -> None:
        with allure.step("Open Side Bar On Tenant Details: Documents"):
            sidebar_toggle = self.page.locator(
                'button[name="QA-HbHeader-HbIcon-mdi-table-actions-custom-1"]'
            )
            expect(sidebar_toggle).to_be_visible(timeout=self.timeout)
            sidebar_toggle.click()
            # Confirmed live: this sidebar's items render as plain <li>
            # inside a "listbox" container rather than proper ARIA
            # "option" children, so Playwright's role query for
            # "listitem" doesn't reliably match them even though a
            # debug accessibility dump shows "listitem: Documents" -
            # matching by its own text is what actually works.
            documents_link = self.page.get_by_text("Documents", exact=True)
            expect(documents_link).to_be_visible(timeout=self.timeout)
            documents_link.click()
            expect(
                self.page.get_by_role("button", name="Upload File", exact=True)
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def upload_file(self, file_path: str) -> None:
        with allure.step(f"Upload File: {file_path}"):
            self.page.get_by_role(
                "button", name="Upload File", exact=True
            ).click()

            # Confirmed live: the attach icon's accessible name is
            # "prepend icon" (a Vuetify slot name leaking through as the
            # aria-label) rather than anything describing its purpose -
            # its rendered "attach_file" text is icon-ligature content,
            # not the accessible name.
            with self.page.expect_file_chooser() as file_chooser_info:
                self.page.get_by_role(
                    "button", name="prepend icon", exact=True
                ).click()
            file_chooser_info.value.set_files(file_path)

            upload_confirm_button = self.page.get_by_role(
                "button", name="Upload", exact=True
            )
            expect(upload_confirm_button).to_be_enabled(timeout=self.timeout)
            upload_confirm_button.click()

    @log_method_exceptions
    def assert_file_uploaded(self, file_name: str) -> None:
        with allure.step(f"Validate uploaded file appears: {file_name}"):
            file_row = self.page.get_by_role(
                "row", name=re.compile(re.escape(file_name))
            )
            expect(file_row.first).to_be_visible(timeout=self.timeout)
            expect(
                file_row.first.get_by_text("Uploaded", exact=True)
            ).to_be_visible(timeout=self.timeout)
