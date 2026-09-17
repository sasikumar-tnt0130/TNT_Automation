import time

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


class MPDailyDealPage:
    """The storefront home page's coupon banner and the "Send me the Daily
    Deal" form it opens (old Robot Lead_Management CouponClick suite).
    Confirmed live 2026-09-14 (uat_storoutlet storefront): the desktop
    banner (.desktop-banner > .promo-banner.banner) shows the coupon
    ("Test promo coupon"); clicking it opens the form with state/city
    pickers, first/last name, email, phone, a reCAPTCHA checkbox and Submit.
    The form is never submitted here - it's protected by a real reCAPTCHA
    (the storefront's own site key, not Google's test key)."""

    @log_method_exceptions
    def __init__(self, page: Page, base_url: str, timeout: float) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout = timeout

    @log_method_exceptions
    def _coupon_banner(self):
        # Two copies render; only the desktop one is visible at desktop width.
        return self.page.locator(".desktop-banner .promo-banner.banner").filter(
            has=self.page.locator(".offer_title")
        )

    @log_method_exceptions
    def _close_company_notice(self, wait_seconds: int = 8) -> None:
        # "⚠️ Storage Outlet Company Notice" (the automation-properties
        # notice) covers the banner and can appear a few seconds after the
        # page loads - later than MPUnitSearchPage._dismiss_banners runs.
        notice = self.page.get_by_text("Storage Outlet Company Notice", exact=False).first
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if notice.is_visible():
                container = notice.locator(
                    "xpath=ancestor::*[.//*[normalize-space(.)='×']][1]"
                )
                container.get_by_text("×", exact=True).first.click()
                expect(notice).to_be_hidden(timeout=self.timeout)
                return
            self.page.wait_for_timeout(500)

    @log_method_exceptions
    def open_home_daily_deal(self) -> str:
        """Opens the home page, clicks the coupon banner and returns the
        coupon's title."""
        with allure.step("Open the home page coupon (Daily Deal)"):
            MPUnitSearchPage(self.page, self.base_url, self.timeout).open_storefront()
            banner = self._coupon_banner().first
            expect(banner).to_be_visible(timeout=self.timeout)
            self._close_company_notice()
            title = banner.locator(".offer_title").first
            coupon_title = (title.text_content() or "").strip()
            title.click()
            expect(self.page.get_by_text("Send me the Daily Deal").first).to_be_visible(
                timeout=self.timeout
            )
            return coupon_title

    @log_method_exceptions
    def assert_daily_deal_form(self) -> None:
        with allure.step("The Daily Deal form shows its fields, reCAPTCHA and Submit"):
            for field in (
                "select#facility-state",
                "select#facility-city",
                "#email_first_name",
                "#email_last_name",
                "#email_email",
                "#phone_dailydeal",
            ):
                expect(self.page.locator(field).first).to_be_attached(timeout=self.timeout)
            for field in ("#email_first_name", "#email_last_name", "#email_email", "#phone_dailydeal"):
                expect(self.page.locator(field).first).to_be_visible(timeout=self.timeout)
            expect(self.page.locator('iframe[title="reCAPTCHA"]').first).to_be_visible(
                timeout=self.timeout
            )
            expect(self.page.get_by_role("button", name="Submit", exact=True)).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def close_daily_deal(self) -> None:
        with allure.step("Close the Daily Deal form without submitting"):
            close_icons = self.page.locator('img[alt="close"]')
            for index in range(close_icons.count()):
                if close_icons.nth(index).is_visible():
                    close_icons.nth(index).click()
                    break
            expect(self.page.get_by_role("button", name="Submit", exact=True)).to_be_hidden(
                timeout=self.timeout
            )
