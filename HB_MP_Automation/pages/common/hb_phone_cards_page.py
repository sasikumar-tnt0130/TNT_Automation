import re

import allure
from playwright.sync_api import expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_communication_compose_page import SENT_TODAY
from pages.common.hb_email_cards_page import HBEmailCardsPage
from pages.common.hb_tenant_notes_page import _words

# Call Direction -> the card's label and icon. Call (In) / mdi-phone-incoming
# confirmed live 2026-09-14; Call (Out) / mdi-phone-outgoing as in Robot.
CALLS = {
    "Incoming": (re.compile(r"Call\s*\(In\)"), "mdi-phone-incoming"),
    "Outgoing": (re.compile(r"Call\s*\(Out\)"), "mdi-phone-outgoing"),
}


class HBPhoneCardsPage(HBEmailCardsPage):
    """Logged phone calls in the Communication Center - the old Robot
    Unified_Communications/Phone_uiupdate suite (its 14298).

    Confirmed live 2026-09-14 (uat_storoutlet, Bellflower): Log Phone Call
    has Call Direction radios, Incoming (checked by default) and Outgoing, a
    note and Log. A logged call's card reads "Call (In) Today, 9:29am <note>
    Manager:<user>" with mdi-phone-incoming and the pin icon - no buttons and
    no property/source line (the playback, call back, voicemail and missed
    call cards come only from calls through HB's Charm phone integration).
    """

    @log_method_exceptions
    def assert_call_card(self, token: str, direction: str, note: str) -> None:
        kind, icon = CALLS[direction]
        other = next(other_icon for name, (_, other_icon) in CALLS.items() if name != direction)
        with allure.step(f"Verify {direction.lower()} call {token}: label, icon, time, note, manager"):
            card = self._cards().filter(has_text=token).first
            expect(card).to_be_visible(timeout=self.timeout)
            expect(card).to_contain_text(kind, timeout=self.timeout)
            expect(card).to_contain_text(SENT_TODAY)
            expect(card).to_contain_text(_words(note))
            expect(card).to_contain_text(re.compile(r"Manager:\s*\S"))
            expect(card.locator(f"i.{icon}")).to_have_count(1)
            expect(card.locator(f"i.{other}")).to_have_count(0)

    @log_method_exceptions
    def assert_left_call(self, tenant_name: str, direction: str, check_label: bool = True) -> None:
        """Under the Communication Center's Incoming or Outgoing filter, the
        tenant is listed today - with check_label, as a call of that direction.
        The filter picks contacts by their latest message while the item shows
        the latest by time: a call In and Out logged in the same minute was
        listed under Outgoing as "Call (In)" (2026-09-14)."""
        kind, icon = CALLS[direction]
        with allure.step(f"Verify {direction} filter lists {tenant_name}"):
            self.filter_direction(direction)
            try:
                search = self._center().get_by_role("textbox", name="Search Tenant or Space")
                search.fill(tenant_name.split()[-1])
                self.page.keyboard.press("Enter")
                item = self._left_items().filter(has_text=tenant_name).first
                expect(item).to_be_visible(timeout=self.timeout)
                expect(item).to_contain_text(SENT_TODAY)
                if check_label:
                    expect(item).to_contain_text(kind, timeout=self.timeout)
                    expect(item.locator(f"i.{icon}")).to_have_count(1)
            finally:
                self.clear_direction_filter()
