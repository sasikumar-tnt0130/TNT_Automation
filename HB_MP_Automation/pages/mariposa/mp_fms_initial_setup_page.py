import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


class MPFMSInitialSetupPage:
    """FMS Initial Setup > 2-Step Rental Process / Landing Page Layout /
    Value Tier Layout / Advance Reservation Days, configured under HB
    Settings' Website (Mariposa) app.

    Landing Page Layout has three values (confirmed live): Default, Grid
    View, List View. Confirmed live that a per-property "BLOG" accordion
    section (see MPFacilityLandingPage) renders on the storefront when
    this is set to Grid View or List View.

    Value Tier Layout is a separate setting, immediately below Landing
    Page Layout on the same form (confirmed live 2026-09-08, Garden
    Grove/GARDEN GROVE) - only two values, no "Default": Grid View, List
    View. Controls how a unit's protection-plan tiers (Economy/Standard/
    Premium) render in the tier-selection dialog (see
    MPUnitSearchPage.select_unit) - not yet confirmed live which of Grid/List
    corresponds to which rendering.

    Advance Reservation Days is a plain numeric field, separate from
    the Landing/Value Tier Layout dropdowns above but on the same form
    and saved via the same Save button (confirmed live 2026-09-09) -
    how many days out a reservation can be made; not yet confirmed live
    what the storefront actually does at/beyond that limit."""

    @log_method_exceptions
    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav

    @log_method_exceptions
    def open_fms_initial_setup(self) -> None:
        with allure.step("Open FMS Initial Setup"):
            self.nav.open_settings_panel()
            fms_initial_setup = self.page.locator(
                ".setting-menu-list-inactive-color, .setting-menu-list-active-color",
                has_text="FMS Initial Setup",
            )
            # The app filter switch has been observed to occasionally not
            # stick on repeat calls within the same test (still showing
            # only the "hummingbird" app's menu afterward, confirmed live
            # - e.g. a test that already used company_blog_page, then
            # separately opens FMS Initial Setup) - retry rather than
            # trusting one call to have switched it. Matches the same
            # pattern already used by MPCompanyBlogPage.open_company_blogs.
            for _ in range(3):
                self.nav.switch_app_filter_to_website()
                try:
                    expect(fms_initial_setup).to_be_visible(timeout=15000)
                    break
                except AssertionError:
                    continue
            else:
                expect(fms_initial_setup).to_be_visible(timeout=self.timeout)
            fms_initial_setup.click()

    @log_method_exceptions
    def list_properties(self) -> list[str]:
        """Returns the numeric property ID of every property offered by
        FMS Initial Setup's own "Select Property" picker (each option
        reads like "340079519 - Irvine - 5281 California Ave Suite
        320") - used to discover a property dynamically instead of
        hardcoding one.

        The ID, not the display name, is what's used throughout this
        module - confirmed live that a property's HB display name and
        its public MP storefront name can genuinely differ, while the
        numeric ID is the one thing that reliably appears in both."""
        with allure.step("List properties available in FMS Initial Setup"):
            self.open_fms_initial_setup()
            trigger = self.page.get_by_role("textbox", name="Select Property")
            trigger.click()
            listbox = trigger.locator("xpath=following::*[@role='listbox'][1]")
            expect(listbox).to_be_visible(timeout=self.timeout)
            options = listbox.get_by_role("option").all_text_contents()
            self.page.keyboard.press("Escape")
            ids = []
            for option in options:
                match = re.match(r"\s*(\d+)", option)
                if match:
                    ids.append(match.group(1))
            return ids

    @log_method_exceptions
    def find_property_with_layout(self, layout: str) -> str | None:
        """Returns the property ID of the first property (in
        list_properties() order) whose Landing Page Layout is already
        `layout`, or None if none matches - lets callers use whatever
        property an environment already has configured a given way,
        instead of assuming a specific hardcoded property/state/city
        exists."""
        with allure.step(f"Find a property with Landing Page Layout = {layout}"):
            for property_id in self.list_properties():
                if self.get_landing_page_layout(property_id) == layout:
                    return property_id
            return None

    _LAYOUT_TRIGGER_NAME = re.compile(r"^(Default|Grid View|List View)$")

    def _layout_trigger(self, index: int):
        """The Landing Page Layout and Value Tier Layout dropdown triggers
        are Vuetify `<div role="button">` elements (not native <button>
        tags - confirmed live 2026-09-08 via document.querySelectorAll,
        which found zero real <button> matches for these), so an
        XPath search relative to the label text is fragile: the ARIA
        accessibility tree renders the label and trigger as direct
        siblings, but the real DOM has extra wrapper elements between
        them that broke every "following"/"following-sibling" XPath
        tried here. Confirmed live there are exactly two elements on
        this whole form whose own accessible name is one of the three
        known layout values, always in this fixed document order:
        Landing Page Layout's trigger first, Value Tier Layout's
        trigger second - so select by ordinal position among that
        narrow, well-defined candidate set instead."""
        return self.page.get_by_role(
            "button", name=self._LAYOUT_TRIGGER_NAME
        ).nth(index)

    @log_method_exceptions
    def open_landing_page_layout_settings(self, property_id: str) -> None:
        with allure.step(f"Open Landing Page Layout settings for property: {property_id}"):
            self.open_fms_initial_setup()
            self.nav.select_property(property_id)
            layout_label = self.page.get_by_text("Landing Page Layout", exact=True)
            expect(layout_label).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def get_landing_page_layout(self, property_id: str) -> str:
        with allure.step(f"Read Landing Page Layout for property: {property_id}"):
            self.open_landing_page_layout_settings(property_id)
            trigger = self._layout_trigger(0)
            return (trigger.text_content() or "").strip()

    @log_method_exceptions
    def set_landing_page_layout(self, property_id: str, layout: str) -> None:
        """Sets the Landing Page Layout (Default / Grid View / List View)
        for a property. No-ops if already set to `layout`."""
        with allure.step(f"Set Landing Page Layout to {layout} for property: {property_id}"):
            self.open_landing_page_layout_settings(property_id)
            trigger = self._layout_trigger(0)
            # A bare `return` here previously skipped clear_cache()
            # below entirely (it sat outside this `with` block) whenever
            # already set to `layout` - see set_two_step for why that
            # leaves the storefront on a stale cache. Only the actual
            # dropdown change is conditional now; the cache always gets
            # cleared.
            if (trigger.text_content() or "").strip() != layout:
                # Confirmed live (2026-09-08): a JS-synthetic click here
                # never opens the dropdown at all (the "option" role
                # below then times out with 0 matches) - this Vuetify
                # autocomplete needs a real, actionability-checked
                # pointer click.
                trigger.click()
                option = self.page.get_by_role("option", name=layout, exact=True)
                expect(option).to_be_visible(timeout=self.timeout)
                option.click()
                self.page.keyboard.press("Escape")
                self.page.get_by_role("button", name="Save", exact=True).click()
                expect(trigger).to_have_text(layout, timeout=self.timeout)
        self.nav.clear_cache()

    @log_method_exceptions
    def open_value_tier_layout_settings(self, property_id: str) -> None:
        with allure.step(f"Open Value Tier Layout settings for property: {property_id}"):
            self.open_fms_initial_setup()
            self.nav.select_property(property_id)
            layout_label = self.page.get_by_text("Value Tier Layout", exact=True)
            expect(layout_label).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def get_value_tier_layout(self, property_id: str) -> str:
        with allure.step(f"Read Value Tier Layout for property: {property_id}"):
            self.open_value_tier_layout_settings(property_id)
            trigger = self._layout_trigger(1)
            return (trigger.text_content() or "").strip()

    @log_method_exceptions
    def set_value_tier_layout(self, property_id: str, layout: str) -> None:
        """Sets the Value Tier Layout (Grid View / List View - no
        "Default", unlike Landing Page Layout) for a property. No-ops if
        already set to `layout`."""
        with allure.step(f"Set Value Tier Layout to {layout} for property: {property_id}"):
            self.open_value_tier_layout_settings(property_id)
            trigger = self._layout_trigger(1)
            # See set_landing_page_layout for why this is now a
            # conditional action rather than an early `return` -
            # clear_cache() below must always run.
            if (trigger.text_content() or "").strip() != layout:
                # See set_landing_page_layout: a JS-synthetic click never
                # opens this Vuetify autocomplete's dropdown - a real,
                # actionability-checked pointer click is required.
                trigger.click()
                option = self.page.get_by_role("option", name=layout, exact=True)
                expect(option).to_be_visible(timeout=self.timeout)
                option.click()
                self.page.keyboard.press("Escape")
                self.page.get_by_role("button", name="Save", exact=True).click()
                expect(trigger).to_have_text(layout, timeout=self.timeout)
        self.nav.clear_cache()

    @log_method_exceptions
    def open_advance_reservation_days_settings(self, property_id: str) -> None:
        with allure.step(
            f"Open Advance Reservation Days settings for property: {property_id}"
        ):
            self.open_fms_initial_setup()
            self.nav.select_property(property_id)
            expect(self._advance_reservation_days_input).to_be_visible(
                timeout=self.timeout
            )

    @property
    def _advance_reservation_days_input(self):
        # Confirmed live (2026-09-09, stage): a plain `<input type=
        # "number">` (Vuetify v-text-field, not the autocomplete/dropdown
        # Landing Page Layout and Value Tier Layout use) with its own
        # unique accessible name, taken from its placeholder - unlike
        # those two, no ordinal-position workaround is needed here.
        return self.page.get_by_role(
            "spinbutton", name="Enter Advance Reservation Days"
        )

    @log_method_exceptions
    def get_advance_reservation_days(self, property_id: str) -> int | None:
        """None if the field is currently blank (confirmed live: not
        every property has a value set)."""
        with allure.step(f"Read Advance Reservation Days for property: {property_id}"):
            self.open_advance_reservation_days_settings(property_id)
            value = self._advance_reservation_days_input.input_value().strip()
            return int(value) if value else None

    @log_method_exceptions
    def set_advance_reservation_days(self, property_id: str, days: int) -> None:
        """Sets Advance Reservation Days for a property. No-ops the
        field write if already set to `days` - see set_landing_page_
        layout for why clear_cache() below still always runs
        regardless."""
        with allure.step(
            f"Set Advance Reservation Days to {days} for property: {property_id}"
        ):
            self.open_advance_reservation_days_settings(property_id)
            field = self._advance_reservation_days_input
            current = field.input_value().strip()
            if current != str(days):
                field.fill(str(days))
                self.page.get_by_role("button", name="Save", exact=True).click()
                expect(field).to_have_value(str(days), timeout=self.timeout)
        self.nav.clear_cache()

    @log_method_exceptions
    def open_two_step_settings(self, property_name: str) -> None:
        with allure.step("Open Two-Step Rental settings"):
            fms_initial_setup = self.page.locator(
                ".setting-menu-list-inactive-color, .setting-menu-list-active-color",
                has_text="FMS Initial Setup",
            )
            if not fms_initial_setup.is_visible():
                self.nav.switch_app_filter_to_website()
            expect(fms_initial_setup).to_be_visible(timeout=self.timeout)
            fms_initial_setup.click()
            self.nav.select_property(property_name)
            two_step_label = self.page.get_by_text(
                "Enable 2-Step Rental", exact=True
            )
            expect(two_step_label).to_be_visible(timeout=self.timeout)
            two_step_switch = two_step_label.locator(
                "xpath=following::input[@role='switch'][1]"
            )
            # Confirmed live (2026-09-09, stage) via direct DOM
            # inspection: "Enable 2-Step Rental" is the switch's own
            # adjacent label (cursor: pointer, sitting right next to the
            # switch in the DOM) - clicking it, which this code used to
            # do here (via a locator misleadingly named
            # two_step_section) whenever the switch wasn't immediately
            # visible, is very likely the same toggle click as clicking
            # the switch itself. That meant what's supposed to be a
            # harmless "wait for this panel to finish rendering" step
            # could silently fire a real enable/disable attempt
            # (Confirm dialog, eligibility check, the "unable to turn
            # on Superlease" warning) as a side effect of just opening/
            # checking this panel. There's also no accordion here to
            # expand in the first place (confirmed live: no
            # v-expansion-panel or similar in this section's DOM
            # ancestry) - the switch simply not being visible yet is a
            # render-timing gap after selecting the property, not a
            # collapsed section, so the fix is to wait, not click
            # anything.
            expect(two_step_switch).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def set_two_step(self, property_name: str, enable: bool) -> None:
        """`property_name` is FMS Initial Setup's own picker text for the
        property (confirmed live: this can differ from the Lease
        Configuration & State Compliance picker's text for the exact same
        physical property, e.g. "GARDEN GROVE" here vs "Hamilton Self
        Storage" there) - always pass FMS's own name, not whatever the
        Lease Configuration picker was last set to."""
        action = "Enable" if enable else "Disable"
        with allure.step(f"{action} Two-Step Rental"):
            # Confirmed live (2026-09-08, stage): this toggle can
            # silently reject a click - no error, switch stays on its
            # old value - when FMS Initial Setup's own "can this be
            # toggled" check is cached from a Clickwrap/Super Lease
            # state that's since changed (see LeaseConfigurationSetup.
            # enable_two_step_clickwrap_and_super_lease's own caching
            # comments). Retries the whole toggle against the real
            # signal - the switch actually flipping - rather than
            # assuming one attempt works: clear_cache() plus a fresh
            # re-open of this panel (open_two_step_settings again, not
            # just re-clicking the still-open one) is what actually
            # picks up current state.
            max_attempts = 3
            for attempt in range(max_attempts):
                self.open_two_step_settings(property_name)
                two_step_label = self.page.get_by_text(
                    "Enable 2-Step Rental", exact=True
                )
                two_step_switch = two_step_label.locator(
                    "xpath=following::input[@role='switch'][1]"
                )
                if two_step_switch.is_checked() == enable:
                    break
                two_step_switch.click(force=True)
                try:
                    if enable:
                        confirmation = self.page.get_by_text(
                            re.compile(r"You are about to enable 2-Step Rental")
                        )
                        expect(confirmation).to_be_visible(timeout=self.timeout)
                        confirm_button = self.page.get_by_role(
                            "button", name="Confirm", exact=True
                        )
                        confirm_button.click()
                        expect(confirm_button).to_be_hidden(timeout=self.timeout)
                        # Confirmed live (2026-09-09, stage): the
                        # confirmation dialog above always appears first,
                        # unconditionally, regardless of Super Lease/
                        # Clickwrap state - only *after* clicking Confirm
                        # does FMS run its real eligibility check
                        # (confirmed via the app's own bundled JS,
                        # captured in an Allure attachment from an
                        # earlier run, and by direct live reproduction).
                        # When that check fails - a stale client-side
                        # `superleaseEnabled` flag on the FMS Initial
                        # Setup component, set once at mount and never
                        # re-fetched after Lease Configuration changes it
                        # elsewhere in the same session - a *second*,
                        # separate "Warning" dialog appears instead ("We
                        # are unable to turn on Superlease...", with its
                        # own "Close" button) and the switch is reset
                        # back to unchecked, rather than the switch
                        # simply becoming checked. This appears near-
                        # instantly (a synchronous Vue $nextTick, not a
                        # network call), so a short wait here is enough
                        # to catch it before falling through to the
                        # normal (longer) checked-state wait below.
                        # clear_cache() (server/CDN cache) never touched
                        # this in-memory value; only a hard reload of
                        # this page forces the component to remount and
                        # re-read the real, current state (see the
                        # except branch below).
                        stale_state_warning = self.page.get_by_text(
                            re.compile(r"unable to turn on Superlease", re.IGNORECASE)
                        )
                        try:
                            expect(stale_state_warning).to_be_visible(timeout=3000)
                        except AssertionError:
                            pass
                        else:
                            close_button = self.page.get_by_role(
                                "button", name="Close", exact=True
                            )
                            if close_button.is_visible():
                                close_button.click()
                            raise AssertionError(
                                "2-Step enable rejected: FMS Initial "
                                "Setup showed the \"unable to turn on "
                                "Superlease\" stale-state warning after "
                                "confirming"
                            )
                        expect(two_step_switch).to_be_checked(timeout=self.timeout)
                    else:
                        # Per explicit instruction: this toggle takes
                        # effect on click, for enable (Confirm) and
                        # disable alike - no separate Save button
                        # needed either way.
                        expect(two_step_switch).not_to_be_checked(timeout=self.timeout)
                    break
                except AssertionError:
                    if attempt == max_attempts - 1:
                        raise
                    # Confirmed live (2026-09-08, stage): a failure
                    # here (e.g. the confirmation dialog never showing
                    # matching text) can still leave its Vuetify modal
                    # overlay (".v-overlay--active") up, which then
                    # blocks clear_cache()'s own first click for the
                    # rest of its timeout - clearing any stray overlay
                    # first (a no-op if none is up) so the retry itself
                    # doesn't get stuck behind whatever this attempt
                    # left open.
                    self.page.keyboard.press("Escape")
                    expect(
                        self.page.locator(".v-overlay--active")
                    ).to_be_hidden(timeout=self.timeout)
                    # Confirmed live (2026-09-09, stage): even a
                    # genuinely fresh login/session (a brand-new
                    # browser context sharing none of this page's
                    # state) hit this exact same rejection immediately
                    # after Super Lease/Clickwrap were enabled - ruling
                    # out every client-side caching theory tried here (a
                    # stale Vue component flag, a closed Settings
                    # panel, cached localStorage/sessionStorage all
                    # confirmed live not to be it). What's left is a
                    # backend propagation delay: whatever FMS Initial
                    # Setup's eligibility check actually reads lags
                    # behind the write Super Lease/Clickwrap just made
                    # elsewhere. A real wait - not just a reload - is
                    # what actually gives that time to catch up;
                    # reload() and clear_cache() are kept too since
                    # they're cheap and don't hurt, even though neither
                    # alone was the fix.
                    #
                    # Extended to disable too (2026-09-09): observed live
                    # that disabling Two-Step right after disabling
                    # Super Lease/Clickwrap hit the same silent click
                    # rejection (switch stayed checked, no error) that
                    # this recovery previously only ran for enable - the
                    # same eligibility check plausibly gates disabling
                    # too, so the same reload+wait is applied here
                    # rather than the plain clear_cache() this branch
                    # used to fall back to on disable.
                    self.page.reload(wait_until="load")
                    self.nav.clear_cache()
                    self.page.wait_for_timeout(20000)
        # A bare `return` above previously skipped this entirely
        # whenever the switch already matched - confirmed live
        # (2026-09-08, stage) this leaves the storefront serving a
        # stale cache from whatever it last saw, even though the
        # admin-side value looks correct. Always cleared, not folded
        # into the retry loop above, which only clears on an actual
        # verification failure.
        self.nav.clear_cache()

    @log_method_exceptions
    def verify_two_step_on_storefront(
        self,
        property_name: str,
        enable: bool,
        rental_page: MPUnitSearchPage,
        *,
        state: str | None = None,
        city: str | None = None,
        property_url: str | None = None,
    ) -> None:
        """Confirms the MP storefront's own Facility Reservation flow -
        not just this page's admin switch - actually reflects `enable`.

        Per explicit instruction: set_two_step's own verification (the
        admin switch state, plus clear_cache) has been seen live to
        report a successful disable while the storefront kept serving
        the Two-Step ("Reserve Now") flow instead of Legacy ("Reserve
        This Space") - only driving the real storefront and reading
        which flow actually renders (MPUnitSearchPage.
        wait_for_reservation_flow) catches that.

        `rental_page` is a caller-built MPUnitSearchPage, driven on
        whatever page/context the caller wants (kept separate from
        this page's own `self.page`, which stays on HB admin
        throughout) - the same page-object split MPTwoStepReservationSetup/
        MPLegacyReservationSetup already use. Pass `property_url` (see
        MPUnitSearchPage.open_property_page) to go straight to a known
        property, or `state`/`city` to search for one; with neither,
        falls back to MPUnitSearchPage.select_first_available_location.

        On a mismatch, re-runs set_two_step (which already retries via
        clear_cache) before trying the storefront again, rather than
        assuming the admin side is still correct."""
        expected_flow = "two_step" if enable else "legacy"
        action = "enabled" if enable else "disabled"
        with allure.step(f"Verify 2-Step Rental is {action} on the storefront"):
            max_attempts = 3
            for attempt in range(max_attempts):
                if property_url:
                    rental_page.open_property_page(property_url)
                else:
                    rental_page.open_storefront()
                    if state and city:
                        rental_page.search_storage_location(state=state, city=city)
                    else:
                        rental_page.select_first_available_location()
                rental_page.select_unit()
                flow = rental_page.wait_for_reservation_flow()
                if flow == expected_flow:
                    return
                if attempt == max_attempts - 1:
                    served = (
                        'Two-Step ("Reserve Now")'
                        if flow == "two_step"
                        else 'Legacy ("Reserve This Space")'
                    )
                    raise AssertionError(
                        f"Storefront kept serving the {served} flow for "
                        f"property {property_name!r} after {max_attempts} "
                        f"attempts, even though FMS Initial Setup shows "
                        f"2-Step Rental {action}."
                    )
                self.set_two_step(property_name, enable)

    @log_method_exceptions
    def is_two_step_enabled(self, property_name: str) -> bool:
        with allure.step("Read 2-Step Rental state"):
            self.open_two_step_settings(property_name)
            two_step_label = self.page.get_by_text("Enable 2-Step Rental", exact=True)
            two_step_switch = two_step_label.locator(
                "xpath=following::input[@role='switch'][1]"
            )
            return two_step_switch.is_checked()

    @log_method_exceptions
    def assert_two_step_enabled(self, property_name: str) -> None:
        with allure.step("Assert Two-Step is enabled"):
            self.open_two_step_settings(property_name)
            two_step_label = self.page.get_by_text("Enable 2-Step Rental", exact=True)
            two_step_switch = two_step_label.locator(
                "xpath=following::input[@role='switch'][1]"
            )
            expect(two_step_switch).to_be_checked()

    @log_method_exceptions
    def assert_two_step_disabled(self, property_name: str) -> None:
        with allure.step("Assert Two-Step is disabled"):
            self.open_two_step_settings(property_name)
            two_step_label = self.page.get_by_text("Enable 2-Step Rental", exact=True)
            two_step_switch = two_step_label.locator(
                "xpath=following::input[@role='switch'][1]"
            )
            expect(two_step_switch).not_to_be_checked()
