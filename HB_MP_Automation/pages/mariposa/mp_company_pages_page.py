import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation


class MPCompanyPagesPage:
    """Company Pages CMS, configured under HB Settings' Website (Mariposa) app."""

    STATUSES = ("Published", "Publish Later", "Draft")

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float, nav: HBSettingsNavigation) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        self.created_titles: list[str] = []
        self._pending_new_page = False

    @log_method_exceptions
    def open_company_pages(self) -> None:
        self.nav.open_settings_panel()
        self.nav.switch_app_filter_to_website()
        with allure.step("Open Company Pages settings"):
            link = self.page.get_by_role("listitem").filter(
                has_text=re.compile(r"^Company Pages$")
            )
            expect(link).to_be_visible(timeout=self.timeout)
            link.click()

    @log_method_exceptions
    def add_new_company_page(self) -> None:
        with allure.step("Add new Company Page"):
            self.page.get_by_text("+ Add New Company Page", exact=True).click()
            # Marks the next fill_title() call as the one that names a
            # brand-new page, so it can be recorded for cleanup - see
            # created_titles / delete_company_page.
            self._pending_new_page = True

    @log_method_exceptions
    def delete_company_page(self, title: str, *, timeout: float | None = None) -> None:
        """Deletes a Company Page by title via its row's "..." menu ->
        Delete -> Continue (same confirmation flow confirmed live for
        Company Blogs - the confirmation dialog is titled "Delete Entry"
        and its confirm button reads "Continue", not "Delete" or
        "Yes"). `timeout` overrides self.timeout - see
        cleanup_created_pages, which passes a short one so a title that
        was tracked but never actually saved fails fast instead of
        waiting the full timeout for a row that will never appear."""
        wait = self.timeout if timeout is None else timeout
        with allure.step(f"Delete Company Page: {title}"):
            self.search(title)
            row = self.page.get_by_role("row", name=re.compile(re.escape(title)))
            expect(row).to_be_visible(timeout=wait)
            row.locator(".mdi-dots-vertical").click()
            self.page.get_by_role("button", name="Delete", exact=True).click()
            continue_button = self.page.get_by_role(
                "button", name="Continue", exact=True
            )
            expect(continue_button).to_be_visible(timeout=wait)
            continue_button.click()
            expect(row).not_to_be_visible(timeout=wait)

    @log_method_exceptions
    def cleanup_created_pages(self) -> None:
        """Deletes every page created via add_new_company_page() +
        fill_title() during this page object's lifetime - intended for
        test teardown so QA automation runs don't leave test data behind
        in shared environments."""
        for title in self.created_titles:
            try:
                self.delete_company_page(title, timeout=5000)
            except Exception:
                pass
        self.created_titles = []

    @log_method_exceptions
    def search(self, query: str) -> None:
        with allure.step(f"Search Company Pages for: {query}"):
            search_box = self.page.get_by_role(
                "textbox", name="Search By Title or Slug"
            )
            try:
                expect(search_box).to_be_visible(timeout=10000)
            except AssertionError:
                # Confirmed live: the Settings panel can get stuck
                # mid-render with no error, leaving this search box
                # never appearing - same class of issue as
                # HBSettingsNavigation.open_settings_panel and
                # HBLoginPage.open_login_page, including in teardown
                # (cleanup_created_pages -> delete_company_page ->
                # search), where it silently stranded pages that were
                # never actually deleted. A full reload resets that
                # stuck client-side state; re-opening Company Pages
                # from scratch (open_settings_panel's own retry logic
                # handles the rest) restores it - cheaper than waiting
                # out the full timeout for a state that isn't coming
                # back on its own.
                self.page.reload(wait_until="commit")
                self.open_company_pages()
                expect(search_box).to_be_visible(timeout=self.timeout)
            search_box.click()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.type(query)
            search_box.press("Enter")

    @log_method_exceptions
    def open_company_page(self, title: str) -> None:
        with allure.step(f"Open Company Page: {title}"):
            # The title looks like a link (styled blue/underlined) but the
            # clickable accessible element is the table row, not an <a> -
            # get_by_role("link", ...) never matches anything here.
            self.search(title)
            row = self.page.get_by_role("row", name=re.compile(re.escape(title)))
            expect(row).to_be_visible(timeout=self.timeout)
            row.click()

    @log_method_exceptions
    def open_content_tab(self) -> None:
        self.page.get_by_role("tab", name="Content", exact=True).click()

    @log_method_exceptions
    def open_settings_tab(self) -> None:
        self.page.get_by_role("tab", name="Settings", exact=True).click()

    @log_method_exceptions
    def fill_title(self, title: str) -> None:
        with allure.step(f"Set Company Page Title: {title}"):
            self.open_content_tab()
            self.page.get_by_role("textbox", name="Enter Page Title").fill(title)
            if self._pending_new_page:
                self.created_titles.append(title)
                self._pending_new_page = False

    @log_method_exceptions
    def get_slug(self) -> str:
        return self.page.get_by_role(
            "textbox", name="Enter Title to generate Slug"
        ).input_value()

    @log_method_exceptions
    def fill_contents(self, contents: str) -> None:
        with allure.step("Set Company Page Contents"):
            editor = self.page.get_by_text("Contents*", exact=True).locator(
                "xpath=following::*[@contenteditable='true'][1]"
            )
            editor.click()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.type(contents)

    @log_method_exceptions
    def set_status(self, status: str) -> None:
        with allure.step(f"Set Company Page status: {status}"):
            self.open_settings_tab()
            self.page.get_by_role("button", name=re.compile(r"^Status\*")).click()
            self.page.get_by_role("option", name=status, exact=True).click()

    @log_method_exceptions
    def set_hide_from_listing(self, hidden: bool) -> None:
        with allure.step(f"Set Hide From Listing: {hidden}"):
            self.open_settings_tab()
            checkbox = self.page.get_by_role("checkbox", name="Hide From Listing")
            if checkbox.is_checked() != hidden:
                self.page.get_by_text("Hide From Listing", exact=True).click()
            expect(checkbox).to_be_checked(checked=hidden)

    @log_method_exceptions
    def save(self) -> None:
        with allure.step("Save Company Page"):
            self.page.get_by_role("button", name="Save Page", exact=True).click()
            success = self.page.get_by_text(
                "Company Page details successfully updated", exact=True
            )
            expect(success).to_be_visible(timeout=self.timeout)
        self.nav.clear_cache()
