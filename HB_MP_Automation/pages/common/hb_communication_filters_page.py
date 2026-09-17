import re

import allure
from playwright.sync_api import Locator, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_tenant_notes_page import HBTenantNotesPage
from common_utils.waits import waits


class HBCommunicationFiltersPage(HBTenantNotesPage):
    """The communication panel's space filter - the old Robot
    Unified_Communications/Space_Specific suite. Builds on HBTenantNotesPage's
    navigation and filter helpers (the same panel).

    Confirmed live 2026-09-14 (uat_storoutlet):
    - Every card's text starts with its type ("Email (Out)", "Text (Out)",
      "Note(Rent Changes)") and names its space ("Space 0010"); a
      tenant-level one names none.
    - With the space filter on one space and the type filter on Email or
      Text, only that type's cards for that space are listed (Bellflower
      "PilotAutomation SmokeTeste2fc87": 7 emails for 0010, 5 for 0013).
    - Send Email's window has its own "Space/Subject" select next to "To".
    - A lead (Leads -> its name) opens a view with an "Overview /
      Contact Details / Communication / Access" tab row; its Communication
      tab has the same filters, and QA-HbHeader-HbIcon-mdi-close closes it.
    """

    @log_method_exceptions
    def cards(self) -> list[tuple[str, str]]:
        """(type, space) of each listed card - e.g. ("Email", "0010"), or
        "Tenant" for a card that names no space."""
        listed = []
        for text in self._cards().filter(visible=True).all_inner_texts():
            text = " ".join(text.split())
            kind = re.match(r"^(\w+)", text)
            space = re.search(r"\bSpace\s+(\S+)", text)
            listed.append((kind.group(1) if kind else text[:20], space.group(1) if space else "Tenant"))
        return listed

    @log_method_exceptions
    def expect_cards_only(self, kind: str, space: str) -> None:
        with allure.step(f"Only {kind} cards for space {space} are listed"):
            seen = None
            for _ in range(int(self.timeout / 500)):
                seen = self.cards()
                if seen and all(card == (kind, space) for card in seen):
                    return
                self.page.wait_for_timeout(waits().poll_interval)
            raise AssertionError(
                f"Expected only {kind} cards for space {space}, listed: {sorted(set(seen or []))}"
            )

    @log_method_exceptions
    def _chat_window(self) -> Locator:
        return (
            self.page.locator('button[name="QA-ChatWindow-HbIcon-mdi-close"]')
            .filter(visible=True)
            .first.locator('xpath=ancestor::*[contains(@class,"chat-window-container")][1]')
        )

    @log_method_exceptions
    def email_compose_space_options(self) -> list[str]:
        """Send Email's "Space/Subject" options. The draft is closed with the
        window's X - nothing is sent."""
        with allure.step("Send email: Space/Subject options"):
            self._compose_button().click()
            send_email = self._menu_items().filter(has_text=re.compile(r"^\s*Send Email\s*$")).first
            expect(send_email).to_be_visible(timeout=self.timeout)
            send_email.click()
            window = self._chat_window()
            label = window.get_by_text("Space/Subject", exact=True)
            expect(label).to_be_visible(timeout=self.timeout)
            options = self._options(
                label.locator("xpath=following::div[contains(@class,'v-select__selections')][1]")
            )
            close = self.page.locator('button[name="QA-ChatWindow-HbIcon-mdi-close"]').filter(visible=True)
            close.first.click()
            expect(close).to_have_count(0, timeout=self.timeout)
            return options

    @log_method_exceptions
    def open_first_lead_communication(self) -> None:
        """Opens the first lead in the Leads grid's current view and its
        Communication tab."""
        with allure.step("Open the first lead's Communication tab"):
            name = self.page.locator(".ag-center-cols-container .ag-row").first.locator(
                '[col-id="lead_name"]'
            )
            expect(name).to_be_visible(timeout=self.timeout)
            name.click()
            tab = self.page.get_by_role("tab", name="Communication", exact=True).first
            expect(tab).to_be_visible(timeout=self.timeout)
            tab.click()
            expect(self._compose_button()).to_be_visible(timeout=self.timeout)
            expect(self._select_showing("Tenant")).to_be_visible(timeout=self.timeout)
            self._wait_for_list_settled()

    @log_method_exceptions
    def close_lead_view(self) -> None:
        close = self.page.locator('button[name="QA-HbHeader-HbIcon-mdi-close"]').filter(visible=True)
        close.first.click()
        expect(self.page.get_by_role("tab", name="Communication", exact=True)).to_have_count(
            0, timeout=self.timeout
        )
