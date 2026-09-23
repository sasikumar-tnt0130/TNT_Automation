import re

import allure
from playwright.sync_api import Locator, Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_communication_compose_page import TEST_INBOX

# (707)/(714) 555-0100..0199 only - the range reserved for fictional use.
FICTIONAL_NUMBER = re.compile(r"^(707|714)55501\d\d$")


class HBAdditionalContactsPage:
    """A tenant's Additional Contacts (tenant page -> Tenant Info).

    Confirmed live 2026-09-14 (uat_storoutlet, Bellflower): Tenant Info has
    an "Additional Contacts" expansion panel. A tenant with no contacts yet
    shows a "Click to Add" link in the panel's header; once there is one,
    each contact is a row with its own Remove link and "+ Add New Contact"
    sits below them. Either opens a "New Contact" draft whose fields are
    numbered by the contacts already there (N): input#associated_space_N
    (the tenant's spaces, multi-select), input#designations_N (Alternate /
    Emergency / Authorized Access / Lien Holder, multi-select),
    relationship_first_N / last_N / email_N, a phone type (its id stayed
    relationship_phone_type_0 on a second contact), relationship_phone_code_N
    (+1 first), relationship_phone_N, relationship_sms_N (unticked; it can be
    ticked once the phone is filled) and address fields. The draft's Save is
    QA-v-expansion-panel-content-hb-primary-button-Save; Cancel is a link. A
    saved contact can't be edited, only removed.
    """

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def _panel(self) -> Locator:
        return self.page.locator(".v-expansion-panel").filter(has_text="Additional Contacts").first

    @log_method_exceptions
    def _field(self, panel: Locator, input_selector: str) -> Locator:
        return panel.locator(".v-input").filter(has=self.page.locator(input_selector)).last

    @log_method_exceptions
    def _menu_item(self, option: str) -> Locator:
        # By its accessible name: a multi-select item's text starts with its
        # checkbox icon's ligature with no space before the label
        # ("check_box_outline_blank0040"), so a text match on the label missed
        # it, while the option itself is named "0040" (2026-09-14).
        return self.page.get_by_role("option", name=option, exact=True).filter(visible=True).first

    @log_method_exceptions
    def _tick(self, field: Locator, options: list[str]) -> None:
        field.locator(".v-select__slot").first.click()
        for option in options:
            item = self._menu_item(option)
            expect(item).to_be_visible(timeout=self.timeout)
            item.click()
        self.page.keyboard.press("Escape")
        for option in options:
            expect(field.locator(".v-select__selections")).to_contain_text(option, timeout=self.timeout)

    @log_method_exceptions
    def _choose(self, field: Locator, option: str) -> None:
        field.locator(".v-select__slot").first.click()
        item = self._menu_item(option)
        expect(item).to_be_visible(timeout=self.timeout)
        item.click()
        expect(field.locator(".v-select__selections")).to_contain_text(option, timeout=self.timeout)

    @log_method_exceptions
    def add_contact(self, contact: dict, designation: str, spaces: list[str], sms: bool = False) -> None:
        """Adds `contact` (first_name, last_name, email, phone_number) as
        `designation` for `spaces` on the tenant page that's open - with SMS
        on only when `sms`. Refuses anything but the Gmail test inbox and a
        fictional (707)/(714) 555-01xx number."""
        if not TEST_INBOX(contact["email"]) or not FICTIONAL_NUMBER.match(contact["phone_number"]):
            raise AssertionError(
                f"Not adding {contact['email']} / {contact['phone_number']} - only a test-inbox"
                " email and a fictional 555-01xx number"
            )
        name = f"{contact['first_name']} {contact['last_name']}"
        with allure.step(f"Add {designation} contact {name} for {spaces} (SMS {'on' if sms else 'off'})"):
            tab = self.page.get_by_role("tab", name="Tenant Info", exact=True).first
            expect(tab).to_be_visible(timeout=self.timeout)
            tab.click()
            panel = self._panel()
            expect(panel).to_be_visible(timeout=self.timeout)
            # A tenant with no contacts yet has only a "Click to Add" link in
            # the panel's header (seen on a fresh tenant, 2026-09-14); once
            # there's one, "+ Add New Contact" sits below the contacts (each
            # contact's own address "Click to Add" is never in the header).
            first_add = (
                panel.locator("button.v-expansion-panel-header a.hb-link")
                .filter(has_text=re.compile(r"^\s*Click to Add\s*$"))
                .first
            )
            add_new = panel.locator("a.hb-link").filter(has_text=re.compile(r"^\s*\+\s*Add New Contact\s*$")).first
            if first_add.is_visible():
                first_add.click()
            else:
                if not add_new.is_visible():
                    panel.locator("button.v-expansion-panel-header").first.click()
                expect(add_new).to_be_visible(timeout=self.timeout)
                add_new.click()

            first_name = panel.locator('input[id^="relationship_first_"]').last
            expect(first_name).to_be_visible(timeout=self.timeout)
            index = first_name.get_attribute("id").rsplit("_", 1)[-1]
            self._tick(self._field(panel, f"input#associated_space_{index}"), spaces)
            self._tick(self._field(panel, f"input#designations_{index}"), [designation])
            first_name.fill(contact["first_name"])
            panel.locator(f"input#relationship_last_{index}").fill(contact["last_name"])
            panel.locator(f"input#relationship_email_{index}").fill(contact["email"])
            self._choose(self._field(panel, 'input[id^="relationship_phone_type_"]'), "Mobile")
            self._choose(self._field(panel, f"input#relationship_phone_code_{index}"), "+1")
            panel.locator(f"input#relationship_phone_{index}").fill(contact["phone_number"])
            sms_box = panel.locator(f"input#relationship_sms_{index}")
            if sms:
                # Ticked through its field - the input itself is hidden; it's
                # clickable once the phone is filled (confirmed live 2026-09-14).
                self._field(panel, f"input#relationship_sms_{index}").locator(
                    ".v-input--selection-controls__ripple"
                ).first.click()
                expect(sms_box).to_be_checked(timeout=self.timeout)
            else:
                expect(sms_box).not_to_be_checked()

            panel.locator('button[name="QA-v-expansion-panel-content-hb-primary-button-Save"]').last.click()
            expect(panel.locator(f"input#relationship_first_{index}")).to_be_hidden(timeout=self.timeout)
            expect(panel.get_by_text(name, exact=True).first).to_be_visible(timeout=self.timeout)
