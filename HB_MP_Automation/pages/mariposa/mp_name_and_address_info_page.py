import re

import allure
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation
from common_utils.waits import waits


class MPNameAndAddressInfoPage:
    """Name and Address Info, configured under HB Settings' Website
    (Mariposa) app - per-property (gated by its own "Select Property"
    picker, confirmed live distinct from Website General Settings'
    single company-wide record).

    Confirmed live this is the source of the storefront's per-property
    contact numbers: "Phone"/"SMS Phone" feed the header quick-call
    icon and the "Current Tenants" panel entries, "New Customer
    Phone"/"New Customer SMS Phone" feed the "New Customers" panel
    entries (see common_utils/storefront_contact_numbers.py). Saving
    here has no visible confirmation banner - persistence is confirmed
    live by reading the field back after a fresh navigation, which
    save() below does not do automatically (matching
    MPLocalBlogsPage.save's reasoning: a same-session read-back would
    otherwise race a reload)."""

    @log_method_exceptions
    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation, hb_base_url: str
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        self.hb_dashboard_url = hb_base_url.rstrip("/").removesuffix("/login") + "/dashboard"

    @log_method_exceptions
    def open(self, property_id: str) -> None:
        with allure.step(f"Open Name and Address Info for property: {property_id}"):
            # Confirmed live: a test that already navigated this same
            # page to the MP storefront (a different domain) before
            # calling open() again for another property leaves
            # HBSettingsNavigation.open_settings_panel() hunting for an
            # HB-only button that doesn't exist on the storefront page -
            # it retries through several escalating timeouts (multiple
            # minutes) before eventually failing, rather than failing
            # fast. Same idiom as MPLocalBlogsPage.open_local_blogs.
            if not self.page.url.startswith(self.hb_dashboard_url.rsplit("/dashboard", 1)[0]):
                self.page.goto(self.hb_dashboard_url, wait_until="commit")
            self.nav.open_settings_panel()
            link = self.page.get_by_role("listitem").filter(
                has_text=re.compile(r"^Name and Address Info$")
            ).first
            for _ in range(3):
                self.nav.switch_app_filter_to_website()
                try:
                    expect(link).to_be_visible(timeout=waits().long)
                    break
                except AssertionError:
                    continue
            else:
                expect(link).to_be_visible(timeout=self.timeout)
            link.click()
            self.nav.select_property(property_id)
            expect(
                self.page.get_by_role("textbox", name="Enter Phone")
            ).to_be_visible(timeout=self.timeout)
            # Selecting a property mounts the form immediately, then
            # fetches its saved values asynchronously (same race
            # confirmed live on MPLocalBlogsPage.open_local_blogs) - a
            # read right after this method returns can otherwise see
            # every field as empty even though real data is saved.
            # Best-effort only: not fatal if an environment never goes
            # fully idle, since the getters below poll independently too.
            try:
                self.page.wait_for_load_state("networkidle", timeout=waits().medium)
            except PlaywrightTimeoutError:
                pass

    @log_method_exceptions
    def _read_with_poll(self, locator: Locator) -> str:
        """Confirmed live: the Phone/SMS/New Customer fields can all
        still read as empty for up to ~1s after open() returns, even
        after its own networkidle wait, because the value-populating
        fetch can outlast that (same race MPLocalBlogsPage.get_h1_title
        guards against). Polls briefly rather than trusting the first
        read - a field that's still empty after this either genuinely
        has no value configured (e.g. Irvine's SMS Phone) or the fetch
        is unusually slow; either way, returning the last-seen value is
        more honest than an artificially extended wait for something
        that may never become non-empty."""
        value = locator.input_value()
        for _ in range(6):
            if value:
                break
            self.page.wait_for_timeout(waits().poll_interval)
            value = locator.input_value()
        return value

    @log_method_exceptions
    def get_phone(self) -> str:
        return self._read_with_poll(
            self.page.get_by_role("textbox", name="Enter Phone", exact=True)
        )

    @log_method_exceptions
    def get_new_customer_phone(self) -> str:
        return self._read_with_poll(
            self.page.get_by_role("textbox", name="Enter New Customer Phone")
        )

    @log_method_exceptions
    def get_sms_phone(self) -> str:
        return self._read_with_poll(
            self.page.get_by_role("textbox", name="Enter SMS Phone", exact=True)
        )

    @log_method_exceptions
    def get_new_customer_sms_phone(self) -> str:
        return self._read_with_poll(
            self.page.get_by_role("textbox", name="Enter New Customer SMS Phone")
        )

    @log_method_exceptions
    def set_phone(self, value: str) -> None:
        with allure.step(f"Set Name and Address Info Phone: {value}"):
            self.page.get_by_role("textbox", name="Enter Phone", exact=True).fill(value)

    @log_method_exceptions
    def set_new_customer_phone(self, value: str) -> None:
        with allure.step(f"Set Name and Address Info New Customer Phone: {value}"):
            self.page.get_by_role("textbox", name="Enter New Customer Phone").fill(value)

    @log_method_exceptions
    def set_sms_phone(self, value: str) -> None:
        with allure.step(f"Set Name and Address Info SMS Phone: {value}"):
            self.page.get_by_role("textbox", name="Enter SMS Phone", exact=True).fill(value)

    @log_method_exceptions
    def set_new_customer_sms_phone(self, value: str) -> None:
        with allure.step(f"Set Name and Address Info New Customer SMS Phone: {value}"):
            self.page.get_by_role(
                "textbox", name="Enter New Customer SMS Phone"
            ).fill(value)

    @log_method_exceptions
    def get_google_place_id(self) -> str:
        return self._read_with_poll(self.page.locator('input[placeholder="Enter Google Place ID"]'))

    @log_method_exceptions
    def get_yelp_business_id(self) -> str:
        return self._read_with_poll(self.page.locator('input[placeholder="Enter Yelp Business ID"]'))

    @log_method_exceptions
    def sync_reviews_button(self) -> Locator:
        # Confirmed live 2026-09-14 (uat_storoutlet): the form's Reviews
        # section, below Google Place ID / Yelp Business ID. A property never
        # synced shows no last-sync date under it.
        return self.page.get_by_role("button", name="Sync Reviews", exact=True)

    @log_method_exceptions
    def save(self) -> None:
        with allure.step("Save Name and Address Info"):
            self.page.get_by_role("button", name="Save", exact=True).click()
            # Confirmed live: the storefront (MP) can keep serving a
            # property's previous phone number for some time after a save
            # here, even though HB itself reflects the new value
            # immediately on read-back. Callers flush once via
            # nav.clear_cache / flush_website_cache after all Saves.
