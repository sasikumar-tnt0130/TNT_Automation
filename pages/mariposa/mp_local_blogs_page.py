import re

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation


class MPLocalBlogsPage:
    """Local Blogs CMS, configured under HB Settings' Website (Mariposa) app.

    Unlike Company Blogs/Pages, Local Blogs is scoped per-property (a
    "Select Property" picker gates the form) and has no publish
    status/workflow - it's a single H1 Title + repeatable Facility
    Content (title/content) blocks + optional Meta Title/Description,
    always live once saved. The CMS explicitly warns changes here can
    take up to 24 hours to reach the website, so storefront-reflection
    checks in tests built on this page object should not assume
    same-session propagation.

    The Settings nav lists "Local Blogs" twice - both entries open the
    identical property-picker screen (a CMS menu duplication, not two
    different features) - callers just need `.first`.
    """

    @log_method_exceptions
    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation, hb_base_url: str
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        self.hb_dashboard_url = hb_base_url.rstrip("/").removesuffix("/login") + "/dashboard"
        self.property_name: str | None = None
        self._added_block_count = 0

    @log_method_exceptions
    def _ensure_open(self) -> None:
        """save() ends by clearing cache, which navigates away from this
        form - every accessor/mutator below calls this first so callers
        don't have to remember to re-navigate after every save()."""
        if not self.property_name:
            return
        field = self.page.get_by_role(
            "textbox", name="Enter H1 Tag For Local Blog page"
        )
        if field.count() == 0 or not field.is_visible():
            self.open_local_blogs(self.property_name)

    @log_method_exceptions
    def open_local_blogs(self, property_name: str) -> None:
        self.property_name = property_name
        if not self.page.url.startswith(self.hb_dashboard_url.rsplit("/dashboard", 1)[0]):
            self.page.goto(self.hb_dashboard_url, wait_until="commit")
        self.nav.open_settings_panel()
        with allure.step("Open Local Blogs settings"):
            link = self.page.get_by_role("listitem").filter(
                has_text=re.compile(r"^Local Blogs$")
            ).first
            # See MPCompanyBlogPage.open_company_blogs for why this
            # retries rather than trusting one switch to have stuck.
            for _ in range(3):
                self.nav.switch_app_filter_to_website()
                try:
                    expect(link).to_be_visible(timeout=15000)
                    break
                except AssertionError:
                    continue
            else:
                expect(link).to_be_visible(timeout=self.timeout)
            link.click()
        with allure.step(f"Select property: {property_name}"):
            search = self.page.get_by_role("textbox", name="Select Property")
            search.click()
            search.fill(property_name)
            option = self.page.get_by_role(
                "option", name=re.compile(re.escape(property_name), re.IGNORECASE)
            )
            expect(option).to_be_visible(timeout=self.timeout)
            option.click()
        # Selecting a property mounts the form immediately, then fetches
        # the saved H1/content/meta values asynchronously - reading a
        # field right after selection can race that fetch and see an
        # empty value even though data was saved. Give the fetch a
        # bounded window to land; a timeout here isn't fatal (some
        # environments never go fully idle), just best-effort settling.
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass

    @log_method_exceptions
    def fill_h1_title(self, title: str) -> None:
        with allure.step(f"Set Local Blogs H1 Title: {title}"):
            self._ensure_open()
            self.page.get_by_role(
                "textbox", name="Enter H1 Tag For Local Blog page"
            ).fill(title)

    @log_method_exceptions
    def get_h1_title(self) -> str:
        self._ensure_open()
        field = self.page.get_by_role(
            "textbox", name="Enter H1 Tag For Local Blog page"
        )
        value = field.input_value()
        # Selecting a property (inside open_local_blogs, via _ensure_open
        # above) mounts the form immediately and fetches its saved record
        # asynchronously - reading right after selection can race that
        # fetch and see an empty value even though data was saved. A
        # short bounded poll is enough since this resolves in ~1-2s when
        # it's actually a race, not a genuinely empty title.
        for _ in range(6):
            if value:
                break
            self.page.wait_for_timeout(500)
            value = field.input_value()
        return value

    @log_method_exceptions
    def expand_facility_content(self) -> None:
        with allure.step("Expand Facility Content section"):
            self._ensure_open()
            header = self.page.get_by_text("Facility Content", exact=True)
            content = self.page.get_by_text("Add Title and Content", exact=True)
            if content.count() == 0 or not content.is_visible():
                header.evaluate("el => el.click()")
                expect(content).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def add_content_block(self, title: str, content: str) -> None:
        """Fill the last content block if it's still empty, otherwise
        click "+ Add Content" for a new one, then fill it - so repeated
        calls build up multiple blocks."""
        with allure.step(f"Add Facility Content block: {title}"):
            self.expand_facility_content()
            title_fields = self.page.get_by_role("textbox", name="Enter Title")
            if title_fields.count() > 0 and (title_fields.last.input_value() or "") == "":
                pass
            else:
                self.page.get_by_text("+ Add Content", exact=True).evaluate(
                    "el => el.click()"
                )
                title_fields = self.page.get_by_role("textbox", name="Enter Title")
                # Only a genuinely new block (via "+ Add Content") needs
                # cleanup at teardown - reusing an already-existing empty
                # block (the `pass` branch above) doesn't add anything
                # that wasn't already part of this property's saved state.
                self._added_block_count += 1
            title_fields.last.fill(title)
            self.page.get_by_role("textbox", name="Enter Content").last.fill(content)

    @log_method_exceptions
    def cleanup_added_blocks(self) -> None:
        """Removes every content block this page object added via
        add_content_block() (tracked by count, since blocks aren't
        individually named/searchable the way Company Blog/Page entries
        are) and saves - so a test that adds blocks doesn't leave this
        property's Local Blogs page permanently altered. Blocks are
        always appended at the end, so removing from the end N times
        removes exactly the ones this object added, in reverse order."""
        if self._added_block_count == 0:
            return
        try:
            self.expand_facility_content()
            for _ in range(self._added_block_count):
                count = self.get_content_block_count()
                if count == 0:
                    break
                self.remove_content_block(count - 1)
            self.save()
        except Exception:
            pass
        self._added_block_count = 0

    @log_method_exceptions
    def get_content_block_count(self) -> int:
        self.expand_facility_content()
        return self.page.get_by_role("textbox", name="Enter Title").count()

    @log_method_exceptions
    def remove_content_block(self, index: int) -> None:
        with allure.step(f"Remove Facility Content block #{index}"):
            self.expand_facility_content()
            # The remove control is an aria-hidden <i class="mdi-close">
            # icon, not a role=button - get_by_role can never match it.
            self.page.locator(".mdi-close").nth(index).evaluate("el => el.click()")

    @log_method_exceptions
    def expand_meta_details(self) -> None:
        with allure.step("Expand Meta Details section"):
            self._ensure_open()
            header = self.page.get_by_role(
                "button", name=re.compile(r"^Meta Details")
            )
            meta_title_field = self.page.get_by_role(
                "textbox", name="Enter meta title"
            )
            if meta_title_field.count() == 0 or not meta_title_field.is_visible():
                header.evaluate("el => el.click()")
                expect(meta_title_field).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def fill_meta_title(self, text: str) -> None:
        with allure.step(f"Set Local Blogs Meta Title: {text}"):
            self.expand_meta_details()
            self.page.get_by_role("textbox", name="Enter meta title").fill(text)

    @log_method_exceptions
    def get_meta_title(self) -> str:
        self.expand_meta_details()
        return self.page.get_by_role("textbox", name="Enter meta title").input_value()

    @log_method_exceptions
    def fill_meta_description(self, text: str) -> None:
        with allure.step(f"Set Local Blogs Meta Description: {text}"):
            self.expand_meta_details()
            self.page.get_by_role("textbox", name="Enter meta Description").fill(text)

    @log_method_exceptions
    def get_meta_description(self) -> str:
        self.expand_meta_details()
        return self.page.get_by_role(
            "textbox", name="Enter meta Description"
        ).input_value()

    @log_method_exceptions
    def get_last_modified_text(self) -> str:
        self.expand_meta_details()
        return (
            self.page.get_by_text("Last Modified By", exact=False).text_content() or ""
        )

    @log_method_exceptions
    def click_tokens_for_meta_details(self) -> None:
        with allure.step("Click Tokens for Meta Details"):
            self._ensure_open()
            self.page.get_by_role(
                "button", name="Tokens for Meta Details", exact=True
            ).evaluate("el => el.click()")

    @log_method_exceptions
    def save(self) -> None:
        """Deliberately does not clear_cache()/navigate away afterward.

        Live investigation found the backend's own read-path for a
        saved field can lag several minutes behind the write (separate
        from - and not fixed by - clear_cache(), which only affects the
        public-facing cache). The field DOES correctly show its own
        just-saved value immediately after Save, with no reload, in the
        same page/session - so any read-back in the same test should
        happen right here, before a re-navigation (e.g. via
        _ensure_open()) forces a refetch that can return stale data.
        """
        with allure.step("Save Local Blogs"):
            before_modified = self.get_last_modified_text()
            # JS click, not a coordinate-based one - see
            # MPCompanyBlogPage.select_category for why.
            self.page.get_by_role(
                "button", name="Save", exact=True
            ).evaluate("el => el.click()")
            # A "Success: ..." banner was observed during exploration, but
            # its exact wording was not reliably reproducible in
            # automated runs - the "Last Modified By" timestamp changing
            # is the functional proxy that the save actually took effect.
            expect(
                self.page.get_by_text("Last Modified By", exact=False)
            ).not_to_have_text(before_modified, timeout=self.timeout)
