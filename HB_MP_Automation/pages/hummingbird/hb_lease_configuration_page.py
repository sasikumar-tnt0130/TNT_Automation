import re

import allure
from playwright.sync_api import Page, expect

from common_utils.waits import waits
from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation


class HBLeaseConfigurationPage:
    """Lease Configuration & State Compliance (Super Lease, Clickwrap Signature).

    Live 2026-09-18 (stage / Hamilton Self Storage):
    - Toggling Super Lease / Clickwrap opens a confirmation modal
      (``.hb-modal-confirmation-border``) with Activate or Disable.
    - Playwright clicks on those HbBottomActionBar buttons do not run the
      Vue handler; the wrapper's ``buttonClicked`` method does (and POSTs
      ``/settings/lease-settings``).
    - After a successful confirm the modal often stays open — dismiss with
      Escape / close icon. Success is the switch state, not the button hiding.
    """

    _CONFIRM_MODAL = ".hb-modal-confirmation-border"
    _SUPER_LEASE_SWITCH = re.compile(r"^Super Lease")
    _CLICKWRAP_SWITCH = re.compile(r"^Clickwrap Signature")
    _SUPER_LEASE_SECTION = re.compile(r"Super Lease.*Property")

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
            # Prefer this page's cached property_name — nav.property_name is
            # shared with FMS Initial Setup and can be overwritten with a
            # different display string for the same facility.
            self.open_state_compliance_tools(self.property_name)
            super_lease_section = self.page.get_by_role(
                "button", name=self._SUPER_LEASE_SECTION
            )
            expect(super_lease_section).to_be_visible(timeout=self.timeout)
            if super_lease_section.get_attribute("aria-expanded") != "true":
                super_lease_section.click()

    def _super_lease_switch(self):
        return self.page.get_by_role(
            "button", name=self._SUPER_LEASE_SWITCH
        ).get_by_role("switch")

    def _clickwrap_switch(self):
        return self.page.get_by_role(
            "button", name=self._CLICKWRAP_SWITCH
        ).get_by_role("switch")

    def _dismiss_confirm_modal(self) -> None:
        modal = self.page.locator(self._CONFIRM_MODAL)
        if modal.count() == 0:
            return
        # Prefer the visible one (stale clones can remain attached).
        for index in range(modal.count()):
            candidate = modal.nth(index)
            if not candidate.is_visible():
                continue
            self.page.keyboard.press("Escape")
            try:
                expect(candidate).to_be_hidden(timeout=waits().short)
            except AssertionError:
                close = candidate.locator(
                    'button[name="QA-v-card-HbIcon-mdi-close"]'
                )
                if close.count() and close.first.is_visible():
                    close.first.click(force=True)
                    expect(candidate).to_be_hidden(timeout=waits().short)
            break

    def _confirm_modal_action(self, action: str) -> None:
        """Confirm Activate / Disable in the Super Lease / Clickwrap modal.

        ``action`` is the primary label: Activate | Disable.
        """
        # Role-based: the QA name is not always present on the confirm
        # primary (live 2026-09-18 Activate modal), and Cancel may be plain
        # text rather than a button. Scope to the confirm card that owns
        # this action so a leftover modal is not used.
        modal = self.page.locator(self._CONFIRM_MODAL).filter(
            has=self.page.get_by_role("button", name=action, exact=True)
        )
        button = modal.get_by_role("button", name=action, exact=True)
        expect(button).to_be_visible(timeout=self.timeout)
        # Live 2026-09-18: Playwright locator.click on these buttons does not
        # invoke Vue's buttonClicked; call it on the wrapper component.
        button.evaluate(
            """(btn) => {
              let el = btn;
              while (el) {
                const vue = el.__vue__;
                if (vue && typeof vue.buttonClicked === 'function') {
                  vue.buttonClicked();
                  return;
                }
                el = el.parentElement;
              }
              throw new Error('HbBottomActionBar buttonClicked not found');
            }"""
        )
        self.page.wait_for_timeout(waits().short)
        self._dismiss_confirm_modal()

    def _set_switch(
        self, switch, *, enable: bool, action_when_enabling: str = "Activate"
    ) -> None:
        if switch.is_checked() == enable:
            return
        switch.click(force=True)
        self._confirm_modal_action(
            action_when_enabling if enable else "Disable"
        )
        if enable:
            expect(switch).to_be_checked(timeout=self.timeout)
        else:
            expect(switch).not_to_be_checked(timeout=self.timeout)

    @log_method_exceptions
    def set_super_lease(self, enable: bool) -> None:
        action = "Enable" if enable else "Disable"
        with allure.step(f"{action} Super Lease"):
            self.open_super_lease()
            self._set_switch(self._super_lease_switch(), enable=enable)

    @log_method_exceptions
    def is_super_lease_enabled(self) -> bool:
        with allure.step("Read Super Lease state"):
            self.open_super_lease()
            return self._super_lease_switch().is_checked()

    @log_method_exceptions
    def open_clickwrap_signature(self) -> None:
        with allure.step("Open Clickwrap Signature"):
            clickwrap_signature = self.page.get_by_role(
                "button", name=self._CLICKWRAP_SWITCH
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
            clickwrap = self._clickwrap_switch()
            # Clickwrap is locked on while Super Lease is enabled.
            if (
                not enable
                and clickwrap.is_checked()
                and (
                    clickwrap.is_disabled()
                    or clickwrap.get_attribute("aria-disabled") == "true"
                )
            ):
                self.set_super_lease(False)
                self.open_super_lease()
                self.open_clickwrap_signature()
                clickwrap = self._clickwrap_switch()
            self._set_switch(clickwrap, enable=enable)

    @log_method_exceptions
    def is_clickwrap_signature_enabled(self) -> bool:
        with allure.step("Read Clickwrap Signature state"):
            self.open_super_lease()
            self.open_clickwrap_signature()
            return self._clickwrap_switch().is_checked()

    @log_method_exceptions
    def assert_super_lease_enabled(self) -> None:
        with allure.step("Assert Super Lease is enabled"):
            self.open_super_lease()
            expect(self._super_lease_switch()).to_be_checked()

    @log_method_exceptions
    def assert_super_lease_disabled(self) -> None:
        with allure.step("Assert Super Lease is disabled"):
            self.open_super_lease()
            expect(self._super_lease_switch()).not_to_be_checked()

    @log_method_exceptions
    def assert_clickwrap_signature_enabled(self) -> None:
        with allure.step("Assert Clickwrap Signature is enabled"):
            self.open_super_lease()
            self.open_clickwrap_signature()
            expect(self._clickwrap_switch()).to_be_checked()

    @log_method_exceptions
    def assert_clickwrap_signature_disabled(self) -> None:
        with allure.step("Assert Clickwrap Signature is disabled"):
            self.open_super_lease()
            self.open_clickwrap_signature()
            expect(self._clickwrap_switch()).not_to_be_checked()

    @log_method_exceptions
    def assert_clickwrap_signature_locked(self) -> None:
        with allure.step(
            "Assert Clickwrap Signature toggle is locked (Super Lease requires it)"
        ):
            self.open_super_lease()
            self.open_clickwrap_signature()
            expect(self._clickwrap_switch()).to_be_disabled()
