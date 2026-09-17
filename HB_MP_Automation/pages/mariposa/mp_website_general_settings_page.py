import re

import allure
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation


class MPWebsiteGeneralSettingsPage:
    """Website General Settings, configured under HB Settings' Website
    (Mariposa) app - a single company-wide record (confirmed live: no
    "Select Property" picker anywhere on this panel, unlike Name and
    Address Info).

    Confirmed live: this "Phone Number" is the corporate/homepage
    number - it is NOT meant to represent any one property, so tests
    should read it for comparison only, never set it to simulate a
    single property's number."""

    @log_method_exceptions
    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation, hb_base_url: str
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        self.hb_dashboard_url = hb_base_url.rstrip("/").removesuffix("/login") + "/dashboard"

    @log_method_exceptions
    def open(self) -> None:
        with allure.step("Open Website General Settings"):
            # See HBNameAndAddressInfoPage.open's identical guard - a
            # test that already navigated this page to the MP storefront
            # (a different domain) before calling open() again leaves
            # open_settings_panel() hunting for an HB-only button that
            # doesn't exist there, retrying for several minutes before
            # failing rather than failing fast.
            if not self.page.url.startswith(self.hb_dashboard_url.rsplit("/dashboard", 1)[0]):
                self.page.goto(self.hb_dashboard_url, wait_until="commit")
            self.nav.open_settings_panel()
            link = self.page.get_by_role("listitem").filter(
                has_text=re.compile(r"^Website General Settings$")
            ).first
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
            expect(
                self.page.get_by_role("textbox", name="Enter Phone Number")
            ).to_be_visible(timeout=self.timeout)
            # Same async-fetch race as HBNameAndAddressInfoPage.open -
            # best-effort only, getters below poll independently too.
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

    @log_method_exceptions
    def _read_with_poll(self, locator: Locator) -> str:
        """See HBNameAndAddressInfoPage._read_with_poll - same
        confirmed-live race between the field rendering and its saved
        value being fetched."""
        value = locator.input_value()
        for _ in range(6):
            if value:
                break
            self.page.wait_for_timeout(500)
            value = locator.input_value()
        return value

    @log_method_exceptions
    def get_phone_number(self) -> str:
        return self._read_with_poll(
            self.page.get_by_role("textbox", name="Enter Phone Number")
        )

    @log_method_exceptions
    def get_website_sms_phone(self) -> str:
        return self._read_with_poll(
            self.page.get_by_role("textbox", name="Enter Website SMS Phone")
        )
