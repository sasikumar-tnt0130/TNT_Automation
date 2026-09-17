import re

import allure
from playwright.sync_api import Locator, Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits

# Confirmed live 2026-09-14 (uat_storoutlet). Robot's category loop knew 11 of
# these; "Profile" and "Reverse Move-out" are new.
NOTE_CATEGORIES = [
    "Miscellaneous",
    "Address Changes",
    "Auctions",
    "Delinquency",
    "Invoices",
    "Leads",
    "Move In",
    "Move Outs",
    "Payments",
    "Profile",
    "Rent Changes",
    "Reverse Move-out",
    "Transfer",
]
COMMUNICATION_TYPES = ["All Communications", "Email", "Text", "Phone", "Mailings", "Notes", "Chat"]


def _exactly(text: str) -> re.Pattern:
    return re.compile(rf"^\s*{re.escape(text)}\s*$")


def _words(text: str) -> re.Pattern:
    # to_contain_text matches textContent, which can hold doubled spaces where
    # the page shows one - so words are joined by \s+, not a literal space.
    return re.compile(r"\s+".join(re.escape(word) for word in text.split()))


class HBTenantNotesPage:
    """Notes in HB's communication panel - the tenant profile's communication
    tab and the Communication Center - for the old Robot
    Unified_Communications/Categories_notes suite.

    Confirmed live 2026-09-14 (uat_storoutlet, Bellflower tenant
    "PilotAutomation SmokeTeste2fc87", spaces 0010 and 0013):
    - The panel's filters are v-selects showing "All Communications" (type)
      and "Tenant" (space); picking the "Notes" type adds a third, "All Notes"
      (category). Their menus are .menuable__content__active .v-list-item.
    - Compose (QA-v-menu-hb-primary-button-NoButtonText) -> "Add Note": a
      category select (default Miscellaneous), a space select (the tenant's
      first space preselected), a TinyMCE body in an iframe (Robot's tiptap
      editor is gone, and so is any link tool), "Pin Note" Yes/No (No by
      default) and Save. Save shows no message; the form just closes. Cancel
      didn't reliably close a draft - the window's own X does.
    - A saved note's card ([id^=interaction_id_], newest first, pinned ones
      on top) reads "Note(Rent Changes) Today, 3:11am Space 0010 <text>
      Created by:<user>". Its wrapper gets "isPinned" and an mdi-pin icon
      (mdi-pin-outline otherwise); clicking that icon toggles the pin.
    - HB reopens the Communication Center (and an open onboarding drawer)
      after a page load, over the page - close_restored_drawers.
    """

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def close_restored_drawers(self, wait_seconds: float = 0) -> None:
        with allure.step("Close drawers Hummingbird reopened"):
            drawers = self.page.locator(
                "aside.v-navigation-drawer--open.v-navigation-drawer--temporary"
            )
            for _ in range(int(wait_seconds * 2)):
                if drawers.count():
                    break
                self.page.wait_for_timeout(waits().poll_interval)
            not_required = self.page.locator(
                '.v-dialog--active button[name="QA-HbBottomActionBar-hb-primary-button-Not-required"]'
            )
            for _ in range(3):
                if drawers.count() == 0:
                    return
                close = drawers.last.locator('button[name$="HbIcon-mdi-close"]').filter(visible=True)
                if close.count():
                    close.first.click()
                else:
                    self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(1500)
                if not_required.count() and not_required.first.is_visible():
                    not_required.first.click()
                    self.page.wait_for_timeout(1500)
            expect(drawers).to_have_count(0, timeout=self.timeout)

    @log_method_exceptions
    def _compose_button(self) -> Locator:
        return (
            self.page.locator('button[name="QA-v-menu-hb-primary-button-NoButtonText"]')
            .filter(visible=True)
            .first
        )

    @log_method_exceptions
    def open_tenant(self, full_name: str) -> None:
        # From the Tenants list (HBTenantSpacesPage.open_tenants). A tenant
        # with several spaces has a row per space, hence .first.
        with allure.step(f"Open tenant {full_name}"):
            search = self.page.get_by_role("textbox", name="Search Tenants", exact=True)
            expect(search).to_be_visible(timeout=self.timeout)
            # Searched by the last name (a test tenant's unique word), and typed
            # again if the tenant doesn't show: the list can finish loading
            # after the search was typed and list every tenant again - seen
            # 2026-09-14 with the search box empty and the tenant's row not
            # among those drawn. The reload can also land between the search and
            # the click, which then opens nothing (a regression run 2026-09-14
            # stayed on the full list), so only a click that reached the
            # tenant's page ends the retries.
            cell = self.page.get_by_role("gridcell", name=full_name, exact=True).first
            for attempt in range(3):
                search.fill(full_name.split()[-1])
                self.page.keyboard.press("Enter")
                try:
                    expect(cell).to_be_visible(timeout=waits().long)
                    cell.click()
                    expect(self.page).to_have_url(re.compile(r"/contacts/[^/?#]+"), timeout=waits().long)
                    break
                except AssertionError:
                    if attempt == 2:
                        raise
            expect(self._compose_button()).to_be_visible(timeout=self.timeout)
            expect(self.page.get_by_text(full_name, exact=True).first).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def open_in_communication_center(self, full_name: str) -> None:
        # The app bar's forum icon (Robot: the second "NoButtonText" button),
        # for the dashboard's current property.
        with allure.step(f"Open {full_name} in the Communication Center"):
            self.page.locator('[name="QA-v-list-item-HbIcon-NoButtonText"]').filter(
                has=self.page.locator("i.mdi-forum")
            ).first.click()
            center = (
                self.page.locator("aside.v-navigation-drawer--open")
                .filter(has_text="Communication Center")
                .last
            )
            expect(center).to_be_visible(timeout=self.timeout)
            search = center.get_by_role("textbox", name="Search Tenant or Space")
            search.fill(full_name)
            self.page.keyboard.press("Enter")
            contact = (
                center.locator("div.hb-communication-overflow-handler")
                .filter(has_text=_exactly(full_name))
                .first
            )
            expect(contact).to_be_visible(timeout=self.timeout)
            contact.click()
            expect(self._compose_button()).to_be_visible(timeout=self.timeout)
            # Wait for the contact's cards to load: a Send Text opened while
            # the panel still showed its loading placeholders sent
            # {"space": ""} though its space select showed the space
            # (2026-09-14, a fresh tenant).
            self._wait_for_list_settled()

    @log_method_exceptions
    def _select_showing(self, text: str) -> Locator:
        return (
            self.page.locator(".v-select__selections")
            .filter(visible=True)
            .filter(has_text=_exactly(text))
            .first
        )

    @log_method_exceptions
    def _menu_items(self) -> Locator:
        return self.page.locator(".menuable__content__active .v-list-item")

    @log_method_exceptions
    def _options(self, select: Locator) -> list[str]:
        expect(select).to_be_visible(timeout=self.timeout)
        select.click()
        items = self._menu_items()
        expect(items.first).to_be_visible(timeout=self.timeout)
        self.page.wait_for_timeout(waits().poll_interval)
        options = [" ".join(text.split()) for text in items.filter(visible=True).all_text_contents()]
        self.page.keyboard.press("Escape")
        expect(items).to_have_count(0, timeout=self.timeout)
        return options

    @log_method_exceptions
    def _choose(self, select: Locator, option: str) -> None:
        expect(select).to_be_visible(timeout=self.timeout)
        select.click()
        item = self._menu_items().filter(has_text=_exactly(option)).first
        expect(item).to_be_visible(timeout=self.timeout)
        item.click()
        expect(select).to_have_text(_exactly(option), timeout=self.timeout)

    @log_method_exceptions
    def options_of(self, showing: str) -> list[str]:
        """The options of the filter currently showing `showing`."""
        return self._options(self._select_showing(showing))

    @log_method_exceptions
    def choose(self, showing: str, option: str) -> None:
        """Switches the filter currently showing `showing` to `option`."""
        with allure.step(f"Set filter: {showing} -> {option}"):
            select = self._select_showing(showing)
            expect(select).to_be_visible(timeout=self.timeout)
            select.click()
            item = self._menu_items().filter(has_text=_exactly(option)).first
            expect(item).to_be_visible(timeout=self.timeout)
            item.click()
            expect(self._select_showing(option)).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def reset_filters(self, spaces: list[str]) -> None:
        # The filters render a moment after the page - the space filter is
        # still blank a second in (confirmed live 2026-09-14) - so wait for
        # both before reading them.
        def any_of(texts: list[str]) -> re.Pattern:
            return re.compile(r"^\s*(" + "|".join(re.escape(text) for text in texts) + r")\s*$")

        visible_selects = self.page.locator(".v-select__selections").filter(visible=True)
        expect(visible_selects.filter(has_text=any_of(COMMUNICATION_TYPES)).first).to_be_visible(
            timeout=self.timeout
        )
        expect(visible_selects.filter(has_text=any_of(["Tenant", *spaces])).first).to_be_visible(
            timeout=self.timeout
        )
        for space in spaces:
            if self._select_showing(space).is_visible():
                self.choose(space, "Tenant")
        for kind in COMMUNICATION_TYPES[1:]:
            if self._select_showing(kind).is_visible():
                self.choose(kind, "All Communications")
        self._wait_for_list_settled()

    @log_method_exceptions
    def _wait_for_list_settled(self) -> None:
        # Seen 2026-09-14: a type filter chosen straight after the tenant
        # opened showed "Email" while every note stayed listed - most likely
        # the list's first load landing after the filter. So wait until the
        # card count has held for ~1.5 s (a tenant with no cards just runs
        # out the wait).
        cards = self.page.locator('[id^="interaction_id_"]').filter(visible=True)
        last, steady = -1, 0
        for _ in range(int(self.timeout / 500)):
            count = cards.count()
            steady = steady + 1 if count == last and count > 0 else 0
            if steady >= 3:
                return
            last = count
            self.page.wait_for_timeout(waits().poll_interval)

    @log_method_exceptions
    def _save_button(self) -> Locator:
        return (
            self.page.locator('button[name="QA-v-card-hb-primary-button-Save"]')
            .filter(visible=True)
            .first
        )

    @log_method_exceptions
    def _start_note(self) -> Locator:
        self._compose_button().click()
        add_note = self._menu_items().filter(has_text=_exactly("Add Note")).first
        expect(add_note).to_be_visible(timeout=self.timeout)
        add_note.click()
        expect(self._save_button()).to_be_visible(timeout=self.timeout)
        # The chat window holding the draft - the one with its own X and Save.
        form = (
            self.page.locator('button[name="QA-ChatWindow-HbIcon-mdi-close"]')
            .filter(visible=True)
            .first.locator(
                'xpath=ancestor::*[.//button[@name="QA-v-card-hb-primary-button-Save"]][1]'
            )
        )
        expect(form.locator("iframe.tox-edit-area__iframe")).to_be_visible(timeout=self.timeout)
        return form

    @log_method_exceptions
    def _form_selects(self, form: Locator) -> Locator:
        # Category, then space: the selects right after the "Add Note" header.
        # Counting selects from the top of the window once reached the panel's
        # own notes category filter ("All Notes") instead (2026-09-14).
        return form.locator(
            "xpath=.//*[normalize-space(text())='Add Note']"
            "/following::div[contains(@class,'v-select__selections')]"
        ).filter(visible=True)

    @log_method_exceptions
    def close_note_draft(self) -> None:
        self.page.locator('button[name="QA-ChatWindow-HbIcon-mdi-close"]').filter(
            visible=True
        ).first.click()
        expect(self._save_button()).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def note_form_options(self) -> dict:
        """Add Note's category and space options; the draft is closed unsaved."""
        with allure.step("Add note: category and space options"):
            form = self._start_note()
            selects = self._form_selects(form)
            options = {
                "category": self._options(selects.nth(0)),
                "space": self._options(selects.nth(1)),
            }
            self.close_note_draft()
            return options

    @log_method_exceptions
    def add_note(self, text: str, category: str, space: str, pin: bool) -> None:
        with allure.step(f"Add note: {category}, space {space}, pinned={pin}"):
            form = self._start_note()
            selects = self._form_selects(form)
            self._choose(selects.nth(0), category)
            self._choose(selects.nth(1), space)
            body = form.locator("iframe.tox-edit-area__iframe").content_frame.locator("body")
            # Typed again if it didn't stick: like The Script's editor, this one
            # can still be filling itself in when it first shows.
            for _ in range(3):
                self.page.wait_for_timeout(1000)
                body.click()
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Delete")
                self.page.keyboard.type(text)
                self.page.wait_for_timeout(1000)
                if " ".join(body.inner_text().split()) == text:
                    break
            expect(body).to_have_text(_exactly(text), timeout=self.timeout)
            answer = "Yes" if pin else "No"
            form.locator("label").filter(has_text=_exactly(answer)).first.click()
            expect(form.get_by_role("radio", name=answer, exact=True)).to_be_checked(
                timeout=self.timeout
            )
            self._save_button().click()
            expect(self._save_button()).to_be_hidden(timeout=self.timeout)
            expect(self._cards().filter(has_text=_words(text)).first).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def _cards(self) -> Locator:
        return self.page.locator('[id^="interaction_id_"]')

    @log_method_exceptions
    def note_card(self, token: str) -> Locator:
        return self._cards().filter(has_text=token).first

    @log_method_exceptions
    def _assert_pinned(self, card: Locator, pinned: bool) -> None:
        wrapper = card.locator(".hb-communication-wrapper").first
        if pinned:
            expect(wrapper).to_have_class(re.compile(r"\bisPinned\b"), timeout=self.timeout)
            expect(card.locator("i.mdi-pin")).to_have_count(1, timeout=self.timeout)
        else:
            expect(wrapper).not_to_have_class(re.compile(r"\bisPinned\b"), timeout=self.timeout)
            expect(card.locator("i.mdi-pin-outline")).to_have_count(1, timeout=self.timeout)

    @log_method_exceptions
    def assert_note_card(self, token: str, text: str, category: str, space: str, pinned: bool) -> None:
        with allure.step(f"Verify note {token}: Note({category}), Space {space}, pinned={pinned}"):
            card = self.note_card(token)
            expect(card).to_be_visible(timeout=self.timeout)
            expect(card).to_contain_text(
                re.compile(rf"Note\s*\(\s*{_words(category).pattern}\s*\)"), timeout=self.timeout
            )
            expect(card).to_contain_text(re.compile(rf"Space\s+{re.escape(space)}\b"))
            expect(card).to_contain_text(_words(text))
            expect(card).to_contain_text(re.compile(r"Created by:\s*\S"))
            self._assert_pinned(card, pinned)

    @log_method_exceptions
    def set_pinned(self, token: str, pinned: bool) -> None:
        """Pins or unpins a note and waits until HB has saved it. The list
        itself isn't a reliable read straight after the click - confirmed
        2026-09-14: the click sends PUT .../notes/<id> {"pinned": 1} (200),
        yet 4 s later the list had redrawn the note unpinned in its old place,
        and leaving the page at once lost the change. Check the pin on a
        freshly loaded list (assert_pinned_first / assert_note_card)."""
        with allure.step(f"{'Pin' if pinned else 'Unpin'} note {token}"):
            card = self.note_card(token)
            expect(card).to_be_visible(timeout=self.timeout)
            if (card.locator("i.mdi-pin").count() > 0) == pinned:
                return
            with self.page.expect_response(
                lambda response: response.request.method == "PUT" and "/notes/" in response.url,
                timeout=self.timeout,
            ) as saved:
                card.locator("i.mdi-pin, i.mdi-pin-outline").first.click()
            response = saved.value
            assert response.ok, f"Saving the pin failed: HTTP {response.status}"
            sent = response.request.post_data_json or {}
            assert sent.get("pinned") == (1 if pinned else 0), (
                f"The pin click saved pinned={sent.get('pinned')!r}, expected {int(pinned)}"
            )

    @log_method_exceptions
    def assert_pinned_first(self, tokens: list[str]) -> None:
        """The notes carrying `tokens` are pinned, and every pinned card is
        listed before every unpinned one."""
        with allure.step(f"Verify pinned notes {tokens} are listed on top"):
            cards = None
            for _ in range(int(self.timeout / 500)):
                cards = self._cards().evaluate_all(
                    "cards => cards.map(card => ({"
                    " text: card.innerText,"
                    " pinned: /\\bisPinned\\b/.test("
                    "(card.querySelector('.hb-communication-wrapper') || card).className) }))"
                )
                pinned_at = [index for index, card in enumerate(cards) if card["pinned"]]
                unpinned_at = [index for index, card in enumerate(cards) if not card["pinned"]]
                ours = [
                    next((index for index, card in enumerate(cards) if token in card["text"]), None)
                    for token in tokens
                ]
                if (
                    None not in ours
                    and all(index in pinned_at for index in ours)
                    and (not unpinned_at or max(pinned_at) < min(unpinned_at))
                ):
                    return
                self.page.wait_for_timeout(waits().poll_interval)
            listed = [
                ("pinned   " if card["pinned"] else "unpinned ") + " ".join(card["text"].split())[:70]
                for card in (cards or [])[:6]
            ]
            raise AssertionError(f"Pinned notes {tokens} aren't all listed on top: {listed}")

    @log_method_exceptions
    def expect_notes(self, visible: list[str], hidden: list[str]) -> None:
        with allure.step(f"Verify listed: {visible}; not listed: {hidden}"):
            for token in visible:
                expect(self.note_card(token)).to_be_visible(timeout=self.timeout)
            for token in hidden:
                expect(self._cards().filter(has_text=token)).to_have_count(0, timeout=self.timeout)

    @log_method_exceptions
    def assert_note_read_only(self, token: str) -> None:
        # Robot 14467: typing into a saved note does nothing, and its text can
        # be selected (copied).
        with allure.step(f"Verify note {token} can't be edited and its text is selectable"):
            card = self.note_card(token)
            expect(card.locator('[contenteditable="true"], textarea, input')).to_have_count(0)
            text = card.get_by_text(re.compile(re.escape(token))).first
            user_select = text.evaluate("element => getComputedStyle(element).userSelect")
            assert user_select != "none", f"The note's text can't be selected (user-select: {user_select})"
