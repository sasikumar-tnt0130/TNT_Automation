import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation


class HBLeaseConfigurationPage:
    """Lease Configuration & State Compliance (Super Lease, Clickwrap Signature), under HB's Hummingbird app."""

    @log_method_exceptions
    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        self.property_name: str | None = None

    @log_method_exceptions
    def open_lease_configuration(self) -> None:
        with allure.step("Open Lease Configuration and State Compliance"):
            self.nav.open_settings_panel()
            lease_configuration = self.page.locator(
                ".setting-menu-list-inactive-color, .setting-menu-list-active-color",
                has_text="Lease Configuration & State Compliance",
            )
            expect(lease_configuration).to_be_visible(timeout=self.timeout)
            lease_configuration.click()
            self.page.get_by_role("tab", name="Property Settings").click()

    @log_method_exceptions
    def open_state_compliance_tools(self, property_name: str) -> None:
        with allure.step("Open State Compliance Tools"):
            self.property_name = property_name
            subnav = self.page.locator(".template-sidebar-wrapper")
            state_compliance_tools = subnav.get_by_text(
                "State Compliance Tools", exact=True
            )
            expect(state_compliance_tools).to_be_visible(timeout=self.timeout)
            state_compliance_tools.click()
        self.nav.select_property(property_name)

    @log_method_exceptions
    def open_super_lease(self) -> None:
        with allure.step("Open Super Lease"):
            self.open_lease_configuration()
            # Confirmed live 2026-09-08: NOT self.nav.property_name - that
            # field is shared with MPFMSInitialSetupPage (both page objects
            # take the same HBSettingsNavigation instance, see
            # LeaseConfigurationSetup.build_two_step_rental_page), and FMS's
            # own property picker uses different display text for the same
            # physical property (e.g. "GARDEN GROVE" vs "Hamilton Self
            # Storage" here). A set_two_step() call in between two Lease
            # Configuration steps overwrites nav.property_name with FMS's
            # name, which then fails this picker outright. This page's own
            # cached name (set by open_state_compliance_tools) doesn't get
            # clobbered by an unrelated page object's navigation.
            self.open_state_compliance_tools(self.property_name)
            super_lease_section = self.page.get_by_role(
                "button", name=re.compile(r"Super Lease.*Property")
            )
            expect(super_lease_section).to_be_visible(timeout=self.timeout)
            if super_lease_section.get_attribute("aria-expanded") != "true":
                super_lease_section.click()

    @log_method_exceptions
    def set_super_lease(self, enable: bool) -> None:
        action = "Enable" if enable else "Disable"
        with allure.step(f"{action} Super Lease"):
            self.open_super_lease()
            super_lease_checkbox = self.page.get_by_role("button", name=re.compile(r"^Super Lease")).get_by_role("switch")
            if super_lease_checkbox.is_checked() != enable:
                super_lease_checkbox.click(force=True)
                if enable:
                    activate_button = self.page.get_by_role(
                        "button", name="Activate", exact=True
                    )
                    expect(activate_button).to_be_visible(timeout=self.timeout)
                    activate_button.click()
                    expect(activate_button).to_be_hidden(timeout=self.timeout)
                else:
                    disable_button = self.page.get_by_role(
                        "button", name="Disable", exact=True
                    )
                    expect(disable_button).to_be_visible(timeout=self.timeout)
                    disable_button.click()
                    expect(disable_button).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def is_super_lease_enabled(self) -> bool:
        with allure.step("Read Super Lease state"):
            self.open_super_lease()
            super_lease_checkbox = self.page.get_by_role(
                "button", name=re.compile(r"^Super Lease")
            ).get_by_role("switch")
            return super_lease_checkbox.is_checked()

    @log_method_exceptions
    def open_clickwrap_signature(self) -> None:
        with allure.step("Open Clickwrap Signature"):
            clickwrap_signature = self.page.get_by_role(
                "button", name=re.compile(r"^Clickwrap Signature")
            )
            expect(clickwrap_signature).to_be_visible(timeout=self.timeout)
            if clickwrap_signature.get_attribute("aria-expanded") != "true":
                clickwrap_signature.click()

    @log_method_exceptions
    def set_clickwrap_signature(self, enable: bool) -> None:
        action = "Enable" if enable else "Disable"
        with allure.step(f"{action} Clickwrap Signature"):
            self.open_super_lease()
            self.open_clickwrap_signature()
            clickwrap_checkbox = self.page.get_by_role("button", name=re.compile(r"^Clickwrap Signature")).get_by_role("switch")
            already_set = clickwrap_checkbox.is_checked() == enable
            if not already_set and not enable and clickwrap_checkbox.is_disabled():
                # Clickwrap is locked on while Super Lease is enabled.
                self.set_super_lease(False)
                self.open_super_lease()
                self.open_clickwrap_signature()
                clickwrap_checkbox = self.page.get_by_role("button", name=re.compile(r"^Clickwrap Signature")).get_by_role("switch")
                already_set = clickwrap_checkbox.is_checked() == enable
            if not already_set:
                clickwrap_checkbox.click(force=True)
                if enable:
                    activate_button = self.page.get_by_role(
                        "button", name="Activate", exact=True
                    )
                    expect(activate_button).to_be_visible(timeout=self.timeout)
                    activate_button.click()
                    expect(activate_button).to_be_hidden(timeout=self.timeout)
                else:
                    disable_button = self.page.get_by_role(
                        "button", name="Disable", exact=True
                    )
                    expect(disable_button).to_be_visible(timeout=self.timeout)
                    disable_button.click()
                    expect(disable_button).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def is_clickwrap_signature_enabled(self) -> bool:
        with allure.step("Read Clickwrap Signature state"):
            self.open_super_lease()
            self.open_clickwrap_signature()
            clickwrap_checkbox = self.page.get_by_role(
                "button", name=re.compile(r"^Clickwrap Signature")
            ).get_by_role("switch")
            return clickwrap_checkbox.is_checked()

    @log_method_exceptions
    def assert_super_lease_enabled(self) -> None:
        with allure.step("Assert Super Lease is enabled"):
            self.open_super_lease()
            super_lease_checkbox = self.page.get_by_role("button", name=re.compile(r"^Super Lease")).get_by_role("switch")
            expect(super_lease_checkbox).to_be_checked()

    @log_method_exceptions
    def assert_super_lease_disabled(self) -> None:
        with allure.step("Assert Super Lease is disabled"):
            self.open_super_lease()
            super_lease_checkbox = self.page.get_by_role("button", name=re.compile(r"^Super Lease")).get_by_role("switch")
            expect(super_lease_checkbox).not_to_be_checked()

    @log_method_exceptions
    def assert_clickwrap_signature_enabled(self) -> None:
        with allure.step("Assert Clickwrap Signature is enabled"):
            self.open_super_lease()
            self.open_clickwrap_signature()
            clickwrap_checkbox = self.page.get_by_role("button", name=re.compile(r"^Clickwrap Signature")).get_by_role("switch")
            expect(clickwrap_checkbox).to_be_checked()

    @log_method_exceptions
    def assert_clickwrap_signature_disabled(self) -> None:
        with allure.step("Assert Clickwrap Signature is disabled"):
            self.open_super_lease()
            self.open_clickwrap_signature()
            clickwrap_checkbox = self.page.get_by_role("button", name=re.compile(r"^Clickwrap Signature")).get_by_role("switch")
            expect(clickwrap_checkbox).not_to_be_checked()

    @log_method_exceptions
    def assert_clickwrap_signature_locked(self) -> None:
        with allure.step(
            "Assert Clickwrap Signature toggle is locked (Super Lease requires it)"
        ):
            self.open_super_lease()
            self.open_clickwrap_signature()
            clickwrap_checkbox = self.page.get_by_role("button", name=re.compile(r"^Clickwrap Signature")).get_by_role("switch")
            expect(clickwrap_checkbox).to_be_disabled()
