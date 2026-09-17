import re
from pathlib import Path

import allure
from playwright.sync_api import Locator, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_communication_filters_page import HBCommunicationFiltersPage

# Texts only ever go to the reserved fictional range the test guests use
# (conftest's mp_guest / hb_lead_guest) - never to an older (707) 719-xxxx
# number, which could be a real person's.
FICTIONAL_PHONE = re.compile(r"\(\s*(?:707|714)\s*\)\s*555-01\d\d")
MAILINATOR = re.compile(r"@mailinator\.com\b", re.IGNORECASE)
SENT_TODAY = re.compile(r"Today,\s*\d{1,2}:\d{2}\s*[ap]m", re.IGNORECASE)
CARD_KINDS = {
    "email": re.compile(r"Email\s*\(Out\)"),
    "text": re.compile(r"Text\s*\(Out\)"),
    "call": re.compile(r"Call\s*\(In\)"),
    "note": re.compile(r"Note\s*\("),
}
SUBJECT = 'input[placeholder="Enter Subject"]'
TEXT_MESSAGE = 'textarea[placeholder="Compose your personal message..."]'
CALL_NOTE = 'textarea[placeholder="Compose a note about this call..."]'


class HBCommunicationComposePage(HBCommunicationFiltersPage):
    """Compose from the communication panel (tenant profile, Communication
    Center, a lead's Communication tab) - the old Robot
    Unified_Communications/Communications_test suite.

    Confirmed live 2026-09-14 (uat_storoutlet):
    - Compose -> Send Email: "To" recipient chips (".hb-chip-overflow",
      "<address> (Primary)"), Space/Subject, Template, "Enter Subject", a
      TinyMCE body in an iframe, Send (QA-v-card-hb-primary-button-Send).
      Send Text: To*, a space select, "Compose your personal message...",
      Send. Log Phone Call: Call Direction (Incoming by default), "Compose a
      note about this call...", Log (QA-v-card-hb-primary-button-Log). Each
      window closes by itself once sent; no message is shown.
    - Each compose window is a .chat-window-container - and so is a lead's
      own communication panel, so a window is found by its own form (the
      innermost container holding it), not by the nearest close button.
    - The new cards: "Email (Out) Today, 8:37am Space 0003 - <subject>",
      "Text (Out) Today, 8:37am Space 0003 <message>", "Call (In) Today,
      8:37am <note>". The email reached the tenant's Mailinator inbox from
      "Storage Outlet - Bellflower".
    - With every recipient removed (their mdi-close-circle), Send is refused:
      "Error: All fields are required." (email), "Please review fields"
      (text); the window stays open.
    - The To list also offers additional contacts, e.g. "<address>
      (Alternate)" - ticking one adds a second chip.
    - Email cards start collapsed (mdi-chevron-down); under the Text filter
      multi-line texts are expanded (mdi-chevron-up); phone cards have none.
    """

    @log_method_exceptions
    def _compose_window(self, option: str) -> Locator:
        marker = (
            self.page.get_by_text("Pin Note", exact=True)
            if option == "Add Note"
            else self.page.locator({"Send Email": SUBJECT, "Send Text": TEXT_MESSAGE, "Log Phone Call": CALL_NOTE}[option])
        )
        return self.page.locator(".chat-window-container").filter(has=marker).last

    @log_method_exceptions
    def _open_compose(self, option: str) -> Locator:
        window = self._compose_window(option)
        # Opened once more if the window doesn't show: in a lead's panel a
        # "Send Email" clicked while the list was still loading never opened
        # (2026-09-14). Only retried when no window is showing, so it can't
        # open a second one.
        for attempt in range(2):
            self._compose_button().click()
            item = self._menu_items().filter(has_text=re.compile(rf"^\s*{re.escape(option)}\s*$")).first
            expect(item).to_be_visible(timeout=self.timeout)
            item.click()
            try:
                expect(window).to_be_visible(timeout=15000 if attempt == 0 else self.timeout)
                return window
            except AssertionError:
                if attempt == 1:
                    raise
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(1000)
        return window

    @log_method_exceptions
    def _close_window(self, window: Locator) -> None:
        window.locator('button[name="QA-ChatWindow-HbIcon-mdi-close"]').last.click()
        expect(window).to_have_count(0, timeout=self.timeout)

    @log_method_exceptions
    def recipients(self, window: Locator) -> list[str]:
        # A contact opened moments before can still be loading in the panel
        # behind the window, and its chips come late: a fresh tenant's Send
        # Text read none (2026-09-14). With none after the wait, the send
        # guards refuse.
        try:
            expect(window.locator(".hb-chip-overflow").filter(visible=True).first).to_be_visible(timeout=20000)
        except AssertionError:
            pass
        return [
            " ".join(text.split())
            for text in window.locator(".hb-chip-overflow").filter(visible=True).all_text_contents()
        ]

    @log_method_exceptions
    def _tick_recipient(self, window: Locator, address: str) -> None:
        window.locator(".v-input").filter(has=self.page.locator("input#To")).locator(
            ".v-select__slot"
        ).first.click()
        option = self._menu_items().filter(has_text=address).first
        expect(option).to_be_visible(timeout=self.timeout)
        option.click()
        self.page.keyboard.press("Escape")
        expect(window.locator(".hb-chip-overflow").filter(has_text=address)).to_be_visible(
            timeout=self.timeout
        )

    @log_method_exceptions
    def _send(self, window: Locator) -> None:
        window.locator('button[name="QA-v-card-hb-primary-button-Send"]').last.click()
        expect(window).to_have_count(0, timeout=self.timeout)

    @log_method_exceptions
    def _type_in_editor(self, window: Locator, text: str) -> None:
        editor = window.locator("iframe").last.content_frame.locator("body")
        # Typed again if it didn't stick: the editor can still be filling
        # itself in when it first shows (as The Script's and Add Note's do).
        for _ in range(3):
            self.page.wait_for_timeout(1000)
            editor.click()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Delete")
            self.page.keyboard.type(text)
            self.page.wait_for_timeout(1000)
            if text in " ".join(editor.inner_text().split()):
                break
        expect(editor).to_contain_text(text, timeout=self.timeout)

    @log_method_exceptions
    def _attach(self, window: Locator, file_path: str) -> None:
        # Paperclip -> Upload opens an "Attach File" dialog with a file input and
        # an Upload button that stays disabled until a file is picked; the file
        # then shows as a chip in the window (confirmed live 2026-09-14).
        window.locator("i.mdi-paperclip").first.click()
        upload = self._menu_items().filter(has_text=re.compile(r"^\s*Upload\s*$")).first
        expect(upload).to_be_visible(timeout=self.timeout)
        upload.click()
        dialog = self.page.locator(".v-dialog--active").filter(has_text="Attach File").last
        expect(dialog).to_be_visible(timeout=self.timeout)
        dialog.locator('input[type="file"]').set_input_files(file_path)
        confirm = dialog.locator('button[name="QA-HbBottomActionBar-hb-primary-button-Upload"]')
        expect(confirm).to_be_enabled(timeout=self.timeout)
        confirm.click()
        expect(dialog).to_be_hidden(timeout=self.timeout)
        expect(window.locator(".v-chip").filter(has_text=Path(file_path).name)).to_be_visible(
            timeout=self.timeout
        )

    @log_method_exceptions
    def send_email(
        self,
        subject: str,
        body: str,
        also_to: str | None = None,
        attachment: str | None = None,
        space: str | None = None,
    ) -> list[str]:
        """Sends an email to the contact's default recipient (plus `also_to`,
        one of its other contacts, and the file `attachment`) - for `space`
        when given, see _send_for_space - and returns the recipients. Refuses
        to send unless every recipient is a Mailinator test inbox."""
        with allure.step(f"Send Email: {subject}"):
            window = self._open_compose("Send Email")
            if also_to:
                self._tick_recipient(window, also_to)
            recipients = self.recipients(window)
            if not recipients or not all(MAILINATOR.search(recipient) for recipient in recipients):
                self._close_window(window)
                raise AssertionError(f"Not emailing {recipients} - only Mailinator test inboxes")
            window.locator(SUBJECT).fill(subject)
            self._type_in_editor(window, body)
            if attachment:
                self._attach(window, attachment)
            self._send(window)
            return recipients

    @log_method_exceptions
    def _only_recipient(self, window: Locator, address: str) -> None:
        # The default recipients are removed with their chips' close icons
        # (as in send_without_recipient), then `address` is ticked in the To
        # list.
        self.recipients(window)
        remove = window.locator("i.mdi-close-circle")
        for _ in range(5):
            if remove.count() == 0:
                break
            remove.first.click()
            self.page.wait_for_timeout(300)
        expect(window.locator(".hb-chip-overflow")).to_have_count(0, timeout=self.timeout)
        self._tick_recipient(window, address)

    @log_method_exceptions
    def send_text(self, message: str, space: str | None = None, only_to: str | None = None) -> list[str]:
        """Sends a text to the contact's default recipient - or, with
        `only_to`, to that other contact alone (e.g. "(707) 555-0123", an
        SMS-enabled Alternate) - for `space` when given, and returns the
        recipients. Refuses unless every recipient is a fictional 555-01xx
        number."""
        with allure.step(f"Send Text: {message}"):
            window = self._open_compose("Send Text")
            if only_to:
                self._only_recipient(window, only_to)
            recipients = self.recipients(window)
            if not recipients or not all(FICTIONAL_PHONE.search(recipient) for recipient in recipients):
                self._close_window(window)
                raise AssertionError(
                    f"Not texting {recipients} - only fictional (707)/(714) 555-01xx numbers"
                )
            window.locator(TEXT_MESSAGE).fill(message)
            self._send_for_space(window, space)
            return recipients

    @log_method_exceptions
    def _send_for_space(self, window: Locator, space: str | None) -> None:
        """Sends the window's email or text. With `space`, first picks it in
        the window's space select (input#mainView: "Tenant" or the tenant's
        spaces - the same in both windows) and checks the send request (POST
        .../send-message, {"space": "0003", ...}) carried it: two runs' texts
        were saved as "Tenant" though the select showed the space
        (2026-09-14), and the request tells a page fault from a server one."""
        if not space:
            self._send(window)
            return
        select = (
            window.locator(".v-input")
            .filter(has=self.page.locator("input#mainView"))
            .locator(".v-select__selections")
            .first
        )
        self._choose(select, space)
        expect(select).to_have_text(re.compile(rf"^\s*{re.escape(space)}\s*$"))
        with self.page.expect_request(
            lambda request: request.method == "POST" and "/send-message" in request.url,
            timeout=self.timeout,
        ) as sent:
            self._send(window)
        self.sent_space = (sent.value.post_data_json or {}).get("space")
        assert self.sent_space == space, (
            f"The message was sent with space {self.sent_space!r}, not {space!r}"
        )

    @log_method_exceptions
    def log_phone_call(self, note: str, direction: str = "Incoming") -> None:
        """Logs a call - Call Direction "Incoming" (the window's default) or
        "Outgoing" (radios, confirmed live 2026-09-14)."""
        with allure.step(f"Log Phone Call ({direction}): {note}"):
            window = self._open_compose("Log Phone Call")
            window.locator("label").filter(has_text=re.compile(rf"^\s*{re.escape(direction)}\s*$")).first.click()
            expect(window.get_by_role("radio", name=direction, exact=True)).to_be_checked(timeout=self.timeout)
            window.locator(CALL_NOTE).fill(note)
            window.locator('button[name="QA-v-card-hb-primary-button-Log"]').last.click()
            expect(window).to_have_count(0, timeout=self.timeout)

    @log_method_exceptions
    def add_plain_note(self, text: str) -> None:
        """Add Note with its defaults (category, space) and Pin No."""
        with allure.step(f"Add Note: {text}"):
            window = self._open_compose("Add Note")
            self._type_in_editor(window, text)
            window.locator('button[name="QA-v-card-hb-primary-button-Save"]').last.click()
            expect(window).to_have_count(0, timeout=self.timeout)

    @log_method_exceptions
    def expect_sent_card(self, token: str, kind: str, space: str | None = None) -> None:
        """The card carrying `token` is of `kind` ("email", "text", "call",
        "note"), dated today and - when given - for `space`."""
        with allure.step(f"A {kind} card for {token}, dated today"):
            card = self.note_card(token)
            expect(card).to_be_visible(timeout=self.timeout)
            expect(card).to_contain_text(CARD_KINDS[kind], timeout=self.timeout)
            expect(card).to_contain_text(SENT_TODAY)
            if space:
                expect(card).to_contain_text(re.compile(rf"Space\s+{re.escape(space)}\b"))

    @log_method_exceptions
    def send_without_recipient(self, option: str, expected_message: str) -> None:
        """Removes every recipient, presses Send and checks HB refuses with
        `expected_message`; the window is then closed. Nothing can be sent:
        there is no one to send to."""
        with allure.step(f"{option} with no recipient is refused: {expected_message}"):
            window = self._open_compose(option)
            remove = window.locator("i.mdi-close-circle")
            for _ in range(5):
                if remove.count() == 0:
                    break
                remove.first.click()
                self.page.wait_for_timeout(300)
            expect(window.locator(".hb-chip-overflow")).to_have_count(0, timeout=self.timeout)
            window.locator(SUBJECT if option == "Send Email" else TEXT_MESSAGE).fill(
                "QA automation - no recipient"
            )
            window.locator('button[name="QA-v-card-hb-primary-button-Send"]').last.click()
            expect(self.page.get_by_text(expected_message).first).to_be_visible(timeout=self.timeout)
            expect(window).to_be_visible()
            self._close_window(window)

    @log_method_exceptions
    def card_chevrons(self, kind: str) -> list[tuple[str, str]]:
        """(type, "up" / "down" / "") of each listed card's expand icon, once
        the list shows `kind` cards only ("Email", "Text", "Call") - a type
        filter reloads the list, and reading it straight away found none."""
        cards = []
        for _ in range(int(self.timeout / 500)):
            cards = [
                (re.match(r"\s*(\w+)", card["text"]).group(1) if card["text"].strip() else "", card["chevron"])
                for card in self._cards().filter(visible=True).evaluate_all(
                    "cards => cards.map(card => {"
                    " const icon = [...card.querySelectorAll('i')]"
                    "   .map(i => (i.className.match(/mdi-chevron-(up|down)/) || [])[1]).find(Boolean);"
                    " return { text: card.innerText, chevron: icon || '' }; })"
                )
            ]
            if cards and all(card_kind == kind for card_kind, _ in cards):
                return cards
            self.page.wait_for_timeout(500)
        return cards
