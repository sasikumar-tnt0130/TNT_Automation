import re
import time

import allure
from playwright.sync_api import Locator, Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits

# The report grids are virtualized ag-grids whose pinned and centre columns
# render as separate .ag-row elements - merge them by row-index.
_READ_ROWS_JS = """
() => {
  const rows = {};
  for (const container of document.querySelectorAll(
      '.ag-center-cols-container, .ag-pinned-left-cols-container')) {
    for (const row of container.querySelectorAll('.ag-row')) {
      const index = row.getAttribute('row-index');
      rows[index] = rows[index] || {};
      for (const cell of row.querySelectorAll('[col-id]')) {
        rows[index][cell.getAttribute('col-id')] =
          (cell.textContent || '').replace(/\\s+/g, ' ').trim();
      }
    }
  }
  return rows;
}
"""


class HBReportsPage:
    """HB Reports library (sidebar "Reports", /reports-library): run a
    library report for the property that's already selected and read its
    rows. Confirmed live 2026-09-13 (uat_storoutlet, Bellflower): reports sit
    in collections ("Occupancy Reports (15)", ...) that expand in place; a
    report's inline panel defaults to "This Month" for the selected property
    and "Run Report" opens /reports-library/<report>?dynamicRun=true, an
    ag-grid with col-ids (lead_email, lead_status, lead_retire_reason, ...)
    and a "Search This Report" box."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def open_reports_library(self) -> None:
        with allure.step("Open the Reports library"):
            reports_link = self.page.get_by_role("complementary").get_by_text(
                "Reports", exact=True
            )
            expect(reports_link).to_be_visible(timeout=self.timeout)
            reports_link.locator("xpath=ancestor::*[@role='listitem'][1]").dispatch_event(
                "click"
            )
            expect(self.page).to_have_url(
                re.compile(r"/reports-library/?(\?.*)?$"), timeout=self.timeout
            )
            expect(self.page.locator('[id^="collection-"]').first).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def run_report(self, collection: str, report_name: str) -> None:
        with allure.step(f"Run report: {report_name}"):
            name = self.page.locator("span.report-name").filter(
                has_text=re.compile(rf"^\s*{re.escape(report_name)}\s*$")
            ).first
            collection_title = (
                self.page.locator('[id^="collection-"]')
                .filter(has_text=re.compile(rf"^\s*{re.escape(collection)}"))
                .first.get_by_text(collection, exact=False)
                .first
            )
            # The library remembers which collections were left open, and
            # clicking an open collection's title collapses it (confirmed
            # live) - so only click the title while the report isn't showing,
            # and click it back once if that turned out to close it.
            for _ in range(2):
                try:
                    expect(name).to_be_visible(timeout=waits().tiny)
                    break
                except AssertionError:
                    collection_title.click()
            expect(name).to_be_visible(timeout=self.timeout)
            name.click()
            report_panel = name.locator(
                "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '),"
                " ' v-expansion-panel ')][1]"
            )
            run_button = report_panel.locator(
                'button[name="QA-v-expansion-panel-content-hb-primary-button-Run-Report"]'
            )
            expect(run_button).to_be_visible(timeout=self.timeout)
            run_button.click()
            expect(self.page).to_have_url(
                re.compile(r"/reports-library/.+dynamicRun=true"), timeout=self.timeout
            )
            expect(self._search_box()).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _show_report_name(self, collection: str, report_name: str) -> Locator:
        # Same rule as run_report: the library remembers open collections and
        # clicking an open one's title collapses it, so only click while the
        # report isn't showing.
        name = self.page.locator("span.report-name").filter(
            has_text=re.compile(rf"^\s*{re.escape(report_name)}\s*$")
        ).first
        collection_title = (
            self.page.locator('[id^="collection-"]')
            .filter(has_text=re.compile(rf"^\s*{re.escape(collection)}"))
            .first.get_by_text(collection, exact=False)
            .first
        )
        for _ in range(2):
            try:
                expect(name).to_be_visible(timeout=waits().tiny)
                break
            except AssertionError:
                collection_title.click()
        expect(name).to_be_visible(timeout=self.timeout)
        return name

    @log_method_exceptions
    def delete_custom_report(self, report_name: str, for_everyone: bool = True) -> None:
        """Deletes a saved report from "Custom Reports" (the library
        collection that appears once a report has been saved). Confirmed live
        2026-09-14: the report's ⋮ menu has "Delete Report", whose dialog
        offers "Delete for Myself" (the default) or "Delete for Everyone".
        Choosing Everyone only relabels the confirm button - its name
        attribute stays ...Delete-for-Myself - so its text is what's checked."""
        choice = "Delete for Everyone" if for_everyone else "Delete for Myself"
        with allure.step(f"Delete custom report {report_name} ({choice})"):
            name = self._show_report_name("Custom Reports", report_name)
            report_panel = name.locator(
                "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '),"
                " ' v-expansion-panel ')][1]"
            )
            report_panel.locator('button[name="QA-v-menu-HbIcon-mdi-dots-vertical"]').first.click()
            delete_item = self.page.locator(
                ".v-menu__content.menuable__content__active .v-list-item,"
                " .v-menu__content.menuable__content__active [role='menuitem']"
            ).filter(has_text=re.compile(r"^\s*Delete Report\s*$")).first
            expect(delete_item).to_be_visible(timeout=self.timeout)
            delete_item.click()
            dialog = self.page.locator(".v-dialog--active").last
            expect(dialog).to_contain_text(
                "You are about to delete this custom report", timeout=self.timeout
            )
            dialog.get_by_text(choice, exact=True).first.click()
            confirm = dialog.locator(
                'button[name="QA-HbBottomActionBar-hb-destructive-button-Delete-for-Myself"]'
            )
            expect(confirm).to_have_text(re.compile(rf"^\s*{choice}\s*$"), timeout=self.timeout)
            confirm.click()
            expect(
                self.page.get_by_text(
                    re.compile(rf"You have deleted .{re.escape(report_name)}. from your Custom Reports")
                ).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _search_box(self) -> Locator:
        return self.page.locator('input[placeholder="Search This Report"]').first

    @log_method_exceptions
    def _rendered_rows(self) -> dict:
        return self.page.evaluate(_READ_ROWS_JS)

    @log_method_exceptions
    def _search(self, term: str) -> None:
        self._search_box().fill(term)
        self.page.keyboard.press("Enter")

    @log_method_exceptions
    def find_row(self, email: str) -> dict:
        """The report row for this lead email (waits for it to appear)."""
        with allure.step(f"Report row for {email}"):
            self._search(email)
            deadline = time.monotonic() + self.timeout / 1000
            while time.monotonic() < deadline:
                for cells in self._rendered_rows().values():
                    if cells.get("lead_email") == email:
                        return cells
                self.page.wait_for_timeout(waits().poll_interval)
            raise AssertionError(f"{email} isn't listed in this report")

    @log_method_exceptions
    def listed_emails(self, search_term: str) -> set[str]:
        """Every lead email the report lists for a search - for "is NOT
        listed" checks, so the search must be seen to have finished first:
        either every rendered row matches the term, or no rows render for a
        few seconds running."""
        with allure.step(f"Report rows matching {search_term}"):
            self._search(search_term)
            term = search_term.lower()
            deadline = time.monotonic() + self.timeout / 1000
            empty_since = None
            while time.monotonic() < deadline:
                rows = self._rendered_rows()
                if rows:
                    empty_since = None
                    if all(
                        any(term in value.lower() for value in cells.values())
                        for cells in rows.values()
                    ):
                        break
                else:
                    empty_since = empty_since or time.monotonic()
                    if time.monotonic() - empty_since >= 5:
                        return set()
                self.page.wait_for_timeout(waits().poll_interval)
            else:
                raise AssertionError(f"Report search for {search_term!r} never settled")
            return {
                row["lead_email"] for row in self._read_all_rows() if row.get("lead_email")
            }

    @log_method_exceptions
    def _read_all_rows(self) -> list[dict]:
        # Rows are virtualized: scroll the grid body to the end, merging
        # every batch that gets rendered on the way.
        viewport = self.page.locator(".ag-body-viewport").first
        rows: dict[str, dict] = {}
        idle_rounds = 0
        for _ in range(100):
            before = len(rows)
            for index, cells in self._rendered_rows().items():
                rows.setdefault(index, {}).update(cells)
            at_end = viewport.evaluate(
                "v => { const end = v.scrollTop + v.clientHeight >= v.scrollHeight - 2;"
                " v.scrollBy(0, v.clientHeight); return end; }"
            )
            self.page.wait_for_timeout(300)
            idle_rounds = idle_rounds + 1 if at_end and len(rows) == before else 0
            if idle_rounds >= 2:
                break
        return [rows[index] for index in sorted(rows, key=int)]
