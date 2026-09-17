import re

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


class HBLoginPage:
    @log_method_exceptions
    def __init__(
        self, page: Page, environment_config: EnvironmentConfig, timeout: float
    ) -> None:
        self.page = page
        self.base_url = environment_config.hb_base_url
        self.username_value = environment_config.hb_username
        self.password_value = environment_config.hb_password
        self.login_url = self.base_url
        self.timeout = timeout
        self.username = page.get_by_role("textbox", name="Username")
        self.password = page.get_by_role("textbox", name="Password")
        self.login_button = page.get_by_role("button", name="Login")

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
                if re.search(r"/dashboard", self.page.url):
                    return False
                last_error = error
        raise last_error

    @log_method_exceptions
    def _login_error_visible(self) -> bool:
        """True when a login-form error/alert is showing."""
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
                    re.compile(r"/dashboard"),
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
                        self.page.wait_for_timeout(waits().short)
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
        expect(self.page).to_have_url(re.compile(r"/dashboard"), timeout=self.timeout)
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
