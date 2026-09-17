import re

import allure
from playwright.sync_api import Locator, Page, Response, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation

SCRIPT_HEADING = "Follow this script to gather information about the customer."
# GET .../leads/properties/<property id>/lead-script/ - the property's saved script.
_PROPERTY_SCRIPT_URL = re.compile(r"/leads/properties/[^/?]+/lead-script/?(?:\?|$)")


def _normalize(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(line.strip() for line in lines if line.strip())


def _is_property_script_load(response: Response) -> bool:
    return (
        response.request.method == "GET"
        and _PROPERTY_SCRIPT_URL.search(response.url) is not None
    )


class HBLeadScriptsPage:
    """Settings -> Lead Management's "The Script" (the follow-up script an
    agent reads to a new lead) and where it shows in Tenant Onboarding - the
    old Robot Lead_Management/AbilityToAddScripts suite.

    Confirmed live 2026-09-14 (uat_storoutlet): the Lead Management page has
    tabs "Corporate Settings" (Lead Questionnaire, The Script, Reservation
    Settings, Advanced Reservations and Rentals, Lead Expiration, Offline
    Spaces) and "Property Settings" (input#facility "Select Property", then
    The Script, Offline Spaces and any property-level panels). The editor is
    TinyMCE in an iframe.tox-edit-area__iframe - one per tab, only the open
    tab's visible (Robot's tiptap editor is gone). Save shows "Script Added
    Successfully".

    Tenant Onboarding's Lead step (aside.new_lead) shows p.script-description
    "Follow this script ..." and the script in .lead-interaction-rte-wrap
    whenever the property has a script record - even an empty one: Clear +
    Save leaves {"script": ""} behind (GET .../leads/properties/<id>/
    lead-script/), so the heading stays with an empty box, where a property
    that never had a script (Bellflower, data: []) shows no section at all.
    """

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float, nav: HBSettingsNavigation) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        # What the last open_property_script loaded: None when the property
        # has no script record, "" for an empty one, else the script's HTML.
        self.saved_script: str | None = None

    @log_method_exceptions
    def open_lead_management(self) -> None:
        with allure.step("Open Settings -> Lead Management"):
            self.nav.open_settings_panel()
            menu = self.page.locator(
                ".setting-menu-list-inactive-color, .setting-menu-list-active-color",
                has_text=re.compile(r"^\s*Lead Management\s*$"),
            )
            expect(menu).to_be_visible(timeout=self.timeout)
            menu.click()
            expect(self._landing_text()).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _landing_text(self) -> Locator:
        return self.page.get_by_text(
            re.compile(r"^\s*Set up and manage questions for the Lead Questionnaire")
        )

    @log_method_exceptions
    def assert_landing_page(self) -> None:
        with allure.step("Lead Management landing page: description and both tabs"):
            expect(self._landing_text()).to_be_visible(timeout=self.timeout)
            for tab in ("Corporate Settings", "Property Settings"):
                expect(self.page.get_by_role("tab", name=tab, exact=True)).to_be_visible(
                    timeout=self.timeout
                )

    @log_method_exceptions
    def open_tab(self, name: str) -> None:
        with allure.step(f"Open the {name} tab"):
            tab = self.page.get_by_role("tab", name=name, exact=True)
            tab.click()
            expect(tab).to_have_attribute("aria-selected", "true", timeout=self.timeout)

    @log_method_exceptions
    def _panel_titles(self) -> list[str]:
        # Visible only: the other tab's panels stay in the DOM, hidden.
        headers = self.page.locator(".v-expansion-panel-header").filter(visible=True)
        return [" ".join(text.split()) for text in headers.all_text_contents()]

    @log_method_exceptions
    def wait_for_panel_titles(self, expected_titles: list[str]) -> None:
        # Confirmed live 2026-09-14: "Advanced Reservations and Rentals" joins
        # the Corporate panels about a second after the other five.
        titles = None
        for _ in range(int(self.timeout / 500)):
            titles = self._panel_titles()
            if titles == expected_titles:
                return
            self.page.wait_for_timeout(500)
        raise AssertionError(
            f"Lead Management panels are {titles}, expected {expected_titles}"
        )

    @log_method_exceptions
    def _facility(self) -> Locator:
        return self.page.locator("input#facility").filter(visible=True)

    @log_method_exceptions
    def assert_property_prompt(self) -> None:
        # Robot 16449: the tab does nothing until a property is picked. Seen
        # 2026-09-14 straight after login, before any dashboard property.
        with allure.step("Property Settings asks for a property first"):
            expect(
                self.page.get_by_text("Please select a Property to continue.", exact=True)
            ).to_be_visible(timeout=self.timeout)
            expect(self._facility()).to_have_value("", timeout=self.timeout)
            expect(
                self.page.locator(".v-expansion-panel-header").filter(visible=True)
            ).to_have_count(0)

    @log_method_exceptions
    def select_property(self, settings_name: str) -> None:
        # Confirmed live 2026-09-14: this picker only ever offers the property
        # selected on the dashboard (cleared, it lists just that one) and
        # comes up preset to it - so pick the dashboard property first
        # (HBQuickLaunchPage.select_property).
        with allure.step(f"Property Settings on {settings_name}"):
            facility = self._facility()
            expect(facility).to_be_visible(timeout=self.timeout)
            if facility.input_value() != settings_name:
                facility.click()
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Backspace")
                option = self.page.get_by_role("option", name=settings_name, exact=True)
                try:
                    expect(option).to_be_visible(timeout=self.timeout)
                except AssertionError:
                    raise AssertionError(
                        f"Property Settings doesn't offer {settings_name!r} - select that "
                        "property on the dashboard first"
                    ) from None
                option.click()
            # Checked before anything is saved or cleared here, so a script
            # can never be written to some other property.
            expect(facility).to_have_value(settings_name, timeout=self.timeout)

    @log_method_exceptions
    def expand_script_panel(self) -> None:
        with allure.step("Expand The Script"):
            header = (
                self.page.locator(".v-expansion-panel-header")
                .filter(visible=True)
                .filter(has_text=re.compile(r"^\s*The Script\s*$"))
            )
            expect(header).to_be_visible(timeout=self.timeout)
            if "v-expansion-panel-header--active" not in (header.get_attribute("class") or ""):
                header.click()
            expect(
                self.page.get_by_text(
                    re.compile(r"^\s*The Script section allows managers to create and manage scripts")
                ).filter(visible=True)
            ).to_be_visible(timeout=self.timeout)
            expect(self._editor()).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def open_property_script(self, settings_name: str) -> None:
        # The editor shows before the property's saved script has loaded, and
        # that load replaces whatever the editor holds - confirmed live
        # 2026-09-14: text typed at 0.8 s was wiped when the script arrived at
        # 1.1 s, and a read before it sees "" even where a script exists. So
        # wait for the load and keep what it returned (self.saved_script).
        with self.page.expect_response(
            _is_property_script_load, timeout=self.timeout
        ) as script_load:
            self.open_lead_management()
            self.open_tab("Property Settings")
            self.select_property(settings_name)
            self.expand_script_panel()
        records = script_load.value.json().get("data") or []
        self.saved_script = records[0].get("script") if records else None
        allure.attach(
            repr(self.saved_script),
            name=f"{settings_name} saved script",
            attachment_type=allure.attachment_type.TEXT,
        )

    @log_method_exceptions
    def _editor(self) -> Locator:
        return self.page.locator("iframe.tox-edit-area__iframe").filter(visible=True)

    @log_method_exceptions
    def _editor_body(self) -> Locator:
        return self._editor().content_frame.locator("body")

    @log_method_exceptions
    def _button(self, name: str) -> Locator:
        return self.page.locator(f'button[name="{name}"]').filter(visible=True)

    @log_method_exceptions
    def assert_script_controls_enabled(self) -> None:
        with allure.step("The Script's Save and Clear are enabled"):
            expect(self._button("QA-v-card-hb-primary-button-Save")).to_be_enabled(
                timeout=self.timeout
            )
            expect(self._button("QA-v-card-hb-secondary-button-Clear")).to_be_enabled(
                timeout=self.timeout
            )

    @log_method_exceptions
    def read_script(self) -> str:
        body = self._editor_body()
        expect(body).to_be_attached(timeout=self.timeout)
        return _normalize(body.inner_text())

    @log_method_exceptions
    def _save(self) -> None:
        self._button("QA-v-card-hb-primary-button-Save").click()
        expect(
            self.page.get_by_text(re.compile(r"Script Added Successfully")).first
        ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def write_script(self, lines: list[str]) -> None:
        with allure.step("Type the script and Save"):
            body = self._editor_body()
            # Checked after a pause and retyped if it didn't stick: the saved
            # script's late load (see open_property_script) wipes the editor.
            for _ in range(3):
                body.click()
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Delete")
                for index, line in enumerate(lines):
                    if index:
                        self.page.keyboard.press("Enter")
                    self.page.keyboard.type(line)
                self.page.wait_for_timeout(1000)
                if _normalize(body.inner_text()) == "\n".join(lines):
                    break
            expect(body).to_contain_text(lines[-1], timeout=self.timeout)
            self._save()

    @log_method_exceptions
    def clear_script(self) -> None:
        with allure.step("Clear the script and Save"):
            if not self.saved_script:
                # HB saves nothing (no "Script Added Successfully") when the
                # script hasn't changed - seen 2026-09-14 when a run failed
                # before its script was saved. Anything typed but unsaved goes
                # when the page is left.
                allure.attach(
                    repr(self.saved_script),
                    name="No saved script - nothing to clear",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return
            self._button("QA-v-card-hb-secondary-button-Clear").click()
            # Robot's "Clear Scripts To Validate No Lead Scripts Are Added"
            # checked the editor was empty before saving - so does this.
            expect(self._editor_body()).to_have_text(re.compile(r"^\s*$"), timeout=self.timeout)
            self._save()

    @log_method_exceptions
    def _onboarding(self) -> Locator:
        return self.page.locator("aside.new_lead.v-navigation-drawer--open")

    @log_method_exceptions
    def assert_onboarding_script(self, lines: list[str]) -> None:
        with allure.step("Tenant Onboarding shows the script"):
            drawer = self._onboarding()
            expect(drawer.locator("p.script-description")).to_have_text(
                SCRIPT_HEADING, timeout=self.timeout
            )
            script = drawer.locator(".lead-interaction-rte-wrap")
            for line in lines:
                expect(script).to_contain_text(line, timeout=self.timeout)
            # Block by block (one <div> per line, as saved), not by innerText:
            # its line breaks depend on layout - the Spaces drawer's came back
            # run together ("...52f6cde7.Please confirm...", 2026-09-14).
            blocks = [
                " ".join(text.split())
                for text in script.locator(".list-style-override > *").all_text_contents()
            ]
            blocks = [block for block in blocks if block]
            assert blocks == lines, f"Onboarding script lines are {blocks!r}, expected {lines!r}"

    @log_method_exceptions
    def assert_onboarding_script_empty(self) -> None:
        with allure.step("Tenant Onboarding shows the script heading with no script"):
            drawer = self._onboarding()
            expect(drawer.locator("p.script-description")).to_have_text(
                SCRIPT_HEADING, timeout=self.timeout
            )
            expect(drawer.locator(".lead-interaction-rte-wrap")).to_have_text(
                re.compile(r"^\s*$"), timeout=self.timeout
            )

    @log_method_exceptions
    def assert_no_onboarding_script(self) -> None:
        with allure.step("Tenant Onboarding shows no script section"):
            drawer = self._onboarding()
            expect(drawer.locator("input#lead_initiated")).to_be_visible(timeout=self.timeout)
            # The section only renders once the property's lead-script request
            # returns, so a check made the moment the Lead step shows would
            # pass even where a script exists. Give it that time first.
            self.page.wait_for_timeout(3000)
            expect(drawer.locator("p.script-description")).to_have_count(0)
            expect(drawer.get_by_text(SCRIPT_HEADING)).to_have_count(0)

    @log_method_exceptions
    def close_restored_onboarding(self) -> None:
        # HB reopens a Tenant Onboarding drawer that was open when the page was
        # left - confirmed live 2026-09-14, it came back a few seconds after
        # going to the dashboard, and its backdrop blocked the dashboard's
        # property picker (a failed check had left one open, and the write
        # test's restore couldn't get past it). Close it if it comes back.
        expect(self.page.locator("#search-box")).to_be_visible(timeout=self.timeout)
        drawer = self._onboarding()
        for _ in range(10):
            if drawer.count() > 0 and drawer.first.is_visible():
                self.close_onboarding()
                return
            self.page.wait_for_timeout(500)

    @log_method_exceptions
    def close_onboarding(self) -> None:
        with allure.step("Close Tenant Onboarding"):
            drawer = self._onboarding()
            drawer.locator('button[name="QA-v-card-HbIcon-mdi-close"]').first.click()
            # Closing can first ask about the lead ("Not required" skips it);
            # confirmed live 2026-09-14 that it isn't asked every time.
            not_required = self.page.locator(
                '.v-dialog--active button[name="QA-HbBottomActionBar-hb-primary-button-Not-required"]'
            )
            for _ in range(20):
                if drawer.count() == 0 or not drawer.first.is_visible():
                    return
                if not_required.count() > 0 and not_required.first.is_visible():
                    not_required.first.click()
                self.page.wait_for_timeout(500)
            expect(drawer).to_be_hidden(timeout=self.timeout)
