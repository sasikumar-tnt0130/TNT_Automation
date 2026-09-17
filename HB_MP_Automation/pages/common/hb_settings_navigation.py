import re

import allure
from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


class HBSettingsNavigation:
    """Settings-panel navigation shared by Hummingbird and Mariposa (Website) settings pages."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout
        self.property_name: str | None = None
        # Set by callers after a real Website-settings Save; clear_cache()
        # no-ops unless this is True (or force=True).
        self._website_cache_clear_pending: bool = False

    @log_method_exceptions
    def mark_website_cache_clear_pending(self) -> None:
        """Record that Website settings changed and the storefront cache
        needs a Clear Cache before the next storefront read.

        No Allure step here — callers already step the Save; clear_cache()
        reports whether the flush ran or was skipped."""
        self._website_cache_clear_pending = True

    @log_method_exceptions
    def clear_cache(self, *, force: bool = False) -> None:
        """Flush Website Clear Cache when a clear is pending, or when
        `force=True` (Two-Step retry / recovery paths that must clear
        even with no local Save in this session)."""
        if not force and not self._website_cache_clear_pending:
            with allure.step("Skip Clear Cache (nothing pending)"):
                return
        reason = (
            "forced recovery"
            if force
            else "settings changed"
        )
        with allure.step(f"Clear website cache ({reason})"):
            self.open_settings_panel()
            clear_cache_link = self.page.get_by_text("Clear Cache", exact=True)
            if not clear_cache_link.is_visible():
                self.switch_app_filter_to_website()
            expect(clear_cache_link).to_be_visible(timeout=self.timeout)
            clear_cache_link.click()
            self.switch_app_filter_to_website()
            clear_btn = self.page.get_by_role(
                "button", name="Clear Cache", exact=True
            )
            expect(clear_btn).to_be_visible(timeout=self.timeout)
            # Confirmed live 2026-09-16: a prior clear can leave the button
            # in v-btn--loading with an overlay <span> intercepting clicks.
            # Wait for loading to finish, then force-click if needed.
            try:
                expect(clear_btn).not_to_have_class(
                    re.compile(r"v-btn--loading"), timeout=waits().long
                )
            except AssertionError:
                pass
            try:
                clear_btn.click(timeout=waits().medium)
            except PlaywrightTimeoutError:
                clear_btn.click(force=True)
            # Wait for this click's own loading cycle to finish before
            # reading the outcome - otherwise a leftover "Failed to Warm
            # … Cache" toast from an earlier attempt can look like success
            # immediately (2026-09-17, uat_storoutlet).
            try:
                expect(clear_btn).not_to_have_class(
                    re.compile(r"v-btn--loading"), timeout=waits().long
                )
            except AssertionError:
                pass
            success_message = self.page.get_by_text(
                "Cache cleared successfully!", exact=True
            )
            # Confirmed live 2026-09-17 (uat_storoutlet): Clear Cache can
            # finish the website flush but fail "Warm Homepage Middleware
            # Cache" and never show the success toast - that warm step is
            # not required for Two-Step/storefront to pick up Saves.
            warm_failed = self.page.get_by_text(
                re.compile(r"Failed to Warm .* Middleware Cache", re.I)
            )
            # A single click's own "success" message isn't a reliable
            # signal that a stale value is actually gone elsewhere (e.g.
            # FMS Initial Setup's Two-Step toggle reading Clickwrap/
            # Super Lease from before this clear - see
            # LeaseConfigurationSetup.
            # enable_two_step_clickwrap_and_super_lease's own caching
            # comments) - callers that can verify a specific downstream
            # effect (e.g. MPFMSInitialSetupPage.set_two_step) retry
            # clear_cache(force=True) themselves against that real signal,
            # rather than this generic method (shared by layout settings
            # too, which have no such signal to check) always clicking
            # multiple times whether or not it was actually needed.
            try:
                expect(success_message).to_be_visible(timeout=waits().medium)
            except AssertionError:
                if not (warm_failed.count() > 0 and warm_failed.first.is_visible()):
                    expect(success_message).to_be_visible(timeout=self.timeout)
            self._website_cache_clear_pending = False

    @log_method_exceptions
    def _dismiss_blocking_dialog(self) -> None:
        """Some blocking modal other than the Settings-permission error
        (that one is handled explicitly by callers, since retrying past
        it is pointless) can appear unprompted and intercepts clicks on
        the rest of the page (Vuetify's persistent-dialog overlay) -
        Escape alone doesn't always close it. Prefer the dialog's own
        close/cancel control; Escape is the last resort."""
        dialog = self.page.locator(".v-dialog__content--active").first
        if dialog.count() == 0 or not dialog.is_visible():
            return
        close_button = dialog.locator('button[name="QA-v-card-HbIcon-mdi-close"]')
        cancel_button = dialog.get_by_role("button", name="Cancel", exact=True)
        if close_button.count() > 0 and close_button.first.is_visible():
            close_button.first.click()
        elif cancel_button.count() > 0 and cancel_button.first.is_visible():
            cancel_button.first.click()
        else:
            self.page.keyboard.press("Escape")

    @log_method_exceptions
    def _close_live_agent_notification(self) -> None:
        """A "Need to talk to a live agent?" banner can render pinned to
        the dashboard (seen right after login, and again after a
        reload) and sit on top of the Settings button, intercepting its
        click. Same pattern as HBMoveOutPage/HBLeadManagementPage's own
        copy of this - kept here too since Settings navigation is a
        separate entry point neither of those pages goes through."""
        live_agent_notification = self.page.get_by_text(
            "Need to talk to a live agent?", exact=True
        )
        # Scoped to the banner's own tooltip: an unscoped ".mdi-close" .first
        # can be an open drawer's or dialog's own close X (confirmed live
        # 2026-09-13 - it closed the move-out drawer, see HBMoveOutPage).
        close_notification = (
            self.page.locator(".v-tooltip__content.custom-tooltip-popup")
            .filter(has_text="Need to talk to a live agent?")
            .locator(".mdi-close")
        )
        if live_agent_notification.count() > 0 and live_agent_notification.first.is_visible():
            if close_notification.count() > 0 and close_notification.first.is_visible():
                try:
                    close_notification.first.click(timeout=waits().short)
                except PlaywrightTimeoutError:
                    pass

    @log_method_exceptions
    def open_settings_panel(self) -> None:
        with allure.step("Open Settings panel"):
            # The app-filter trigger button's own accessible name changes
            # with whatever is currently checked (hummingbird/website/
            # storagefront, alone or combined, e.g. "hummi ..(+1
            # others)") - matching on "hummi" text broke once a prior fix
            # made it possible for hummingbird to end up fully unchecked,
            # at which point the button's name no longer contains that
            # text at all. Identified structurally instead, by the
            # "Filter" textbox nested inside it, which is stable
            # regardless of selection state and only exists while the
            # Settings panel is open. Not scoped to the "complementary"
            # landmark - there are two on this page (the main dashboard
            # sidebar, and the Settings panel itself nested inside a
            # separate "document" element), which made that scoping
            # ambiguous/unreliable. "Filter" is distinctive enough on
            # its own.
            # The actual trigger is a Vuetify <div role="button"
            # class="v-input__slot">, not a real <button> tag (confirmed
            # via live DOM inspection) - xpath's "button" step matches
            # HTML tag names literally, so ancestor::button never
            # matched anything at all, regardless of [1] vs [last()].
            # ancestor::*[@role='button'] matches by ARIA role instead.
            app_selector = self.page.get_by_role(
                "textbox", name="Filter"
            ).locator("xpath=ancestor::*[@role='button'][last()]")
            access_error = self.page.get_by_text(
                "Unable to Access Settings", exact=True
            )
            settings_panel = app_selector.or_(access_error)
            if settings_panel.is_visible():
                if access_error.is_visible():
                    raise AssertionError(
                        "The configured account does not have permission to access Settings."
                    )
                return
            settings_button = self.page.locator(
                'button[name="QA-v-list-item-HbIcon-mdi-settings"]'
            )
            self._dismiss_blocking_dialog()
            self._close_live_agent_notification()
            opened = False
            for _ in range(3):
                # This dialog renders as a persistent Vuetify modal - once
                # open, its own overlay blocks the next click on
                # settings_button before that click can ever time out
                # cleanly, so check for it explicitly rather than let a
                # blocked click attempt burn a full 15s/70s timeout only
                # to eventually reach the same conclusion below.
                if access_error.is_visible():
                    raise AssertionError(
                        "The configured account does not have permission to access Settings."
                    )
                try:
                    # force=True: some other overlay (unrelated to this
                    # error dialog) can sit in front of settings_button
                    # before it's ever clicked, causing a normal click to
                    # wait/retry internally for the entire timeout without
                    # ever returning control here to re-check. A forced
                    # click bypasses actionability/interception checks
                    # and clicks straight through via coordinates -
                    # exactly what a standalone diagnostic script
                    # confirmed reliably reaches the real state
                    # underneath (either the Settings panel, or this
                    # access_error dialog, both handled below).
                    settings_button.click(timeout=waits().long, force=True)
                    # Confirmed live: the click can register but the
                    # panel just never renders (no error, no Filter
                    # textbox - a dead client-side state), rather than
                    # being slow. A 5s check is enough to tell "still
                    # loading" from "never coming" without burning the
                    # full 15s on a state that won't resolve on its own -
                    # a full reload resets it before the next attempt.
                    expect(settings_panel).to_be_visible(timeout=waits().short)
                    opened = True
                    break
                except (AssertionError, PlaywrightError):
                    self.page.reload(wait_until="commit")
                    self._dismiss_blocking_dialog()
                    self._close_live_agent_notification()
                    continue
            if not opened:
                if access_error.is_visible():
                    raise AssertionError(
                        "The configured account does not have permission to access Settings."
                    )
                try:
                    settings_button.click(timeout=self.timeout, force=True)
                    expect(settings_panel).to_be_visible(timeout=self.timeout)
                except (AssertionError, PlaywrightError):
                    # Last resort: the Settings panel's own trigger button
                    # can end up in a state where clicking it just doesn't
                    # do anything (confirmed live: the Filter textbox
                    # never appears despite every click/dismiss retry
                    # above) - a full page reload resets that client-side
                    # state, so retry the whole open once more from a
                    # clean load before giving up for good.
                    self.page.reload(wait_until="commit")
                    self._dismiss_blocking_dialog()
                    if access_error.is_visible():
                        raise AssertionError(
                            "The configured account does not have permission to access Settings."
                        )
                    settings_button.click(timeout=self.timeout, force=True)
                    expect(settings_panel).to_be_visible(timeout=self.timeout)
            # Confirmed live: right after login, several Settings-related
            # API calls transiently 401 before self-resolving to 200 a
            # few seconds later (stage's auth token isn't fully
            # propagated/accepted immediately post-login) - that race can
            # leave access_error's text visible in the DOM (e.g. a
            # toast/banner) even after the real panel (app_selector, the
            # "Filter" textbox) has already loaded successfully
            # underneath it. Only treat this as a genuine permission
            # failure if the real panel never actually showed up -
            # otherwise this was flagging working runs as broken.
            if access_error.is_visible() and not app_selector.is_visible():
                raise AssertionError(
                    "The configured account does not have permission to access Settings."
                )

    @log_method_exceptions
    def switch_app_filter_to_website(self) -> None:
        with allure.step("Switch Settings app filter to Website"):
            # See open_settings_panel for why this is identified
            # structurally (via the nested "Filter" textbox, unscoped -
            # not via the ambiguous "complementary" landmark) rather than
            # by matching "hummi" in the button's text.
            application_selector = self.page.get_by_role(
                "textbox", name="Filter"
            ).locator("xpath=ancestor::*[@role='button'][last()]")
            website_application = self.page.get_by_role(
                "option", name="website", exact=True
            )
            # Multi-select checkbox list, not single-select. Local Blogs'
            # property picker was found to need BOTH "hummingbird" and
            # "website" checked together - checking website while
            # leaving hummingbird's default-checked state alone (rather
            # than unchecking it) is what actually works, confirmed live:
            # with only "website" checked, the property picker showed
            # "No data available" for a property that exists and loads
            # fine once both are checked.
            for _ in range(3):
                expect(application_selector).to_be_visible(timeout=self.timeout)
                application_selector.click()
                expect(website_application).to_be_visible(timeout=self.timeout)
                website_application.click()
                self.page.keyboard.press("Escape")
                if not website_application.is_visible():
                    break

    @log_method_exceptions
    def select_property(self, property_name: str) -> None:
        with allure.step(f"Select property: {property_name}"):
            self.property_name = property_name
            property_select = self.page.get_by_role(
                "textbox", name="Select Property", exact=True
            )
            property_select.click()
            property_option = self.page.get_by_text(
                re.compile(rf".*{re.escape(property_name)}.*", re.IGNORECASE)
            ).last
            expect(property_option).to_be_visible(timeout=self.timeout)
            property_option.click()
