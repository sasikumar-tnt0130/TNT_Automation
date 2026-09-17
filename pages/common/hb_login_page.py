import re

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from config.config_reader import EnvironmentConfig
from common_utils.wrapper_methods import log_method_exceptions


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
    def submit_login_credentials(self) -> None:
        self.username.fill(self.username_value)
        self.password.fill(self.password_value)
        self.login_button.click()

    @log_method_exceptions
    def assert_login_successful(self) -> None:
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
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass
