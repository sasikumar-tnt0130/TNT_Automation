import re

import allure
from playwright.sync_api import Locator, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_communication_compose_page import (
    CARD_KINDS,
    SENT_TODAY,
    HBCommunicationComposePage,
)
from pages.common.hb_tenant_notes_page import _exactly, _words

LIVE_AGENT = "Need to talk to a live agent?"
ALTERNATE_CARD = re.compile(r"Email\s*\(Out\)\s*-\s*Alternate")
# A new email's status tooltip - "Sent Today, 9:32am" (confirmed 2026-09-14;
# Robot expected "Success"). Delivered/Opened are accepted too, in case the
# mail provider has reported back by the time it's read.
EMAIL_STATUS = re.compile(
    r"^(Sent|Delivered|Opened)\s+Today,\s*\d{1,2}:\d{2}\s*[ap]m", re.IGNORECASE
)
DIRECTION = re.compile(r"^\s*(\w+)\s*\((In|Out)\)")


class HBEmailCardsPage(HBCommunicationComposePage):
    """Email and text cards in the Communication Center - the old Robot
    Unified_Communications/Email_uiupdate and Sms_uiupdate suites.

    Confirmed live 2026-09-14 (uat_storoutlet, Bellflower, "PilotAutomation
    SmokeTeste636bd"):
    - An email to the tenant and its alternate contact makes two cards:
      "Email (Out) Today, 9:32am Space 0003 - <subject> Sent by:<user>" and
      "Email (Out)-Alternate Today, 9:32am To: QA AltContact Space 0003 -
      <subject> Sent by:<user>". Only the alternate's has "To:" and an
      mdi-account-multiple-outline icon, whose tooltip reads "QA AltContact
      Alternate <email> 17075550199".
    - An email card's mdi-check-circle tooltip is its status and time ("Sent
      Today, 9:32am"). mdi-pin-outline ("Pin") pins a card - POST
      .../contacts/<id>/pinned-interactions - and mdi-pin unpins it - POST
      .../pinned-interactions/<id>. Outgoing cards have no Reply button.
    - A text card reads "Text (Out) Today, 9:29am Space 0003 <message> Sent
      by:<user>" with mdi-message-arrow-right-outline and the pin icon - no
      status icon, and no tooltips. A long text also has mdi-chevron-up (shown
      expanded).
    - Tooltips are .v-tooltip__content.menuable__content__active; the "Need
      to talk to a live agent?" banner is one too.
    - The center's left column (.col-md-5, view select "Latest Messages")
      lists one item per contact, its latest message: "Email (Out) Today,
      9:32am <subject> To: <tenant> Current" (or "Text (Out) ... <message>
      To: ...") - the chip is the tenant's status, as on the right column's
      mini profile.
    - Its mdi-filter-variant icon opens a "Filter your communications" dialog
      with Incoming / Outgoing checkboxes and Apply; "Clear Filters" applies at
      once and closes it. Under Incoming the list shows "Email (In)" (icon
      mdi-email-receive) and "Text (In)" (mdi-message-arrow-left) items -
      other people's messages, so they are only read, never opened.
    """

    @log_method_exceptions
    def _center(self) -> Locator:
        return (
            self.page.locator("aside.v-navigation-drawer--open")
            .filter(has_text="Communication Center")
            .last
        )

    @log_method_exceptions
    def _left_items(self) -> Locator:
        return self._center().locator(".col-md-5").first.locator(".hb-communication-wrapper")

    @log_method_exceptions
    def open_center(self) -> None:
        """The Communication Center with no contact searched - every contact's
        latest message."""
        with allure.step("Open the Communication Center"):
            self.page.locator('[name="QA-v-list-item-HbIcon-NoButtonText"]').filter(
                has=self.page.locator("i.mdi-forum")
            ).first.click()
            expect(self._center()).to_be_visible(timeout=self.timeout)
            search = self._center().get_by_role("textbox", name="Search Tenant or Space")
            if search.input_value():
                search.fill("")
                self.page.keyboard.press("Enter")
            expect(self._left_items().first).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def reopen_center(self, full_name: str) -> None:
        """Closes the Communication Center and opens the contact again - a
        fresh load of its cards (as with notes, the list's redraw straight
        after a pin click isn't a reliable read)."""
        with allure.step(f"Open {full_name} in the Communication Center again"):
            self.close_restored_drawers()
            self.open_in_communication_center(full_name)
            self._wait_for_list_settled()

    @log_method_exceptions
    def tooltip_of(self, icon: Locator) -> str:
        tooltip = (
            self.page.locator(".v-tooltip__content.menuable__content__active")
            .filter(has_not_text=LIVE_AGENT)
            .last
        )
        expect(icon).to_be_visible(timeout=self.timeout)
        for attempt in range(3):
            icon.hover()
            try:
                expect(tooltip).to_be_visible(timeout=5000)
                break
            except AssertionError:
                self.page.mouse.move(0, 0)
                if attempt == 2:
                    raise
        text = " ".join(tooltip.inner_text().split())
        self.page.mouse.move(0, 0)
        self.page.wait_for_timeout(500)
        return text

    @log_method_exceptions
    def card(self, token: str, kind: str) -> Locator:
        """The outgoing "email" (to the primary contact) or "text" card
        carrying `token`."""
        return (
            self._cards()
            .filter(has_text=token)
            .filter(has_text=CARD_KINDS[kind])
            .filter(has_not_text=ALTERNATE_CARD)
            .first
        )

    @log_method_exceptions
    def email_card(self, token: str, alternate: bool = False) -> Locator:
        if not alternate:
            return self.card(token, "email")
        return self._cards().filter(has_text=token).filter(has_text=ALTERNATE_CARD).first

    @log_method_exceptions
    def _expect_email_card(self, card: Locator, subject: str, space: str) -> str:
        """Checks what every email card shows and returns its status tooltip."""
        expect(card).to_be_visible(timeout=self.timeout)
        expect(card).to_contain_text(CARD_KINDS["email"], timeout=self.timeout)
        expect(card).to_contain_text(SENT_TODAY)
        expect(card).to_contain_text(
            re.compile(rf"Space\s+{re.escape(space)}\s*-\s*{_words(subject).pattern}")
        )
        expect(card).to_contain_text(re.compile(r"Sent by:\s*\S"))
        status = self.tooltip_of(card.locator("i.mdi-check-circle").first)
        allure.attach(status, name="Status tooltip", attachment_type=allure.attachment_type.TEXT)
        assert EMAIL_STATUS.search(status), f"Unexpected email status tooltip: {status!r}"
        sent_at = SENT_TODAY.search(" ".join(card.inner_text().split())).group(0)
        assert " ".join(sent_at.split()) in status, (
            f"The status tooltip {status!r} doesn't carry the card's time {sent_at!r}"
        )
        return status

    @log_method_exceptions
    def assert_primary_email_card(self, token: str, subject: str, space: str) -> None:
        # Robot 14167/14168/14169/14178.
        with allure.step(f"Email {token} to the primary contact: space, subject, time, status, no To:"):
            card = self.email_card(token)
            self._expect_email_card(card, subject, space)
            expect(card).not_to_contain_text(ALTERNATE_CARD)
            expect(card).not_to_contain_text("To:")
            expect(card.locator("i.mdi-account-multiple-outline")).to_have_count(0)

    @log_method_exceptions
    def assert_alternate_email_card(self, token: str, subject: str, space: str, contact: dict) -> None:
        # Robot 14164, for the Alternate designation (user choice 2026-09-14).
        with allure.step(f"Email {token} to {contact['designation']} contact {contact['name']}"):
            card = self.email_card(token, alternate=True)
            self._expect_email_card(card, subject, space)
            expect(card).to_contain_text(ALTERNATE_CARD)
            expect(card).to_contain_text(re.compile(rf"To:\s*{_words(contact['name']).pattern}"))
            tooltip = self.tooltip_of(card.locator("i.mdi-account-multiple-outline").first)
            for part in ("name", "designation", "email", "phone"):
                assert contact[part] in tooltip, (
                    f"The contact tooltip {tooltip!r} doesn't show the {part} {contact[part]!r}"
                )

    @log_method_exceptions
    def assert_attachment_icon(self, token: str) -> None:
        # Robot 14174: a paperclip whose tooltip was "Has Attachment(s)".
        with allure.step(f"Email {token} shows the attachment icon"):
            card = self.email_card(token)
            expect(card).to_be_visible(timeout=self.timeout)
            clip = card.locator("i.mdi-paperclip")
            expect(clip).to_have_count(1, timeout=self.timeout)
            tooltip = self.tooltip_of(clip.first)
            assert re.search(r"attachment", tooltip, re.IGNORECASE), (
                f"Unexpected attachment tooltip: {tooltip!r}"
            )

    @log_method_exceptions
    def assert_text_card(self, token: str, message: str, space: str) -> None:
        # Robot 14183 (today's time), 14191 (space and message), 14186 (pin
        # icon) and 14187 (a long text shows expanded).
        with allure.step(f"Text {token}: time, space, message, pin icon, expanded"):
            card = self.card(token, "text")
            expect(card).to_be_visible(timeout=self.timeout)
            expect(card).to_contain_text(SENT_TODAY)
            try:
                expect(card).to_contain_text(re.compile(rf"Space\s+{re.escape(space)}\b"), timeout=10000)
            except AssertionError as error:
                # send_text checked the request carried the space, so a card
                # without it is HB's saving, not the page (seen 2026-09-14).
                if getattr(self, "sent_space", None) == space:
                    shown = re.search(r"Space\s+\S+|\bTenant\b", " ".join(card.inner_text().split()))
                    raise AssertionError(
                        f"HB saved text {token} as {shown.group(0) if shown else 'no space'!r} although"
                        f" its send request carried space {space!r} - an HB server issue"
                    ) from error
                raise
            expect(card).to_contain_text(_words(message))
            expect(card).to_contain_text(re.compile(r"Sent by:\s*\S"))
            expect(card).not_to_contain_text("To:")
            expect(card.locator("i.mdi-message-arrow-right-outline")).to_have_count(1)
            expect(card.locator("i.mdi-pin-outline")).to_have_count(1)
            # HB shows the collapse icon only when the text overflows its
            # collapsed box (24px, about 1.5 lines), so it depends on the
            # window's width: a 251-character text took 2 lines and had the
            # icon in a 730px column, but fit on 1 line with no icon at
            # 1920x1080 (2026-09-14). Check the text really wraps first.
            # Check on a fresh load (reopen_center): the card drawn straight
            # after its own send stays collapsed (24px, overflow hidden, for a
            # minute), while a reload shows the same 857-character text
            # expanded, 7 lines at 730px (2026-09-14).
            text_box = card.locator(".hb-communication-text-night-light").filter(has_text=token).first
            expect(text_box).to_have_css("overflow", "visible", timeout=self.timeout)
            lines = 0.0
            for _ in range(20):
                lines = text_box.evaluate(
                    "box => box.getBoundingClientRect().height"
                    " / (parseFloat(getComputedStyle(box).lineHeight) || 16)"
                )
                if lines > 2:
                    break
                self.page.wait_for_timeout(500)
            assert lines > 2, (
                f"The text takes {lines:.1f} line(s) in this window - too short to show the"
                " collapse icon; the test message needs to be longer"
            )
            expect(card.locator("i.mdi-chevron-up")).to_have_count(1, timeout=self.timeout)
            expect(card.locator("i.mdi-chevron-down")).to_have_count(0)

    @log_method_exceptions
    def assert_text_collapses(self, token: str) -> None:
        # Robot 14187: the long text's icon collapses and expands it. Collapsed,
        # its text box clips (overflow hidden, 24px high); expanded, it shows in
        # full (confirmed live 2026-09-14). Heights depend on the window's
        # width, so the icon and the clipping are checked instead.
        with allure.step(f"Text {token} collapses and expands again"):
            card = self.card(token, "text")
            text_box = card.locator(".hb-communication-text-night-light").filter(has_text=token).first
            expect(text_box).to_have_css("overflow", "visible", timeout=self.timeout)
            card.locator("i.mdi-chevron-up").first.click()
            expect(card.locator("i.mdi-chevron-down")).to_have_count(1, timeout=self.timeout)
            expect(card.locator("i.mdi-chevron-up")).to_have_count(0)
            expect(text_box).to_have_css("overflow", "hidden")
            card.locator("i.mdi-chevron-down").first.click()
            expect(card.locator("i.mdi-chevron-up")).to_have_count(1, timeout=self.timeout)
            expect(card.locator("i.mdi-chevron-down")).to_have_count(0)
            expect(text_box).to_have_css("overflow", "visible")

    @log_method_exceptions
    def pin_card(self, token: str, kind: str, pinned: bool) -> None:
        """Pins or unpins the `kind` card carrying `token` and waits until HB
        has saved it. Check the result on a fresh load (reopen_center, then
        assert_card_pinned)."""
        with allure.step(f"{'Pin' if pinned else 'Unpin'} {kind} {token}"):
            card = self.card(token, kind)
            expect(card).to_be_visible(timeout=self.timeout)
            if (card.locator("i.mdi-pin").count() > 0) == pinned:
                return
            with self.page.expect_response(
                lambda response: response.request.method == "POST"
                and "/pinned-interactions" in response.url,
                timeout=self.timeout,
            ) as saved:
                card.locator("i.mdi-pin, i.mdi-pin-outline").first.click()
            response = saved.value
            assert response.ok, f"Saving the pin failed: HTTP {response.status}"
            unpinned = re.search(r"/pinned-interactions/[^/?]+", response.url) is not None
            assert unpinned != pinned, (
                f"The click sent {'an unpin' if unpinned else 'a pin'} ({response.url})"
            )

    @log_method_exceptions
    def assert_card_pinned(self, token: str, kind: str, pinned: bool) -> None:
        """The `kind` card carrying `token` is (un)pinned; pinned, it's listed
        with the pinned cards, before every unpinned one."""
        with allure.step(f"The {kind} {token} is {'pinned on top' if pinned else 'not pinned'}"):
            card = self.card(token, kind)
            expect(card).to_be_visible(timeout=self.timeout)
            expect(card.locator("i.mdi-pin")).to_have_count(1 if pinned else 0, timeout=self.timeout)
            expect(card.locator("i.mdi-pin-outline")).to_have_count(0 if pinned else 1)
            if not pinned:
                return
            listed = []
            for _ in range(int(self.timeout / 500)):
                listed = [
                    {"text": " ".join(card["text"].split()), "pinned": card["pinned"]}
                    for card in self._cards().filter(visible=True).evaluate_all(
                        "cards => cards.map(card => ({"
                        " text: card.innerText, pinned: !!card.querySelector('i.mdi-pin') }))"
                    )
                ]
                ours = next(
                    (
                        index
                        for index, card in enumerate(listed)
                        if token in card["text"]
                        and CARD_KINDS[kind].search(card["text"])
                        and not ALTERNATE_CARD.search(card["text"])
                    ),
                    None,
                )
                pinned_at = [index for index, card in enumerate(listed) if card["pinned"]]
                unpinned_at = [index for index, card in enumerate(listed) if not card["pinned"]]
                if (
                    ours is not None
                    and ours in pinned_at
                    and (not unpinned_at or max(pinned_at) < min(unpinned_at))
                ):
                    return
                self.page.wait_for_timeout(500)
            shown = [
                ("pinned   " if card["pinned"] else "unpinned ") + card["text"][:70] for card in listed[:6]
            ]
            raise AssertionError(f"The {kind} {token} isn't listed pinned on top: {shown}")

    @log_method_exceptions
    def assert_left_card(self, token: str, tenant_name: str, status: str, kind: str = "email") -> None:
        # Robot 14179/14192 (the left card: To: tenant name and status) and
        # 14177/14190 (the same status as the right column's).
        with allure.step(f"Left card: {kind} {token} To: {tenant_name}, status {status}"):
            item = self._left_items().filter(has_text=token).first
            expect(item).to_be_visible(timeout=self.timeout)
            expect(item).to_contain_text(CARD_KINDS[kind])
            expect(item).to_contain_text(SENT_TODAY)
            expect(item).to_contain_text(re.compile(rf"To:\s*{_words(tenant_name).pattern}"))
            expect(item.locator(".hb-status-v-chip")).to_have_text(_exactly(status))
            profile_status = (
                self._center().locator(".hb-mini-profile-status .hb-status-v-chip").filter(visible=True).first
            )
            expect(profile_status).to_have_text(_exactly(status), timeout=self.timeout)

    @log_method_exceptions
    def _filter_dialog(self) -> Locator:
        return self.page.locator(".v-dialog--active").filter(has_text="Filter your communications").last

    @log_method_exceptions
    def _open_filter_dialog(self) -> Locator:
        self._center().locator("i.mdi-filter-variant").first.click()
        dialog = self._filter_dialog()
        expect(dialog).to_be_visible(timeout=self.timeout)
        return dialog

    @log_method_exceptions
    def filter_direction(self, direction: str) -> None:
        """Filters the Communication Center to "Incoming" or "Outgoing"."""
        with allure.step(f"Communication Center filter: {direction}"):
            dialog = self._open_filter_dialog()
            dialog.get_by_text(direction, exact=True).click()
            apply = dialog.locator('button[name="QA-HbBottomActionBar-hb-primary-button-Apply"]')
            expect(apply).to_be_enabled(timeout=self.timeout)
            apply.click()
            expect(dialog).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def clear_direction_filter(self) -> None:
        with allure.step("Communication Center: Clear Filters"):
            dialog = self._open_filter_dialog()
            dialog.get_by_text("Clear Filters", exact=True).click()
            try:
                expect(dialog).to_be_hidden(timeout=5000)
            except AssertionError:
                dialog.locator('button[name="QA-v-card-HbIcon-mdi-close"]').click()
                expect(dialog).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def _load_more_left_items(self) -> bool:
        """Scrolls the center's list to its end; True if more items loaded. It
        loads 20 at a time - under Outgoing the first 20 were all emails and
        the first text was the 23rd (confirmed 2026-09-14)."""
        items = self._left_items()
        before = items.count()
        items.last.evaluate(
            "item => { let node = item.parentElement;"
            " while (node && !(node.scrollHeight > node.clientHeight + 10"
            " && /auto|scroll/.test(getComputedStyle(node).overflowY))) node = node.parentElement;"
            " if (node) node.scrollTop = node.scrollHeight; }"
        )
        for _ in range(20):
            self.page.wait_for_timeout(500)
            if items.count() > before:
                return True
        return False

    @log_method_exceptions
    def left_list_items(self, direction: str, kind: str | None = None, pages: int = 5) -> list[dict]:
        """Kind ("Email", "Text", ...), direction ("In" / "Out") and icons of
        each item in the center's list, once every item with a direction is
        `direction` - the list reloads a moment after a filter is applied.
        With `kind`, up to `pages` more pages are loaded until one such item
        is listed."""
        items = []
        loaded = 0
        for _ in range(int(self.timeout / 500)):
            items = []
            for item in self._left_items().filter(visible=True).evaluate_all(
                r"items => items.map(item => ({ text: item.innerText,"
                r" icons: [...item.querySelectorAll('i')].map(i => (i.className.match(/mdi-[\w-]+/) || [''])[0]) }))"
            ):
                match = DIRECTION.match(item["text"])
                items.append(
                    {
                        "kind": match.group(1) if match else "",
                        "direction": match.group(2) if match else "",
                        "icons": [icon for icon in item["icons"] if icon],
                        "text": " ".join(item["text"].split())[:60],
                    }
                )
            # With `kind`, only that kind's items must match: the filter picks
            # contacts by their latest message, and a contact with a call In
            # and Out logged in the same minute was listed under Outgoing as
            # "Call (In)" (2026-09-14).
            with_direction = [
                item for item in items if item["direction"] and (kind is None or item["kind"] == kind)
            ]
            if (kind is None and not with_direction) or not all(
                item["direction"] == direction for item in with_direction
            ):
                self.page.wait_for_timeout(500)
                continue
            if (
                kind is None
                or any(item["kind"] == kind for item in items)
                or loaded >= pages
                or not self._load_more_left_items()
            ):
                return items
            loaded += 1
        raise AssertionError(
            f"Expected only ({direction}) items, listed: {[item['text'] for item in items[:8]]}"
        )
