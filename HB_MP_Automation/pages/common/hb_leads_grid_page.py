import re
import time

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits

# Header cells in display order: pinned-left first, then by the grid's own
# horizontal position (ag-grid positions header cells with style.left; DOM
# order doesn't follow a moved column).
_HEADERS_JS = """
() => Array.from(document.querySelectorAll('.ag-header-cell[col-id]'))
  .map(cell => ({
    colId: cell.getAttribute('col-id'),
    title: (cell.textContent || '').replace(/\\s+/g, ' ').trim(),
    left: parseFloat(cell.style.left || '0'),
    pinned: !!cell.closest('.ag-pinned-left-header'),
  }))
  .filter(cell => cell.title)
  .sort((a, b) => (b.pinned - a.pinned) || (a.left - b.left))
"""


class HBLeadsGridPage:
    """The HB Leads grid's views and columns (old Robot Lead_Management
    RearrangeLeadColumns suite), for a Leads page that's already open (see
    HBLeadManagementPage.open_leads). Confirmed live 2026-09-14
    (uat_storoutlet, Bellflower): the view picker ("Select" textbox) offers
    "Active Leads" and "Reservations" plus any saved custom reports; the grid
    is an ag-grid whose header cells carry col-ids. A rearranged layout lives
    only in the browser session (sessionStorage "vuex") - it survives a
    reload, never reaches the server, and a "Reset" link restores it."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def _view_selector(self):
        # The combobox div's own text is only its arrow icon - the selected
        # view is the nested input's value, exposed as this "Select" textbox.
        return self.page.get_by_role("textbox", name="Select", exact=True)

    @log_method_exceptions
    def _open_view_menu(self) -> None:
        self._view_selector().locator(
            "xpath=ancestor::*[contains(@class,'v-select__slot')][1]"
        ).click()
        expect(self.page.get_by_role("option").first).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def view_options(self) -> list[str]:
        with allure.step("Read the Leads view options"):
            expect(self._view_selector()).to_be_visible(timeout=self.timeout)
            self._open_view_menu()
            options = [
                text.strip() for text in self.page.get_by_role("option").all_inner_texts()
            ]
            self.page.keyboard.press("Escape")
            return options

    @log_method_exceptions
    def switch_view(self, view_name: str) -> None:
        with allure.step(f"Switch the Leads view to {view_name}"):
            view_selector = self._view_selector()
            expect(view_selector).to_be_visible(timeout=self.timeout)
            if view_selector.input_value() == view_name:
                return
            # This Vuetify select can drop a click landed mid-animation - check
            # the switch took and retry, as HBLeadManagementPage._select_view.
            for attempt in range(3):
                self._open_view_menu()
                self.page.get_by_role("option", name=view_name, exact=True).click()
                try:
                    expect(view_selector).to_have_value(view_name, timeout=waits().short)
                    break
                except AssertionError:
                    if attempt == 2:
                        raise
            self._wait_for_grid_loading_to_finish()

    @log_method_exceptions
    def _wait_for_grid_loading_to_finish(self) -> None:
        loading_rows = self.page.get_by_text("Loading", exact=True)
        deadline = time.monotonic() + self.timeout / 1000
        while time.monotonic() < deadline and loading_rows.count() > 0:
            self.page.wait_for_timeout(waits().poll_interval)

    @log_method_exceptions
    def _headers(self) -> list[dict]:
        # Wait until the header row has rendered and stopped changing (a view
        # switch re-renders it).
        deadline = time.monotonic() + self.timeout / 1000
        previous = None
        while time.monotonic() < deadline:
            headers = self.page.evaluate(_HEADERS_JS)
            if headers and headers == previous:
                return headers
            previous = headers
            self.page.wait_for_timeout(waits().poll_interval)
        raise AssertionError("The Leads grid's column headers never settled")

    @log_method_exceptions
    def column_titles(self) -> list[str]:
        return [header["title"] for header in self._headers()]

    @log_method_exceptions
    def column_ids(self) -> list[str]:
        return [header["colId"] for header in self._headers()]

    @log_method_exceptions
    def assert_columns(self, expected_titles: list[str]) -> None:
        with allure.step("Leads columns match the expected list and order"):
            titles = self.column_titles()
            assert titles == expected_titles, (
                f"Leads columns changed.\nExpected: {expected_titles}\nActual:   {titles}"
            )

    @log_method_exceptions
    def wait_for_column_ids(self, expected_ids: list[str]) -> None:
        # After a drag or Reset the header row re-renders a moment later.
        deadline = time.monotonic() + self.timeout / 1000
        ids = None
        while time.monotonic() < deadline:
            ids = self.column_ids()
            if ids == expected_ids:
                return
            self.page.wait_for_timeout(waits().poll_interval)
        raise AssertionError(f"Leads columns are {ids}, expected {expected_ids}")

    @log_method_exceptions
    def move_column(self, col_id: str, past_col_id: str) -> None:
        # Confirmed live 2026-09-14: ag-grid only moves a column when the drag
        # starts on the header label and passes over the other headers slowly
        # - a fast sweep from the cell's centre starts no move at all. Hover
        # just past the target before releasing.
        with allure.step(f"Drag column {col_id} past {past_col_id}"):
            source = self.page.locator(f'.ag-header-cell[col-id="{col_id}"]').first
            label = source.locator(".ag-header-cell-label, .ag-header-cell-comp-wrapper").first
            start = (label if label.count() else source).bounding_box()
            target = self.page.locator(f'.ag-header-cell[col-id="{past_col_id}"]').first.bounding_box()
            x0 = start["x"] + start["width"] / 2
            y = start["y"] + start["height"] / 2
            x1 = target["x"] + target["width"] * 0.7
            mouse = self.page.mouse
            mouse.move(x0, y)
            mouse.down()
            mouse.move(x0 + 15, y, steps=5)
            steps = max(10, int(abs(x1 - x0) / 20) + 1)
            for step in range(1, steps + 1):
                mouse.move(x0 + (x1 - x0) * step / steps, y)
                self.page.wait_for_timeout(90)
            self.page.wait_for_timeout(900)
            mouse.up()

    @log_method_exceptions
    def open_in_new_window(self) -> Page:
        # The way the old Robot suite opened its second window. Confirmed live
        # 2026-09-14: a window.open() window starts with a copy of this tab's
        # session (layout included), unlike a separately opened tab.
        with allure.step("Open Leads in a new window"):
            with self.page.context.expect_page() as popup_info:
                self.page.evaluate("window.open(window.location.href)")
            popup = popup_info.value
            popup.set_default_timeout(self.timeout)
            popup.wait_for_load_state("domcontentloaded")
            return popup

    @log_method_exceptions
    def wait_for_column_titles(self, expected_titles: list[str]) -> None:
        deadline = time.monotonic() + self.timeout / 1000
        titles = None
        while time.monotonic() < deadline:
            titles = self.column_titles()
            if titles == expected_titles:
                return
            self.page.wait_for_timeout(waits().poll_interval)
        raise AssertionError(f"Leads columns are {titles}, expected {expected_titles}")

    @log_method_exceptions
    def _wait_for_panel_close_button(self):
        # The side panel's own X - the button name also exists on other,
        # hidden panels, so take the visible one.
        buttons = self.page.locator('button[name="QA-ActionsPanelHeader-HbIcon-mdi-close"]')
        deadline = time.monotonic() + self.timeout / 1000
        while time.monotonic() < deadline:
            for index in range(buttons.count()):
                if buttons.nth(index).is_visible():
                    return buttons.nth(index)
            self.page.wait_for_timeout(waits().poll_interval)
        raise AssertionError("The Leads side panel never opened")

    @log_method_exceptions
    def add_columns(self, group_hint: str, column_names: list[str]) -> None:
        """Set Columns (header button ...mdi-table-actions-custom-2). Confirmed
        live 2026-09-14: a side panel with four unlabelled group pickers
        (Property / Space / Lead / Reservation), each showing its current
        selection ("Lead Created +10 more"), so a group is found by that text;
        its items are the active menu's .v-list-item rows. Added columns are
        appended after the existing ones, and the panel stays open after
        "Set Columns" is applied."""
        with allure.step(f"Set columns: add {', '.join(column_names)}"):
            self.page.locator('button[name="QA-HbHeader-HbIcon-mdi-table-actions-custom-2"]').click()
            close_button = self._wait_for_panel_close_button()
            panel = close_button.locator(
                "xpath=ancestor::*[count(.//button) > 2 or count(.//input) > 0][1]"
            )
            picker = panel.locator(".v-select__slot").filter(has_text=group_hint).first
            expect(picker).to_be_visible(timeout=self.timeout)
            picker.click()
            items = self.page.locator(".v-menu__content.menuable__content__active .v-list-item")
            expect(items.first).to_be_visible(timeout=self.timeout)
            for name in column_names:
                item = items.filter(
                    has_text=re.compile(rf"^\s*(check_box(_outline_blank)?)?\s*{re.escape(name)}\s*$")
                ).first
                expect(item).to_be_visible(timeout=self.timeout)
                # Clicking a ticked item would untick it.
                already_ticked = item.get_attribute("aria-selected") == "true" or (
                    "v-list-item--active" in (item.get_attribute("class") or "")
                )
                if not already_ticked:
                    item.click()
            self.page.keyboard.press("Escape")
            panel.locator('button[name="QA-v-toolbar-hb-primary-button-Set-Columns"]').click()
            self._wait_for_grid_loading_to_finish()
            close_button.click()
            expect(close_button).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def expect_current_view(self, view_name: str) -> None:
        with allure.step(f"The Leads view is {view_name}"):
            expect(self._view_selector()).to_have_value(view_name, timeout=self.timeout)

    @log_method_exceptions
    def save_report(self, name: str, description: str, make_default: bool) -> None:
        """Save Report (header button ...mdi-content-save). Confirmed live
        2026-09-14: a side panel ("Saved reports are displayed in the Custom
        Reports section") with Save Report for, a name, a description and a
        "Make my default report" checkbox. Saving shows "Report Saved" and
        switches the page to the new view. Unlike the column layout this is
        saved on the server for the login - delete it afterwards
        (HBReportsPage.delete_custom_report)."""
        with allure.step(f"Save the Leads view as report: {name}"):
            self.page.locator('button[name="QA-HbHeader-HbIcon-mdi-content-save"]').click()
            close_button = self._wait_for_panel_close_button()
            panel = close_button.locator(
                "xpath=ancestor::*[count(.//button) > 2 or count(.//input) > 0][1]"
            )
            panel.locator('input[name="name"]').fill(name)
            panel.locator('textarea[name="description"]').fill(description)
            default_checkbox = panel.get_by_role("checkbox").first
            if default_checkbox.is_checked() != make_default:
                panel.get_by_text("Make my default report", exact=True).click()
            expect(default_checkbox).to_be_checked(checked=make_default)
            panel.locator('button[name="QA-v-toolbar-hb-primary-button-Save-Report"]').click()
            expect(self.page.get_by_text(re.compile(r"Report Saved")).first).to_be_visible(
                timeout=self.timeout
            )
            # The panel stayed open after saving in the walk - close it if so.
            if close_button.is_visible():
                close_button.click()
                expect(close_button).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def reset_link(self):
        return self.page.locator("a.hb-link").filter(has_text=re.compile(r"^\s*Reset\s*$")).first
