from configparser import ConfigParser

import allure

from common_utils.waits import waits
from common_utils.wrapper_methods import log_method_exceptions
from config.config_reader import EnvironmentConfig
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_lease_configuration_page import HBLeaseConfigurationPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage
from pages.mariposa.mp_fms_initial_setup_page import MPFMSInitialSetupPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


class LeaseConfigurationSetup:
    """Reusable Lease Configuration test scenarios, built on top of the
    Lease Configuration and Two-Step Rental page objects. Property
    identity comes from config/properties.ini (one property per
    environment) rather than a separate test-data JSON.

    Configure methods do not Clear Cache. Mariposa preconditions must
    call ``flush_website_cache`` once after all configure steps.
    """

    @log_method_exceptions
    def __init__(
        self,
        hb_login_page: HBLoginPage,
        environment_config: EnvironmentConfig,
        app_config: ConfigParser,
        property_name: str | None = None,
        fms_property_name: str | None = None,
        hb_property_name: str | None = None,
    ) -> None:
        # property_name/fms_property_name let a caller target a different
        # property than properties.ini's single per-environment default
        # (e.g. disabling Two-Step/Clickwrap/Super Lease on whichever
        # property a specific pilot test happens to be using, without
        # that property becoming every other lease-configuration test's
        # default too) - both fall back to properties.ini when omitted,
        # so existing callers are unaffected.
        self.hb_login_page = hb_login_page
        self.app_config = app_config
        self.environment_config = environment_config
        self.property_name = property_name or environment_config.lease_configuration_property_name
        # FMS Initial Setup's own property picker can show different text
        # for the exact same physical property than the Lease
        # Configuration & State Compliance picker does (confirmed live,
        # e.g. "GARDEN GROVE" vs "Hamilton Self Storage") - callers
        # overriding property_name must also supply the matching
        # fms_property_name rather than assuming they're the same string.
        self.fms_property_name = fms_property_name or environment_config.fms_property_name
        # Dashboard / company property (Quick Launch #search-box). Stage's
        # Hamilton Self Storage vs Lightning Storage live under different
        # facilities (Hamilton County vs Rutland); Settings' Select Property
        # only lists properties for the dashboard facility currently selected
        # (live 2026-09-19: looking for Hamilton while on Rutland failed).
        legacy = environment_config.legacy_property
        self.hb_property_name = (
            hb_property_name
            or (legacy.hb_property_name if legacy else None)
            or self.property_name
        )
        if not self.property_name or not self.fms_property_name:
            raise ValueError(
                f"No property configured for environment "
                f"{environment_config.name!r} - set "
                "lease_configuration_property_name and fms_property_name "
                "in config/properties/<env>.ini, or pass property_name/"
                "fms_property_name explicitly."
            )
        self.lease_configuration = self.build_lease_configuration_page()
        self.two_step_rental_page = self.build_two_step_rental_page()

    @log_method_exceptions
    def build_lease_configuration_page(self) -> HBLeaseConfigurationPage:
        """Ensure this HB page is logged in (no-op when already authenticated)
        and build a Lease Configuration & State Compliance page object."""
        self.hb_login_page.ensure_logged_in()

        timeout = self.app_config.getint("browser", "timeout")
        nav = HBSettingsNavigation(self.hb_login_page.page, timeout)
        nav._dismiss_blocking_dialog()
        return HBLeaseConfigurationPage(self.hb_login_page.page, timeout, nav)

    @log_method_exceptions
    def build_two_step_rental_page(self) -> MPFMSInitialSetupPage:
        """Build a Two-Step Rental (FMS Initial Setup) page object sharing the
        same Settings navigation as the Lease Configuration page, so property
        selection and app-filter state stay in sync between the two."""
        return MPFMSInitialSetupPage(
            self.lease_configuration.page,
            self.lease_configuration.timeout,
            self.lease_configuration.nav,
        )

    @log_method_exceptions
    def _ensure_dashboard_property(self) -> None:
        """Leave Settings and select the facility Settings will list."""
        if not self.hb_property_name:
            return
        with allure.step(
            f"HB dashboard property for Lease/FMS Settings: {self.hb_property_name}"
        ):
            self.hb_login_page.ensure_on_dashboard()
            timeout = self.app_config.getint("browser", "timeout")
            HBQuickLaunchPage(self.hb_login_page.page, timeout).select_property(
                self.hb_property_name
            )

    @log_method_exceptions
    def open_state_compliance_tools(self) -> None:
        """Navigate to Lease Configuration > State Compliance Tools for the property."""
        self._ensure_dashboard_property()
        self.lease_configuration.open_lease_configuration()
        self.lease_configuration.open_state_compliance_tools(self.property_name)

    @log_method_exceptions
    def flush_website_cache(self) -> None:
        """Website Clear Cache — call once at the end of a Mariposa
        admin precondition after all configure steps.

        Always runs Clear Cache — admin can already read the desired
        switch state while the storefront still serves a prior session's
        cache (2026-09-18).
        """
        with allure.step(
            "Flush website cache (Mariposa precondition final step)"
        ):
            self.two_step_rental_page.nav.clear_cache()
            self.hb_login_page.page.wait_for_timeout(waits().long)

    @log_method_exceptions
    def disable_clickwrap_and_super_lease(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # Same confirm-modal flow as disable_two_step_… (live 2026-09-18).
        # Two-Step off first, then Super Lease (unlocks Clickwrap), then
        # Clickwrap. Skip when already off. Caller flushes via
        # flush_website_cache after configure steps.
        self.open_state_compliance_tools()
        # Include Two-Step in the bypass check: when legacy_property and
        # two_step_property are the same key, a prior Two-Step module can
        # leave Two-Step on while SL/CW still match "already off".
        already_configured = (
            not self.lease_configuration.is_clickwrap_signature_enabled()
            and not self.lease_configuration.is_super_lease_enabled()
            and not self.two_step_rental_page.is_two_step_enabled(
                self.fms_property_name
            )
        )
        if not already_configured:
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)
            self.lease_configuration.set_super_lease(False)
            self.lease_configuration.set_clickwrap_signature(False)

        self.lease_configuration.assert_clickwrap_signature_disabled()
        self.lease_configuration.assert_super_lease_disabled()
        self.two_step_rental_page.assert_two_step_disabled(self.fms_property_name)

    @log_method_exceptions
    def disable_two_step_clickwrap_and_super_lease(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # Live 2026-09-18 (stage): Super Lease / Clickwrap confirm modals
        # need Vue buttonClicked (see HBLeaseConfigurationPage). Order:
        # Two-Step off first, then Super Lease, then Clickwrap.
        # Caller flushes via flush_website_cache after configure steps.
        with allure.step(
            f"Ensure Two-Step, Clickwrap, and Super Lease are off "
            f"({self.fms_property_name})"
        ):
            self.open_state_compliance_tools()
            already_configured = (
                not self.lease_configuration.is_clickwrap_signature_enabled()
                and not self.lease_configuration.is_super_lease_enabled()
                and not self.two_step_rental_page.is_two_step_enabled(
                    self.fms_property_name
                )
            )
            if already_configured:
                with allure.step("Skip Saves (already off)"):
                    pass
            else:
                with allure.step(
                    "Disable Two-Step, then Super Lease / Clickwrap"
                ):
                    self.two_step_rental_page.set_two_step(
                        self.fms_property_name, False
                    )
                    self.lease_configuration.set_super_lease(False)
                    self.lease_configuration.set_clickwrap_signature(False)

            self.lease_configuration.assert_clickwrap_signature_disabled()
            self.lease_configuration.assert_super_lease_disabled()
            self.two_step_rental_page.assert_two_step_disabled(
                self.fms_property_name
            )

    @log_method_exceptions
    def enable_clickwrap_with_super_lease_disabled(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # Per explicit instruction: bypass the whole sequence (including
        # the force-disable-Two-Step precondition step) when Clickwrap/
        # Super Lease already match the requested state.
        # open_state_compliance_tools() must run before the check
        # itself - see disable_clickwrap_and_super_lease's comment for
        # why (is_*_enabled() needs property_name already seeded).
        # Caller flushes via flush_website_cache after configure steps.
        self.open_state_compliance_tools()
        # Two-Step must be off for Legacy; same-property role configs can
        # leave it on after a Two-Step module (see disable_clickwrap…).
        already_configured = (
            self.lease_configuration.is_clickwrap_signature_enabled()
            and not self.lease_configuration.is_super_lease_enabled()
            and not self.two_step_rental_page.is_two_step_enabled(
                self.fms_property_name
            )
        )
        if not already_configured:
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)
            self.lease_configuration.set_clickwrap_signature(True)
            self.lease_configuration.set_super_lease(False)

        self.lease_configuration.assert_clickwrap_signature_enabled()
        self.lease_configuration.assert_super_lease_disabled()
        self.two_step_rental_page.assert_two_step_disabled(self.fms_property_name)

    @log_method_exceptions
    def enable_super_lease_and_clickwrap(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # See enable_clickwrap_with_super_lease_disabled for why this
        # checks first and bypasses when already matching, and why
        # open_state_compliance_tools() must run before the check.
        # Caller flushes via flush_website_cache after configure steps.
        self.open_state_compliance_tools()
        # Critical for same-property legacy+two_step configs: after a
        # Two-Step module, SL+CW are already on so a SL/CW-only bypass
        # would leave Two-Step enabled and the storefront serves
        # "Reserve Now" instead of Legacy.
        super_lease_on = self.lease_configuration.is_super_lease_enabled()
        clickwrap_on = self.lease_configuration.is_clickwrap_signature_enabled()
        # Dismiss Super Lease / Clickwrap confirm cards only — do not
        # Escape the Settings v-dialog itself (closes the panel).
        self.lease_configuration._dismiss_confirm_modal()
        already_configured = (
            super_lease_on
            and clickwrap_on
            and not self.two_step_rental_page.is_two_step_enabled(
                self.fms_property_name
            )
        )
        if not already_configured:
            # Two-Step off first (same order as other Legacy configure
            # methods). Enabling Super Lease before disabling Two-Step
            # left Garden Grove serving "Reserve Now" on stage
            # (2026-09-19, legacy_superlease card desktop).
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)
            self.lease_configuration.set_super_lease(True)
            self.lease_configuration.set_clickwrap_signature(True)
        else:
            # Still force Two-Step off: admin switch reads have been wrong
            # while the storefront kept Two-Step (see verify_two_step_on_storefront).
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)

        self.lease_configuration.assert_super_lease_enabled()
        self.lease_configuration.assert_clickwrap_signature_enabled()
        self.two_step_rental_page.assert_two_step_disabled(self.fms_property_name)

    @log_method_exceptions
    def enable_super_lease_with_clickwrap_disabled(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # See enable_clickwrap_with_super_lease_disabled for why this
        # checks first and bypasses when already matching. Despite the
        # method name, the actual end state is Super Lease enabled with
        # Clickwrap enabled-and-locked (set_clickwrap_signature's own
        # docstring: Clickwrap is forced on while Super Lease is on) -
        # the bypass condition checks that real end state, not a
        # standalone "Clickwrap disabled" that this method never
        # actually leaves in place. open_state_compliance_tools() must
        # run before the check itself - see
        # disable_clickwrap_and_super_lease's comment for why.
        # Caller flushes via flush_website_cache after configure steps.
        self.open_state_compliance_tools()
        already_configured = (
            self.lease_configuration.is_super_lease_enabled()
            and self.lease_configuration.is_clickwrap_signature_enabled()
            and not self.two_step_rental_page.is_two_step_enabled(
                self.fms_property_name
            )
        )
        if not already_configured:
            self.lease_configuration.set_super_lease(False)
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)
            self.lease_configuration.set_clickwrap_signature(False)
            self.lease_configuration.set_super_lease(True)

        self.lease_configuration.assert_super_lease_enabled()
        self.lease_configuration.assert_clickwrap_signature_enabled()
        self.lease_configuration.assert_clickwrap_signature_locked()
        self.two_step_rental_page.assert_two_step_disabled(self.fms_property_name)

    @log_method_exceptions
    def set_landing_page_layout(self, layout: str) -> None:
        """Default / Grid View / List View - controls the storefront's
        unit-listing page rendering (see MPUnitSearchPage.select_unit).

        Does not Clear Cache; call ``flush_website_cache`` after all
        configure steps.
        """
        self.two_step_rental_page.set_landing_page_layout(
            self.fms_property_name, layout
        )

    @log_method_exceptions
    def set_value_tier_layout(self, layout: str) -> None:
        """Grid View / List View (no "Default") - controls the
        protection-plan tier-selection dialog's rendering (see
        MPUnitSearchPage.select_unit's protection-plan step).

        Does not Clear Cache; call ``flush_website_cache`` after all
        configure steps.
        """
        self.two_step_rental_page.set_value_tier_layout(
            self.fms_property_name, layout
        )

    @log_method_exceptions
    def set_landing_and_value_tier_layouts(
        self, landing_layout: str, tier_layout: str
    ) -> None:
        """Configure Landing Page Layout + Value Tier Layout together.

        When Landing is Default, FMS hides the Value Tier Layout control
        (walked 2026-09-16 stage/Garden Grove). Set the tier first while
        Landing is still Grid/List, then switch Landing to Default so the
        stored tier setting still applies to the protection-plan dialog.

        Does not Clear Cache; call ``flush_website_cache`` after configure.
        """
        with allure.step(
            f"Set Landing Page Layout to {landing_layout} and "
            f"Value Tier Layout to {tier_layout} ({self.fms_property_name})"
        ):
            if landing_layout == "Default":
                # Any non-Default landing re-exposes Value Tier Layout.
                self.set_landing_page_layout("Grid View")
                self.set_value_tier_layout(tier_layout)
                self.set_landing_page_layout("Default")
            else:
                self.set_landing_page_layout(landing_layout)
                self.set_value_tier_layout(tier_layout)

    @log_method_exceptions
    def set_advance_reservation_days(self, days: int) -> None:
        """How many days out a reservation can be made for this
        property. Does not Clear Cache; call ``flush_website_cache``
        after configure steps."""
        self.two_step_rental_page.set_advance_reservation_days(
            self.fms_property_name, days
        )

    @log_method_exceptions
    def enable_two_step_clickwrap_and_super_lease(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # Per explicit instruction: check the current configuration
        # first and bypass the force-disable-then-reenable Two-Step
        # dance (plus Super Lease/Clickwrap) when everything already
        # matches the requested state. open_state_compliance_tools()
        # must run before the check itself - see
        # disable_clickwrap_and_super_lease's comment for why.
        # Caller flushes via flush_website_cache after configure steps
        # (storefront). Mid-flow Clear Cache below is only for FMS
        # eligibility before toggling Two-Step.
        with allure.step(
            f"Ensure Two-Step, Clickwrap, and Super Lease are on "
            f"({self.fms_property_name})"
        ):
            self.open_state_compliance_tools()
            already_configured = (
                self.lease_configuration.is_super_lease_enabled()
                and self.lease_configuration.is_clickwrap_signature_enabled()
                and self.two_step_rental_page.is_two_step_enabled(
                    self.fms_property_name
                )
            )
            if already_configured:
                with allure.step("Skip Saves (already on)"):
                    pass
            else:
                with allure.step(
                    "Enable Super Lease, Clickwrap, then Two-Step"
                ):
                    self.lease_configuration.set_super_lease(True)
                    self.lease_configuration.set_clickwrap_signature(True)
                    # Live 2026-09-17 (uat_storoutlet / Chula Vista): FMS
                    # still shows the Superlease/Clickwrap requirements copy
                    # and will not stay ON until Website Clear Cache runs and
                    # ~5s elapses. Required for FMS eligibility before
                    # toggling Two-Step — not a substitute for the caller's
                    # final flush_website_cache for the storefront.
                    with allure.step(
                        "Flush website cache so FMS sees Superlease/Clickwrap"
                    ):
                        self.two_step_rental_page.nav.clear_cache()
                        # Backend eligibility lag after Clear Cache - live
                        # 2026-09-17: ~5s often enough, but Superlease stale
                        # warning still hit after waits().long; give FMS more
                        # time before the first Two-Step toggle attempt.
                        self.hb_login_page.page.wait_for_timeout(20000)
                    self.two_step_rental_page.set_two_step(
                        self.fms_property_name, True
                    )

            self.two_step_rental_page.assert_two_step_enabled(
                self.fms_property_name
            )
            self.lease_configuration.assert_super_lease_enabled()
            self.lease_configuration.assert_clickwrap_signature_enabled()
