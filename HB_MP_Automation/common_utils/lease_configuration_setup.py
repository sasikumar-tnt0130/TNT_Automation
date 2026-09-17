from configparser import ConfigParser

from common_utils.wrapper_methods import log_method_exceptions
from config.config_reader import EnvironmentConfig
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_lease_configuration_page import HBLeaseConfigurationPage
from pages.mariposa.mp_fms_initial_setup_page import MPFMSInitialSetupPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


class LeaseConfigurationSetup:
    """Reusable Lease Configuration test scenarios, built on top of the
    Lease Configuration and Two-Step Rental page objects. Property
    identity comes from config/environments.ini (one property per
    environment) rather than a separate test-data JSON."""

    @log_method_exceptions
    def __init__(
        self,
        hb_login_page: HBLoginPage,
        environment_config: EnvironmentConfig,
        app_config: ConfigParser,
        property_name: str | None = None,
        fms_property_name: str | None = None,
    ) -> None:
        # property_name/fms_property_name let a caller target a different
        # property than environments.ini's single per-environment default
        # (e.g. disabling Two-Step/Clickwrap/Super Lease on whichever
        # property a specific pilot test happens to be using, without
        # that property becoming every other lease-configuration test's
        # default too) - both fall back to environments.ini when omitted,
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
        if not self.property_name or not self.fms_property_name:
            raise ValueError(
                f"No property configured for environment "
                f"{environment_config.name!r} - set "
                "lease_configuration_property_name and fms_property_name "
                "in config/environments.ini, or pass property_name/"
                "fms_property_name explicitly."
            )
        self.lease_configuration = self.build_lease_configuration_page()
        self.two_step_rental_page = self.build_two_step_rental_page()

    @log_method_exceptions
    def build_lease_configuration_page(self) -> HBLeaseConfigurationPage:
        """Log in (if this browser context isn't already authenticated -
        e.g. a second LeaseConfigurationSetup built later in the same
        test, such as an autouse teardown fixture restoring a setting)
        and build a Lease Configuration & State Compliance page object."""
        if self.hb_login_page.open_login_page():
            self.hb_login_page.submit_login_credentials()
        self.hb_login_page.assert_login_successful()

        timeout = self.app_config.getint("browser", "timeout")
        nav = HBSettingsNavigation(self.hb_login_page.page, timeout)
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
    def open_state_compliance_tools(self) -> None:
        """Navigate to Lease Configuration > State Compliance Tools for the property."""
        self.lease_configuration.open_lease_configuration()
        self.lease_configuration.open_state_compliance_tools(self.property_name)

    @log_method_exceptions
    def disable_clickwrap_and_super_lease(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # Per explicit instruction: check the current configuration
        # first, and bypass straight to the (cheap) verification below
        # when Clickwrap/Super Lease are already both disabled, instead
        # of always re-running the full disable sequence regardless of
        # current state. open_state_compliance_tools() must run before
        # the check itself - the is_*_enabled() reads go through
        # open_super_lease(), which relies on self.lease_configuration.
        # property_name already being seeded by a prior
        # open_state_compliance_tools(property_name) call.
        self.open_state_compliance_tools()
        already_configured = (
            not self.lease_configuration.is_clickwrap_signature_enabled()
            and not self.lease_configuration.is_super_lease_enabled()
        )
        if not already_configured:
            self.lease_configuration.set_clickwrap_signature(False)
            self.open_state_compliance_tools()
            self.lease_configuration.set_super_lease(False)
            self.open_state_compliance_tools()
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)

        self.lease_configuration.assert_clickwrap_signature_disabled()
        self.lease_configuration.assert_super_lease_disabled()
        # See disable_two_step_clickwrap_and_super_lease's comment - the
        # admin switch reading "disabled" isn't enough on its own, so
        # this only runs when the caller supplies its own MP storefront
        # page (e.g. the mp_rental_page fixture). This method leaves
        # Two-Step disabled too (set_two_step(..., False) above), so the
        # end state to verify on the storefront is Legacy.
        # if rental_page is not None:
        #     self.two_step_rental_page.verify_two_step_on_storefront(
        #         self.fms_property_name,
        #         False,
        #         rental_page,
        #         state=self.environment_config.mp_state,
        #         city=self.environment_config.mp_city,
        #     )

    @log_method_exceptions
    def disable_two_step_clickwrap_and_super_lease(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # Confirmed live (2026-09-08, stage): FMS Initial Setup's own
        # "Enable 2-Step Rental" toggle silently rejects a click - no
        # error, switch stays checked - if that panel was opened while
        # Clickwrap/Super Lease were still enabled, even after they're
        # disabled elsewhere afterward; its own "can this be disabled"
        # check is cached from whenever the panel first loaded, not
        # re-read live. Clickwrap/Super Lease disabled first (each
        # clears the website cache on its own), then a *fresh*
        # navigation into FMS Initial Setup for Two-Step, is what
        # actually sees the updated state - the reverse order (this
        # method's original order) looks like it succeeds (no exception)
        # while leaving Two-Step untouched.
        #
        # Per explicit instruction: check the current configuration
        # first and bypass the whole disable sequence when Clickwrap/
        # Super Lease/Two-Step already all match - clear_cache() still
        # runs even then (see set_two_step's own tail comment for why
        # an already-matching admin state alone isn't reason enough to
        # skip it - the storefront can still be serving a stale value).
        # open_state_compliance_tools() must run before the check
        # itself - see disable_clickwrap_and_super_lease's comment for
        # why (is_*_enabled() needs property_name already seeded).
        self.open_state_compliance_tools()
        already_configured = (
            not self.lease_configuration.is_clickwrap_signature_enabled()
            and not self.lease_configuration.is_super_lease_enabled()
            and not self.two_step_rental_page.is_two_step_enabled(self.fms_property_name)
        )
        if already_configured:
            self.two_step_rental_page.nav.clear_cache()
        else:
            self.lease_configuration.set_clickwrap_signature(False)
            self.lease_configuration.set_super_lease(False)
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)

        self.lease_configuration.assert_clickwrap_signature_disabled()
        self.lease_configuration.assert_super_lease_disabled()
        self.two_step_rental_page.assert_two_step_disabled(self.fms_property_name)
        # Per explicit instruction: the admin switch reading "disabled"
        # isn't enough on its own - the live storefront ("Facility
        # Reservation") has been seen still serving Two-Step afterward
        # (see MPFMSInitialSetupPage.verify_two_step_on_storefront).
        # Optional (needs its own MP storefront page, e.g. the
        # mp_rental_page fixture) so callers without one keep the old,
        # admin-only behavior instead of failing on a missing argument.
        # if rental_page is not None:
        #     self.two_step_rental_page.verify_two_step_on_storefront(
        #         self.fms_property_name,
        #         False,
        #         rental_page,
        #         state=self.environment_config.mp_state,
        #         city=self.environment_config.mp_city,
        #     )

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
        self.open_state_compliance_tools()
        already_configured = (
            self.lease_configuration.is_clickwrap_signature_enabled()
            and not self.lease_configuration.is_super_lease_enabled()
        )
        if not already_configured:
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)
            self.lease_configuration.set_clickwrap_signature(True)
            self.lease_configuration.set_super_lease(False)

        self.lease_configuration.assert_clickwrap_signature_enabled()
        self.lease_configuration.assert_super_lease_disabled()
        # See disable_two_step_clickwrap_and_super_lease's comment - the
        # admin switch reading "disabled" isn't enough on its own, so
        # this only runs when the caller supplies its own MP storefront
        # page. This method leaves Two-Step disabled (set_two_step(...,
        # False) above), so the end state to verify is Legacy.
        # if rental_page is not None:
        #     self.two_step_rental_page.verify_two_step_on_storefront(
        #         self.fms_property_name,
        #         False,
        #         rental_page,
        #         state=self.environment_config.mp_state,
        #         city=self.environment_config.mp_city,
        #     )

    @log_method_exceptions
    def enable_super_lease_and_clickwrap(
        self, rental_page: MPUnitSearchPage | None = None
    ) -> None:
        # See enable_clickwrap_with_super_lease_disabled for why this
        # checks first and bypasses when already matching, and why
        # open_state_compliance_tools() must run before the check.
        self.open_state_compliance_tools()
        already_configured = (
            self.lease_configuration.is_super_lease_enabled()
            and self.lease_configuration.is_clickwrap_signature_enabled()
        )
        if not already_configured:
            self.lease_configuration.set_super_lease(True)
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)
            self.lease_configuration.set_clickwrap_signature(True)

        self.lease_configuration.assert_super_lease_enabled()
        self.lease_configuration.assert_clickwrap_signature_enabled()
        # See disable_two_step_clickwrap_and_super_lease's comment - only
        # runs when the caller supplies its own MP storefront page. This
        # method leaves Two-Step disabled (set_two_step(..., False)
        # above), so the end state to verify is Legacy.
        # if rental_page is not None:
        #     self.two_step_rental_page.verify_two_step_on_storefront(
        #         self.fms_property_name,
        #         False,
        #         rental_page,
        #         state=self.environment_config.mp_state,
        #         city=self.environment_config.mp_city,
        #     )

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
        self.open_state_compliance_tools()
        already_configured = (
            self.lease_configuration.is_super_lease_enabled()
            and self.lease_configuration.is_clickwrap_signature_enabled()
        )
        if not already_configured:
            self.lease_configuration.set_super_lease(False)
            self.two_step_rental_page.set_two_step(self.fms_property_name, False)
            self.lease_configuration.set_clickwrap_signature(False)
            self.lease_configuration.set_super_lease(True)

        self.lease_configuration.assert_super_lease_enabled()
        self.lease_configuration.assert_clickwrap_signature_enabled()
        self.lease_configuration.assert_clickwrap_signature_locked()
        # See disable_two_step_clickwrap_and_super_lease's comment - only
        # runs when the caller supplies its own MP storefront page. This
        # method leaves Two-Step disabled (set_two_step(..., False)
        # above), so the end state to verify is Legacy.
        # if rental_page is not None:
        #     self.two_step_rental_page.verify_two_step_on_storefront(
        #         self.fms_property_name,
        #         False,
        #         rental_page,
        #         state=self.environment_config.mp_state,
        #         city=self.environment_config.mp_city,
        #     )

    @log_method_exceptions
    def set_landing_page_layout(self, layout: str) -> None:
        """Default / Grid View / List View - controls the storefront's
        unit-listing page rendering (see MPUnitSearchPage.select_unit)."""
        self.two_step_rental_page.set_landing_page_layout(self.fms_property_name, layout)

    @log_method_exceptions
    def set_value_tier_layout(self, layout: str) -> None:
        """Grid View / List View (no "Default") - controls the
        protection-plan tier-selection dialog's rendering (see
        MPUnitSearchPage.select_unit's protection-plan step)."""
        self.two_step_rental_page.set_value_tier_layout(self.fms_property_name, layout)

    @log_method_exceptions
    def set_advance_reservation_days(self, days: int) -> None:
        """How many days out a reservation can be made for this
        property."""
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
        # matches the requested state. clear_cache() still runs even
        # then - see disable_two_step_clickwrap_and_super_lease's
        # mirror-image comment for why an already-matching admin state
        # alone isn't reason enough to skip it. open_state_compliance_
        # tools() must run before the check itself - see
        # disable_clickwrap_and_super_lease's comment for why.
        self.open_state_compliance_tools()
        already_configured = (
            self.lease_configuration.is_super_lease_enabled()
            and self.lease_configuration.is_clickwrap_signature_enabled()
            and self.two_step_rental_page.is_two_step_enabled(self.fms_property_name)
        )
        if already_configured:
            self.two_step_rental_page.nav.clear_cache()
        else:
            self.lease_configuration.set_super_lease(True)
            self.lease_configuration.set_clickwrap_signature(True)
            self.two_step_rental_page.set_two_step(self.fms_property_name, True)

        self.two_step_rental_page.assert_two_step_enabled(self.fms_property_name)
        self.lease_configuration.assert_super_lease_enabled()
        self.lease_configuration.assert_clickwrap_signature_enabled()
        # See disable_two_step_clickwrap_and_super_lease's mirror-image
        # comment - the admin switch reading "enabled" isn't enough on
        # its own, so this only runs when the caller supplies its own
        # MP storefront page (e.g. the mp_rental_page fixture).
        # if rental_page is not None:
        #     self.two_step_rental_page.verify_two_step_on_storefront(
        #         self.fms_property_name,
        #         True,
        #         rental_page,
        #         state=self.environment_config.mp_state,
        #         city=self.environment_config.mp_city,
        #     )
