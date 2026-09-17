import re

import allure
from playwright.sync_api import Locator, Page, expect

from common_utils.wrapper_methods import log_method_exceptions


class HBSpacesPage:
    """HB Spaces list (sidebar "Spaces", /spaces) for the property that's
    already selected: find a space and check its live status. Confirmed live
    2026-09-13 (uat_storoutlet, Bellflower): an ag-grid whose cells carry
    col-ids (unit_number "#0040", unit_status "Reserved" / "Available", ...),
    filtered with "Search Spaces" + Enter."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def open_spaces(self) -> None:
        with allure.step("Open Spaces"):
            spaces_link = self.page.get_by_role("complementary").get_by_text(
                "Spaces", exact=True
            )
            expect(spaces_link).to_be_visible(timeout=self.timeout)
            spaces_link.locator("xpath=ancestor::*[@role='listitem'][1]").dispatch_event(
                "click"
            )
            expect(self.page).to_have_url(re.compile(r"/spaces"), timeout=self.timeout)
            expect(self._search_box()).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _search_box(self) -> Locator:
        # By role: the "Search Spaces" placeholder sits on both a wrapper div
        # and the input (confirmed live), so a placeholder match is ambiguous.
        return self.page.get_by_role("textbox", name="Search Spaces", exact=True)

    @log_method_exceptions
    def _space_row(self, space_number: str) -> Locator:
        # The search is a substring match ("0040" listed 6 spaces), so pin the
        # row by its exact Space Number cell.
        return self.page.locator(".ag-row").filter(
            has=self.page.locator('[col-id="unit_number"]').get_by_text(
                f"#{space_number.lstrip('#')}", exact=True
            )
        )

    @log_method_exceptions
    def start_lead_from_available_space(self) -> str:
        """Picks the first Available space in the list and opens Tenant
        Onboarding on it with "Create New Lead/Move-In" (confirmed live
        2026-09-14, Chula Vista #O2). Returns the space number ("#O2")."""
        with allure.step("Pick an Available space and start Create New Lead/Move-In"):
            row = (
                self.page.locator(".ag-row")
                .filter(
                    has=self.page.locator('[col-id="unit_status"]').get_by_text(
                        "Available", exact=True
                    )
                )
                .first
            )
            try:
                expect(row).to_be_visible(timeout=self.timeout)
            except AssertionError:
                raise AssertionError("No Available space in the Spaces list") from None
            number_cell = row.locator('[col-id="unit_number"]').first
            space_number = number_cell.inner_text().strip()
            number_cell.click()
            start_lead = self.page.locator(
                'button[name="QA-HbBottomActionBar-hb-primary-button-Create-New-Lead/Move-In"]'
            ).first
            expect(start_lead).to_be_visible(timeout=self.timeout)
            start_lead.click()
            expect(
                self.page.locator("aside.new_lead.v-navigation-drawer--open")
            ).to_be_visible(timeout=self.timeout)
            return space_number

    @log_method_exceptions
    def assert_space_status(self, space_number: str, status: str) -> None:
        with allure.step(f"Space {space_number} is {status}"):
            row = self._space_row(space_number)
            status_cell = row.locator('[col-id="unit_status"] span.hb-status-font')
            expected = re.compile(rf"^\s*{re.escape(status)}\s*$", re.IGNORECASE)
            # Re-search a few times: a status change made moments ago (a
            # reservation or its cancellation) can take a little while to
            # reach the list.
            seen = None
            for _ in range(4):
                self._search_box().fill(space_number.lstrip("#"))
                self.page.keyboard.press("Enter")
                try:
                    expect(row).to_have_count(1, timeout=self.timeout)
                    expect(status_cell).to_have_text(expected, timeout=10000)
                    return
                except AssertionError:
                    seen = status_cell.first.text_content() if status_cell.count() else None
            raise AssertionError(
                f"Space {space_number} shows status {seen!r}, expected {status!r}"
            )
