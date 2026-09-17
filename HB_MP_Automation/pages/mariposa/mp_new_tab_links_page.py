import re
from urllib.parse import urlparse

import allure
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage
from common_utils.waits import waits

# The storefront footer's general pages -> their paths.
FOOTER_PAGES = {
    "Sitemap": "/sitemap/",
    "Privacy Policy & Terms": "/legal-pages/",
    "Contact us": "/contact-us/",
}
# A social link's network (its title) -> the sites it may open.
SOCIAL_SITES = {
    "facebook": ("facebook.com",),
    "twitter": ("twitter.com", "x.com"),
    "x": ("twitter.com", "x.com"),
    "instagram": ("instagram.com",),
    "linkedin": ("linkedin.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "pinterest": ("pinterest.com",),
    "tiktok": ("tiktok.com",),
    "yelp": ("yelp.com",),
}


class MPNewTabLinksPage(MPUnitSearchPage):
    """Storefront links that open in a new tab - the old Robot
    Mariposa/Open_links_newTab suite.

    Confirmed live 2026-09-14 (uat_storoutlet,
    https://tenantv2-strat.storagefront.com/):
    - The footer's Sitemap (/sitemap/), Privacy Policy & Terms
      (/legal-pages/) and Contact us / Contact Us (/contact-us/) links carry
      target="_blank"; a click opens a new tab (e.g. "Storage Outlet - UAT
      Site Map - ...") and leaves the page as it was.
    - A property landing page has a div.social-row of target="_blank" links,
      each an image whose title names the network ("Facebook", "Twitter");
      Bellflower's "Twitter" link points to facebook.com/tenantinc.
    - The home page has no social links, and neither page lists company
      pages or blogs.
    - The "Storage Outlet Company Notice" (the automation properties notice)
      covers the whole page a few seconds after each load and is never
      remembered; only its own "×" closes it - its Continue stays disabled
      until "I have read and understood this notice" is ticked.
    """

    @log_method_exceptions
    def _close_company_notice(self) -> None:
        # The shared _dismiss_banners clicks the notice's text, which doesn't
        # close it; a footer click then landed on the notice (2026-09-14).
        notice = self.page.locator("body > div").filter(has_text="Storage Outlet Company Notice").last
        close = notice.get_by_text("×", exact=True).first
        if notice.count() and notice.is_visible() and close.is_visible():
            close.click()
            expect(notice).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def _dismiss_banners(self) -> None:
        self._close_company_notice()
        super()._dismiss_banners()

    @log_method_exceptions
    def _open_new_tab(self, link: Locator) -> Page:
        # The notice can come up after the banners were dismissed and take
        # the click - closed again and the click retried.
        for attempt in range(3):
            self._dismiss_banners()
            try:
                with self.page.context.expect_page(timeout=waits().long) as new_tab:
                    link.click(timeout=waits().medium)
                break
            except PlaywrightTimeoutError:
                if attempt == 2:
                    raise
        tab = new_tab.value
        tab.wait_for_url(lambda url: not url.startswith("about:"), timeout=self.timeout)
        return tab

    @log_method_exceptions
    def assert_footer_pages_open_in_new_tab(self) -> None:
        for name, path in FOOTER_PAGES.items():
            with allure.step(f"Footer '{name}' opens {path} in a new tab"):
                link = (
                    self.page.locator("footer")
                    .get_by_role("link", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.IGNORECASE))
                    .first
                )
                expect(link).to_be_visible(timeout=self.timeout)
                expect(link).to_have_attribute("target", "_blank")
                before = self.page.url
                tab = self._open_new_tab(link)
                try:
                    expect(tab).to_have_url(
                        re.compile(rf"^{re.escape(self.base_url)}{re.escape(path)}"), timeout=self.timeout
                    )
                    expect(tab).to_have_title(re.compile(r"\S"), timeout=self.timeout)
                finally:
                    tab.close()
                assert self.page.url == before, f"The page itself moved from {before} to {self.page.url}"

    @log_method_exceptions
    def social_link_problems(self) -> list[str]:
        """Clicks every social link on the page and returns each that doesn't
        open, in a new tab, the network its title names - all are checked
        before anything is reported."""
        links = self.page.locator("div.social-row a").filter(visible=True)
        expect(links.first).to_be_visible(timeout=self.timeout)
        problems = []
        for index in range(links.count()):
            link = links.nth(index)
            network = (link.get_attribute("title") or "").strip()
            href = link.get_attribute("href")
            with allure.step(f"Social link '{network}' ({href})"):
                sites = SOCIAL_SITES.get(network.lower())
                if not sites:
                    problems.append(f"{network!r}: not a known network ({href})")
                    continue
                if link.get_attribute("target") != "_blank":
                    problems.append(f"{network}: doesn't open in a new tab")
                    continue
                tab = self._open_new_tab(link)
                try:
                    host = urlparse(tab.url).hostname or ""
                finally:
                    tab.close()
                if not any(host == site or host.endswith("." + site) for site in sites):
                    problems.append(f"{network}: opens {host} ({href}), not {' / '.join(sites)}")
        return problems
