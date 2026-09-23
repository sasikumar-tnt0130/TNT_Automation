import re
from urllib.parse import urlparse

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from config.config_reader import EnvironmentConfig
from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


# Transient HB login failures (rate limit / session / flaky auth).
_LOGIN_ERROR = re.compile(
    r"invalid|incorrect|unable to log|login failed|something went wrong|"
    r"try again|authentication|unauthorized|error",
    re.IGNORECASE,
)
# Shown when /dashboard is hit without a session (redirect to
# /login?redirect=%2Fdashboard) — not a failed credential submit.
_SESSION_REDIRECT_BANNER = re.compile(
    r"you are not logged in|please log in to continue",
    re.IGNORECASE,
)
# Full-URL match for the dashboard *path* only. A bare `/dashboard` also
# matches `login?redirect=/dashboard` and falsely treats the login page as
# success (live 2026-09-22 clickwrap setup — #search-box never appears).
_DASHBOARD_URL = re.compile(
    r"^https?://[^/?#]+/dashboard(?:/|\?|#|$)",
    re.IGNORECASE,
)


class HBLoginPage:
    @log_method_exceptions
    def __init__(
        self, page: Page, environment_config: EnvironmentConfig, timeout: float
    ) -> None:
        self.page = page
        self.browser_context = page.context
        self.base_url = environment_config.hb_base_url
        self.username_value = environment_config.hb_username
        self.password_value = environment_config.hb_password
        # Always the login route — base_url alone can redirect oddly and
        # skips the form when already on /login?redirect=… (live 2026-09-22).
        base_app = self.base_url.rstrip("/").removesuffix("/login")
        self.login_url = f"{base_app}/login"
        self.timeout = timeout
        self._bind_page_locators(page)

    def _bind_page_locators(self, page: Page) -> None:
        self.page = page
        if page is not None and not page.is_closed():
            try:
                self.browser_context = page.context
            except Exception:
                pass
        # Prefer input#username — get_by_placeholder("Username") also matches
        # the wrapping div#username (strict-mode violation, live 2026-09-22).
        self.username = page.locator("input#username")
        self.password = page.locator("input#password")
        self.login_button = page.get_by_role("button", name="Login")

    def rebind_page(self, page: Page) -> None:
        """Point this helper at a new tab in the same HB context (video slice)."""
        self._bind_page_locators(page)

    @staticmethod
    def _url_path(url: str) -> str:
        return (urlparse(url or "").path or "").rstrip("/") or "/"

    def _on_login_url(self, url: str | None = None) -> bool:
        path = self._url_path(url if url is not None else (self.page.url or ""))
        return path.lower() == "/login" or path.lower().endswith("/login")

    def _on_dashboard_url(self, url: str | None = None) -> bool:
        path = self._url_path(url if url is not None else (self.page.url or ""))
        return path.lower() == "/dashboard" or path.lower().endswith("/dashboard")

    def _on_hb_app(self, url: str, base: str) -> bool:
        return bool(url) and url.startswith(base.rstrip("/"))

    def _login_form_visible(self, timeout: float = 500) -> bool:
        try:
            return self.username.is_visible(timeout=timeout)
        except Exception:
            return False

    def _dashboard_shell_ready(self, timeout: float = 500) -> bool:
        """True when the logged-in dashboard chrome is present (#search-box).

        A bare ``/dashboard`` URL is not enough — the SPA can briefly show
        that path with an empty document (aria only ``contentinfo``, zero
        cookies) before redirecting to ``/login?redirect=…`` (live
        2026-09-22 create_hb_admin_session / clickwrap APW).
        """
        try:
            return self.page.locator("#search-box").is_visible(timeout=timeout)
        except Exception:
            return False

    def _wait_for_dashboard_shell_or_login_form(self) -> None:
        """After goto /dashboard: real shell, or login form — not URL alone."""
        try:
            self.page.wait_for_function(
                """() => {
                    const path = (location.pathname || '').replace(/\\/+$/, '') || '/';
                    if (document.querySelector('#search-box')) return true;
                    if (/\\/login$/i.test(path)) {
                        const user = document.querySelector(
                            'input#username, input[placeholder="Username"], '
                            + 'input[name="username"]'
                        );
                        return !!(user && user.offsetParent !== null);
                    }
                    return false;
                }""",
                timeout=min(self.timeout, 30000),
            )
        except PlaywrightTimeoutError:
            pass

    # Back-compat name used by callers / older steps.
    def _wait_for_dashboard_or_login_form(self) -> None:
        self._wait_for_dashboard_shell_or_login_form()

    @log_method_exceptions
    def ensure_logged_in(self) -> None:
        """Reuse an already-authenticated HB window; login only if needed.

        When this page already has the dashboard shell (``#search-box``) or
        another authenticated HB route without the login form, do nothing.
        Otherwise run open_login_page → credentials.

        Never treat a bare ``/dashboard`` URL as logged in — the SPA can
        land there with an empty shell and zero cookies before bouncing to
        ``/login?redirect=%2Fdashboard`` (live 2026-09-22).
        """
        with allure.step("Ensure HB logged in"):
            url = self.page.url or ""
            base_app = self.base_url.rstrip("/").removesuffix("/login")

            # Already on login (incl. ?redirect=) — fill; never early-return.
            if self._on_login_url(url) or self._login_form_visible(timeout=2000):
                expect(self.username).to_be_visible(timeout=self.timeout)
                self.submit_login_credentials()
                self.assert_login_successful()
                return

            # Authenticated shell already up — keep the same window.
            if self._dashboard_shell_ready(timeout=2000):
                return

            # Other HB app route (Settings, etc.) without login form.
            if (
                self._on_hb_app(url, base_app)
                and not self._on_login_url(url)
                and not self._login_form_visible(timeout=500)
            ):
                # Blank SPA on /dashboard (no shell yet) must not early-return.
                if self._on_dashboard_url(url) and not self._dashboard_shell_ready(
                    timeout=waits().short
                ):
                    pass  # fall through — wait / re-login below
                else:
                    return

            # Shared tab was on Mariposa / blank — try dashboard (session or redirect).
            try:
                self.page.goto(f"{base_app}/dashboard", wait_until="commit")
            except PlaywrightTimeoutError:
                pass
            self._wait_for_dashboard_shell_or_login_form()
            url = self.page.url or ""
            if self._on_login_url(url) or self._login_form_visible(timeout=2000):
                expect(self.username).to_be_visible(timeout=self.timeout)
                self.submit_login_credentials()
                self.assert_login_successful()
                return
            if self._dashboard_shell_ready(timeout=waits().short):
                return

            if self.open_login_page():
                self.submit_login_credentials()
            self.assert_login_successful()

    @log_method_exceptions
    def ensure_on_dashboard(self) -> None:
        """Logged-in HB main shell — leave Settings / dialogs if open.

        Module ``hb_admin_session`` often sits in Settings after signing /
        Clear Cache. Tenants and Leads need ``#search-box`` on the main
        shell; clicking it while Settings' ``v-dialog`` is active times out
        (live 2026-09-18, legacy_superlease HB validation).

        Uses ``HBSettingsNavigation.close_settings_panel`` (project-wide
        one-open / one-close rule) before falling back to a dashboard goto.
        """
        with allure.step("Ensure HB dashboard (leave Settings if open)"):
            from pages.common.hb_settings_navigation import HBSettingsNavigation

            self.ensure_logged_in()
            base = self.base_url.rstrip("/").removesuffix("/login")
            dashboard_url = f"{base}/dashboard"
            nav = HBSettingsNavigation(self.page, self.timeout)
            nav.close_settings_panel()
            # Nested non-Settings dialogs (confirm modals) may remain.
            for _ in range(3):
                dialog = self.page.locator(".v-dialog__content--active").first
                if dialog.count() == 0 or not dialog.is_visible():
                    break
                self.page.keyboard.press("Escape")
                try:
                    expect(dialog).to_be_hidden(timeout=waits().short)
                except AssertionError:
                    close = dialog.locator(
                        'button[name="QA-v-card-HbIcon-mdi-close"]'
                    )
                    if close.count() > 0 and close.first.is_visible():
                        close.first.click(force=True)
            settings_still_open = nav.is_settings_panel_open()
            shell_ready = self._dashboard_shell_ready(timeout=1000)
            # Goto clears a stuck Settings overlay even when the URL already
            # says /dashboard (live 2026-09-21 after advance-days ensure).
            # Also recover blank SPA / expired session (live 2026-09-22).
            if settings_still_open or not shell_ready:
                self.page.goto(dashboard_url, wait_until="domcontentloaded")
                self._wait_for_dashboard_shell_or_login_form()
                # Expired session → /login?redirect=%2Fdashboard + banner
                # (live 2026-09-22 screenshot).
                if self._on_login_url() or self._login_form_visible(timeout=2000):
                    self.submit_login_credentials()
                self.assert_login_successful()
            else:
                expect(self.page).to_have_url(_DASHBOARD_URL, timeout=self.timeout)
                expect(self.page.locator("#search-box")).to_be_visible(
                    timeout=self.timeout
                )

    @log_method_exceptions
    def open_login_page(self) -> bool:
        """Returns True if a fresh login form was reached, False if this
        browser context was already authenticated (login_url redirected
        straight to /dashboard instead) - confirmed live (2026-09-08,
        stage): happens whenever a second LeaseConfigurationSetup is
        built against the same hb_login_page/page later in the same
        test (e.g. an autouse teardown fixture restoring a setting).
        Callers skip submit_login_credentials in that case - there's no
        form to submit.
        #
        # Confirmed live: this navigation can hang well past a normal
        # page load (raw HTTP to the same URL responds in ~1s) - a
        # render-blocking third-party script (e.g. an ERR_CONNECTION_RESET
        # seen live against Apple Pay's CDN) can stall the
        # domcontentloaded event a goto would wait on, independent of
        # this app's own server health. "commit" only waits for the
        # navigation itself, so it isn't gated on that stalled script.
        #
        # Also confirmed live: even once the navigation itself resolves,
        # the SPA can occasionally fail to fully boot - the Username
        # field never renders at all (not just slowly), leaving an empty
        # page. A fresh goto (this loop's next attempt) reloads past
        # that stuck client-side state, the same recovery already proven
        # for the Settings panel in
        # HBSettingsNavigation.open_settings_panel. Only the final
        # attempt waits the full timeout - earlier attempts fail fast so
        # a stuck render gets retried instead of burning the whole
        # budget on one attempt that isn't coming back.
        """
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self.page.goto(self.login_url, wait_until="commit")
            except PlaywrightTimeoutError as error:
                last_error = error
                continue
            try:
                expect(self.username).to_be_visible(
                    timeout=self.timeout if attempt == 2 else 20000
                )
                return True
            except AssertionError as error:
                # Checked only here, not immediately after goto() above -
                # confirmed live (2026-09-08, stage): the already-
                # authenticated redirect to /dashboard is client-side
                # (this SPA's own router), not an HTTP redirect, so
                # self.page.url right after "commit" can still show
                # login_url even though the redirect is already
                # underway - checking too early raced it and fell
                # through to a real "Username never showed" failure
                # instead. By the time the Username wait above has
                # timed out, that redirect (if any) has had the whole
                # wait to land.
                if self._on_dashboard_url():
                    return False
                last_error = error
                # Blank SPA boot (aria often only "contentinfo") — reload
                # before the next goto so the next attempt is not stuck
                # on the same dead document.
                try:
                    self.page.reload(wait_until="commit")
                except Exception:
                    pass
        raise last_error

    @log_method_exceptions
    def _login_error_visible(self) -> bool:
        """True when a credentials/auth failure alert is showing.

        Ignores the session-redirect banner ("You are not logged in. Please
        log in to continue.") on ``/login?redirect=…`` — that is expected
        before submit, not a failed Login click.
        """
        for locator in (
            self.page.locator(".v-alert").filter(visible=True),
            self.page.locator(".error--text, .v-messages__message").filter(
                visible=True
            ),
            self.page.get_by_role("alert").filter(visible=True),
        ):
            try:
                if locator.count() == 0:
                    continue
                text = (locator.first.inner_text(timeout=500) or "").strip()
                if not text:
                    continue
                if _SESSION_REDIRECT_BANNER.search(text):
                    continue
                if text and _LOGIN_ERROR.search(text):
                    return True
            except Exception:
                continue
        return False

    @log_method_exceptions
    def _still_on_login_form(self) -> bool:
        try:
            return self.login_button.is_visible() and self.username.is_visible()
        except Exception:
            return False

    @log_method_exceptions
    def submit_login_credentials(self) -> None:
        """Fill credentials and click Login; on login error, click Login again.

        Transient HB auth failures sometimes leave the form up with an error
        banner — retrying the Login click (after a short pause) recovers
        without reopening the page.
        """
        expect(self.username).to_be_visible(timeout=self.timeout)
        self.username.fill(self.username_value)
        self.password.fill(self.password_value)
        max_attempts = 3
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            with allure.step(
                "Click Login" + (f" (retry {attempt})" if attempt else "")
            ):
                expect(self.login_button).to_be_visible(timeout=self.timeout)
                self.login_button.click()
            try:
                expect(self.page).to_have_url(
                    _DASHBOARD_URL,
                    timeout=waits().long if attempt == 0 else waits().medium,
                )
                return
            except AssertionError as error:
                last_error = error
                if attempt == max_attempts - 1:
                    break
                if self._login_error_visible() or self._still_on_login_form():
                    with allure.step(
                        "Login error or form still shown — click Login again"
                    ):
                        self.page.wait_for_timeout(waits().settle_short)
                        if self._still_on_login_form():
                            self.username.fill(self.username_value)
                            self.password.fill(self.password_value)
                        continue
                break
        if last_error is not None:
            raise last_error

    @log_method_exceptions
    def assert_login_successful(self) -> None:
        # submit_login_credentials already waits for /dashboard when it can;
        # this is the final assert for callers that submit separately.
        if self._still_on_login_form() or self._login_error_visible():
            with allure.step("Login not complete — click Login again"):
                if self._still_on_login_form():
                    self.username.fill(self.username_value)
                    self.password.fill(self.password_value)
                self.login_button.click()
        expect(self.page).to_have_url(_DASHBOARD_URL, timeout=self.timeout)
        # URL alone is insufficient — blank SPA can sit on /dashboard with
        # zero cookies before bouncing to login (live 2026-09-22).
        expect(self.page.locator("#search-box")).to_be_visible(timeout=self.timeout)
        # Confirmed live: this dashboard's own background polling/
        # websocket traffic (task center counts, charm widgets, etc.)
        # never lets the network stay quiet for the 500ms Playwright's
        # "networkidle" requires - domcontentloaded and load both fire
        # fine, but networkidle structurally never resolves here.
        # Already best-effort (the timeout is swallowed, nothing
        # downstream requires it to succeed), so waiting the full
        # self.timeout (up to 120s) for something confirmed to never
        # happen was pure waste, paid on every single login across
        # every test. A short bounded wait still gives genuinely-quiet
        # environments their real networkidle; a busy one like this
        # gives up fast instead of burning the whole budget for nothing.
        try:
            self.page.wait_for_load_state("networkidle", timeout=waits().short)
        except PlaywrightTimeoutError:
            pass
