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
    """Settings-panel navigation shared by Hummingbird and Mariposa (Website).

    Project rule — one open / one close per Settings session:
    - ``open_settings_panel`` is idempotent (no-op when already open).
    - Do **not** Escape between configure steps; Settings is one ``v-dialog``
      and Escape closes the whole panel (see ``select_property``).
    - Call ``close_settings_panel`` once when the session ends (after Clear
      Cache / payment ensure / coverage / document templates / leaving HB
      admin for storefront or tenants).
    """

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout
        self.property_name: str | None = None

    def is_settings_panel_open(self) -> bool:
        """True when the Settings fullscreen panel is still showing."""
        # Fullscreen Settings shell (Clear Cache / Payment Processing / FMS
        # all live inside this — live 2026-09-21: Escape alone can leave
        # this open so the user still sees Clear Cache / PP).
        fullscreen = self.page.locator(
            ".hb-settings-fullscreen.v-dialog--active, "
            ".v-dialog.hb-settings-fullscreen.v-dialog--active"
        ).first
        try:
            if fullscreen.count() > 0 and fullscreen.is_visible(timeout=500):
                return True
        except Exception:
            pass
        try:
            if self.page.get_by_role(
                "textbox", name="Filter"
            ).is_visible(timeout=500):
                return True
        except Exception:
            pass
        dialog = self.page.locator(".v-dialog__content--active").first
        try:
            if dialog.count() == 0 or not dialog.is_visible(timeout=500):
                return False
            return (
                dialog.get_by_role("textbox", name="Filter").count() > 0
                or dialog.get_by_role(
                    "textbox", name="Select Property", exact=True
                ).count()
                > 0
                or dialog.get_by_role(
                    "tab", name="Payment Configuration", exact=True
                ).count()
                > 0
                or dialog.get_by_role(
                    "button", name="Clear Cache", exact=True
                ).count()
                > 0
            )
        except Exception:
            return False

    def _dashboard_url(self) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(self.page.url or "")
        origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme else ""
        if not origin:
            return "/dashboard"
        return f"{origin.rstrip('/')}/dashboard"

    @log_method_exceptions
    def close_settings_panel(self) -> None:
        """Leave Settings so the dashboard shell is usable. Idempotent.

        Call once after a configure session — not between individual Saves
        or property switches inside the same session.

        Escape / the Settings X often leave Clear Cache or Payment
        Processing still on screen (live 2026-09-21). If the panel is still
        open after those attempts, navigate to ``/dashboard``.
        """
        with allure.step("Close Settings panel"):
            if not self.is_settings_panel_open():
                return
            filter_box = self.page.get_by_role("textbox", name="Filter")
            fullscreen = self.page.locator(
                ".hb-settings-fullscreen.v-dialog--active, "
                ".v-dialog.hb-settings-fullscreen.v-dialog--active, "
                ".v-dialog__content--active"
            ).first
            for _ in range(4):
                if not self.is_settings_panel_open():
                    return
                # Prefer the Settings chrome X (toolbar), not an inner card X.
                toolbar_close = fullscreen.locator(
                    ".v-toolbar__content "
                    "button[name='QA-v-card-HbIcon-mdi-close']"
                )
                close_btn = (
                    toolbar_close.first
                    if toolbar_close.count() > 0
                    else fullscreen.locator(
                        "button[name='QA-v-card-HbIcon-mdi-close']"
                    ).first
                )
                if close_btn.count() > 0 and close_btn.is_visible():
                    try:
                        close_btn.click(timeout=waits().short, force=True)
                    except PlaywrightError:
                        self.page.keyboard.press("Escape")
                else:
                    self.page.keyboard.press("Escape")
                try:
                    expect(filter_box).to_be_hidden(timeout=waits().short)
                except AssertionError:
                    pass
                if not self.is_settings_panel_open():
                    return
            # Confirmed live: Settings/FMS/Clear Cache overlay may ignore
            # Escape and leave the configure page on screen — dashboard
            # navigation discards that dialog (same recovery as
            # tests/hb/test_pay_tenant_bill_cash.py).
            if self.is_settings_panel_open():
                self.page.goto(
                    self._dashboard_url(), wait_until="domcontentloaded"
                )
                try:
                    expect(filter_box).to_be_hidden(timeout=waits().short)
                except AssertionError:
                    pass


    @log_method_exceptions
    def clear_cache(self) -> None:
        """Click Website → Clear Cache. Call once after admin Saves
        (e.g. ``LeaseConfigurationSetup.flush_website_cache``), not from
        individual page Save methods. Closes Settings when done.

        Does not block forever on the success toast: Clear Cache can finish
        the website flush but fail "Warm … Middleware Cache" and never show
        ``Cache cleared successfully!`` (live 2026-09-17 uat_storoutlet;
        again 2026-09-21 stage). That warm step is not required for
        storefront to pick up Saves — close Settings and continue.
        """
        with allure.step("Clear website cache"):
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
            try:
                expect(clear_btn).not_to_have_class(
                    re.compile(r"v-btn--loading"), timeout=waits().medium
                )
            except AssertionError:
                pass
            try:
                clear_btn.click(timeout=waits().medium)
            except PlaywrightTimeoutError:
                clear_btn.click(force=True)
            success_message = self.page.get_by_text(
                "Cache cleared successfully!", exact=True
            )
            warm_failed = self.page.get_by_text(
                re.compile(r"Failed to Warm .* Middleware Cache", re.I)
            )
            outcome = success_message.or_(warm_failed)
            # Wait for loading to finish OR an outcome toast — whichever
            # first. Cap at medium so a hung warm step cannot pin the UI
            # on Clear Cache for a full browser timeout (live 2026-09-21).
            try:
                expect(clear_btn).not_to_have_class(
                    re.compile(r"v-btn--loading"), timeout=waits().medium
                )
            except AssertionError:
                pass
            try:
                expect(outcome).to_be_visible(timeout=waits().medium)
            except AssertionError:
                allure.attach(
                    "No success/warm-fail toast after Clear Cache; "
                    "continuing (storefront still picks up Saves).",
                    name="clear-cache-no-toast",
                    attachment_type=allure.attachment_type.TEXT,
                )
            # End of Settings configure session — leave dashboard usable.
            self.close_settings_panel()

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
        """Open Settings. Idempotent — returns immediately if already open.

        Keep the panel open across configure steps; call
        ``close_settings_panel`` once when the session ends.
        """
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
            # Do not call _dismiss_blocking_dialog() here: Settings itself is
            # a ``v-dialog__content--active``, so Escape closes the whole
            # panel and "Select Property" disappears (live 2026-09-18
            # payment_gateways / clickwrap ACH).
            self.property_name = property_name
            property_select = self.page.get_by_role(
                "textbox", name="Select Property", exact=True
            )
            expect(property_select).to_be_visible(timeout=self.timeout)
            try:
                current = (property_select.input_value() or "").strip()
            except Exception:
                current = ""
            # Live display names are often longer than config
            # (e.g. hb_property_name "Bellflower" → "Storage Outlet - Bellflower").
            if current and property_name.casefold() in current.casefold():
                return

            name_re = re.compile(
                rf".*{re.escape(property_name)}.*", re.IGNORECASE
            )
            last_error: Exception | None = None
            # Empty "No data available" listbox after module handoff /
            # app-filter flake (live 2026-09-21 hosted-payments setup:
            # FMS Select Property for GARDEN GROVE). Re-tick Website and
            # reopen the picker before failing.
            for attempt in range(3):
                try:
                    self.page.keyboard.press("Escape")
                except Exception:
                    pass
                if attempt > 0:
                    try:
                        self.switch_app_filter_to_website()
                    except Exception:
                        pass
                    expect(property_select).to_be_visible(timeout=self.timeout)
                property_select.click()
                property_option = self.page.locator(
                    ".menuable__content__active [role='option'], "
                    ".v-menu__content--active [role='option'], "
                    ".menuable__content__active .v-list-item, "
                    ".v-menu__content--active .v-list-item"
                ).filter(has_text=name_re)
                if property_option.count() == 0:
                    property_option = self.page.get_by_role("option").filter(
                        has_text=name_re
                    )
                if property_option.count() == 0:
                    listbox = self.page.locator("[role='listbox']").filter(
                        has=self.page.get_by_role("option")
                    )
                    property_option = listbox.get_by_role("option").filter(
                        has_text=name_re
                    )
                try:
                    expect(property_option.first).to_be_visible(
                        timeout=waits().medium if attempt < 2 else self.timeout
                    )
                    property_option.first.click()
                    return
                except AssertionError as exc:
                    last_error = exc
                    empty = self.page.get_by_text("No data available", exact=True)
                    if empty.count() == 0 or attempt == 2:
                        raise
            if last_error is not None:
                raise last_error
