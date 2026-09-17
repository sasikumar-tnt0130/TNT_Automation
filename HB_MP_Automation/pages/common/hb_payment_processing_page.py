import re

import allure
from playwright.sync_api import Locator, Page, Response, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation
from common_utils.waits import waits

METHODS = ("Credit Cards", "ACH", "Direct Debit")
# GET .../v2/companies/<company>/properties/<property>/connections - the
# property's configured gateways.
_CONNECTIONS_URL = re.compile(r"/properties/[^/?]+/connections/?(?:\?|$)")
_ACTIVE_MENU = ".v-menu__content.menuable__content__active"


def _is_connections_load(response: Response) -> bool:
    return response.request.method == "GET" and _CONNECTIONS_URL.search(response.url) is not None


class HBPaymentProcessingPage:
    """Settings -> Payment Processing: each property's payment gateways.
    ensure_integration applies the user's rule (2026-09-15): a gateway that
    isn't set is added from config, a set one is checked against config, and
    one that doesn't match is removed and added again. Gateway values come
    from config/secrets.ini and never reach the report - steps name the fields
    only.

    Confirmed live 2026-09-15 (uat_storoutlet, read-only walks): tabs
    "Payment Configuration" (selected) and "Payment Processing Reports"; until
    a property is picked (textbox "Select Property") the page only says
    "Please select a Property to continue." A property then shows expansion
    panels, all open: "Tenant Payments" (with a "Resume Application"
    button), "Credit Cards", "ACH" and "Direct Debit" - each with a required
    "Merchant*" v-select (textbox "Select merchant") - and "Direct Deposit"
    (a switch, "Disabled" when off). There is no Save button on the loaded
    page.

    A configured method shows its merchant in the v-select and the input is
    disabled, so its list can't be opened (Chula Vista: Credit Cards and ACH
    both "Tenant Payments"). An unconfigured one is empty and opens a list:
    Credit Cards - Authorize.Net, Tsys, Tenant Payments, Fat Zebra; ACH -
    Forte, Tsys, Tenant Payments; Direct Debit - Fat Zebra (Bellflower, which
    had no merchant on any method). The page loads GET .../properties/<id>/
    connections, e.g. {"data": {"connections": [{"name": "tenant_payments",
    "type": "ach"}, {"name": "tenant_payments", "type": "card"}]}}; only
    name and type are kept from it - the response can carry gateway details.

    A set Tenant Payments card (Chula Vista, walked 2026-09-15 without
    saving) also shows API Key*, Public API Key*, Acct Number* and Device ID*
    (all locked), Swiper Terminals, and "Remove Integration" and "Edit"
    buttons; Edit unlocks only Public API Key and adds "+ Add New Device", a
    "Cancel" link and "Save". A set Tenant Payments ACH shows Acct Number* and
    only "Remove Integration" - a set merchant is changed by removing the
    integration first.
    """

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float, nav: HBSettingsNavigation) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        # (name, type) pairs from the last select_property's connections load,
        # e.g. [("tenant_payments", "ach"), ("tenant_payments", "card")].
        self.connections: list[tuple[str, str]] = []
        # Every connections load, newest last - see select_property.
        self._connection_loads: list[list[tuple[str, str]]] = []
        page.on("response", self._record_connections)

    def _record_connections(self, response: Response) -> None:
        if _is_connections_load(response):
            self._connection_loads.append(self._connection_pairs(response))

    @log_method_exceptions
    def open_payment_processing(self) -> None:
        with allure.step("Open Settings → Payment Processing"):
            self.nav.open_settings_panel()
            menu = self.page.locator(
                ".setting-menu-list-inactive-color, .setting-menu-list-active-color",
                has_text=re.compile(r"^\s*Payment Processing\s*$"),
            )
            expect(menu).to_be_visible(timeout=self.timeout)
            menu.click()
            expect(
                self.page.get_by_role("tab", name="Payment Configuration", exact=True)
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_landing_page(self) -> None:
        with allure.step("Verify Payment Processing landing page: both tabs and the property prompt"):
            for tab in ("Payment Configuration", "Payment Processing Reports"):
                expect(self.page.get_by_role("tab", name=tab, exact=True)).to_be_visible(
                    timeout=self.timeout
                )
            expect(
                self.page.get_by_text("Please select a Property to continue.", exact=True)
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def select_property(self, property_name: str) -> None:
        with allure.step(f"Select payment processing property: {property_name}"):
            loads_before = len(self._connection_loads)
            self.nav.select_property(property_name)
            self._close_open_menus()
            expect(
                self.page.get_by_role("button", name="Credit Cards", exact=True)
            ).to_be_visible(timeout=self.timeout)
            if not self._wait_for_connections_load(loads_before):
                # Picking the property the page already shows loads nothing
                # new, and the newest load on record can be another
                # property's (seen live 2026-09-15: Bellflower was given Chula
                # Vista's connections) - so reload: the page keeps the picked
                # property and loads its connections (confirmed live).
                self.page.reload(wait_until="domcontentloaded")
                self.open_payment_processing()
                expect(
                    self.page.get_by_role("button", name="Credit Cards", exact=True)
                ).to_be_visible(timeout=self.timeout)
                if not self._wait_for_connections_load(loads_before):
                    raise AssertionError(f"No connections load for {property_name} - can't tell its gateways")
            self.connections = self._connection_loads[-1]
            allure.attach(
                repr(self.connections), name="configured connections (name, type)",
                attachment_type=allure.attachment_type.TEXT,
            )

    @staticmethod
    def _connection_pairs(response: Response) -> list[tuple[str, str]]:
        try:
            body = response.json()
        except Exception:
            return []
        data = body.get("data") if isinstance(body, dict) else None
        items = data.get("connections", []) if isinstance(data, dict) else []
        return [
            (str(item.get("name", "")), str(item.get("type", "")))
            for item in items
            if isinstance(item, dict)
        ]

    @log_method_exceptions
    def _close_open_menus(self) -> None:
        for _ in range(3):
            if self.page.locator(_ACTIVE_MENU).count() == 0:
                return
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(waits().poll_interval)

    @log_method_exceptions
    def _method_panel(self, method: str) -> Locator:
        header = self.page.locator(".v-expansion-panel-header").filter(
            has_text=re.compile(rf"^\s*{re.escape(method)}\s*$")
        )
        return self.page.locator(".v-expansion-panel").filter(has=header).first

    @log_method_exceptions
    def _merchant_input(self, method: str) -> Locator:
        return self._method_panel(method).get_by_role("textbox", name="Select merchant").first

    @log_method_exceptions
    def _merchant_slot(self, method: str) -> Locator:
        return self._merchant_input(method).locator(
            "xpath=ancestor::*[contains(@class,'v-select__slot')][1]"
        ).first

    @log_method_exceptions
    def merchant(self, method: str) -> str | None:
        """The merchant shown for "Credit Cards", "ACH" or "Direct Debit", or
        None when none is set."""
        selection = self._merchant_slot(method).locator(".v-select__selection")
        if selection.count() == 0:
            return None
        return " ".join(selection.first.inner_text().split()) or None

    @log_method_exceptions
    def is_merchant_locked(self, method: str) -> bool:
        """A configured method's merchant input is disabled."""
        return self._merchant_input(method).is_disabled()

    @log_method_exceptions
    def merchant_options(self, method: str) -> list[str]:
        """Opens an unconfigured method's merchant list, reads it and closes
        it with Escape - nothing is picked."""
        with allure.step(f"Read the {method} merchant options"):
            if self.is_merchant_locked(method):
                raise AssertionError(
                    f"The {method} merchant is locked ({self.merchant(method)!r} is configured) - "
                    "its list can't be opened"
                )
            shown = self.merchant(method)
            self._close_open_menus()
            self._merchant_slot(method).click()
            menu = self.page.locator(_ACTIVE_MENU).last
            expect(menu).to_be_visible(timeout=self.timeout)
            options = [" ".join(text.split()) for text in menu.get_by_role("option").all_inner_texts()]
            self._close_open_menus()
            if self.merchant(method) != shown:
                raise AssertionError(
                    f"Reading the {method} options changed its merchant from {shown!r} "
                    f"to {self.merchant(method)!r}"
                )
            return options

    @log_method_exceptions
    def _panel_field(self, method: str, field: str) -> Locator:
        # HB names these inputs by data-vv-name ("api_key", "deviceId"); their
        # name attribute is empty (confirmed live 2026-09-15). secrets.ini
        # keys come lower-cased from ConfigParser ("deviceid"), so matched
        # case-insensitively.
        return self._method_panel(method).locator(
            f'input[data-vv-name="{field}" i], input[name="{field}" i]'
        ).first

    @log_method_exceptions
    def select_merchant(self, method: str, merchant: str) -> None:
        """Picks the merchant on a method with none set; its fields then show
        (Authorize.Net: "Authorize.net Login*" authnetLogin and
        "Authorize.net Key*" authnetKey, a "Cancel" link and "Save" - walked
        on Bellflower 2026-09-15 without saving)."""
        with allure.step(f"Select {merchant} for {method}"):
            if self.is_merchant_locked(method):
                raise AssertionError(f"The {method} merchant is set ({self.merchant(method)!r}) - remove it first")
            self._close_open_menus()
            self._merchant_slot(method).click()
            option = self.page.locator(_ACTIVE_MENU).last.get_by_role("option", name=merchant, exact=True)
            expect(option).to_be_visible(timeout=self.timeout)
            option.click()
            expect(
                self._merchant_slot(method).locator(".v-select__selection").first
            ).to_have_text(merchant, timeout=self.timeout)

    @log_method_exceptions
    def fill_integration(self, method: str, fields: dict[str, str]) -> None:
        with allure.step(f"Fill the {method} integration: {', '.join(fields)}"):
            for field, value in fields.items():
                box = self._panel_field(method, field)
                expect(box).to_be_editable(timeout=self.timeout)
                box.fill(value)

    @log_method_exceptions
    def save_integration(self, method: str, merchant: str) -> None:
        """Save, then the merchant shows set and locked, as on a configured
        property (the save itself not yet walked live, 2026-09-15)."""
        with allure.step(f"Save the {method} integration"):
            loads_before = len(self._connection_loads)
            panel = self._method_panel(method)
            panel.get_by_role("button", name="Save", exact=True).click()
            # Seen live 2026-09-15 (Bellflower, Tenant Payments card): Save sent
            # no request and the form stayed open - the panel's own messages
            # then say why, reported instead of a bare timeout.
            messages = panel.locator(".v-messages__message, .error--text").filter(visible=True)
            locked = False
            for _ in range(int(self.timeout / 500)):
                if self._merchant_input(method).is_disabled():
                    locked = True
                    break
                if messages.count():
                    break
                self.page.wait_for_timeout(waits().poll_interval)
            if not locked:
                shown = sorted({" ".join(text.split()) for text in messages.all_inner_texts() if text.strip()})
                raise AssertionError(
                    f"{method}: Save didn't set the {merchant} integration - the form says {shown or 'nothing'}"
                )
            self.assert_merchant(method, merchant)
            if self._wait_for_connections_load(loads_before):
                self.connections = self._connection_loads[-1]

    @log_method_exceptions
    def _wait_for_connections_load(self, loads_before: int) -> bool:
        for _ in range(40):
            if len(self._connection_loads) > loads_before:
                return True
            self.page.wait_for_timeout(waits().poll_interval)
        return False

    @log_method_exceptions
    def mismatched_fields(self, method: str, fields: dict[str, str]) -> list[str]:
        """Names (never values) of the fields whose shown value differs from
        config. A partly masked value ("****6667") is compared on its visible
        end; a fully masked one can't be compared and is skipped (noted in
        the report); a field missing from the panel counts as a mismatch."""
        mismatched, unverifiable = [], []
        for field, expected in fields.items():
            box = self._panel_field(method, field)
            if box.count() == 0:
                mismatched.append(field)
                continue
            shown = box.input_value().strip()
            if shown == expected:
                continue
            # A saved API key shows as a short mask only (3 characters on
            # Chula Vista, 2026-09-15) - nothing to compare.
            if re.fullmatch(r"[*•●xX]+", shown):
                unverifiable.append(field)
                continue
            visible_end = re.split(r"[*•●]+", shown)[-1]
            if visible_end == shown or not expected.endswith(visible_end):
                mismatched.append(field)
        if unverifiable:
            allure.attach(
                ", ".join(unverifiable), name=f"{method}: fully masked, not compared",
                attachment_type=allure.attachment_type.TEXT,
            )
        return mismatched

    @log_method_exceptions
    def remove_integration(self, method: str) -> None:
        """Walked up to the confirmation 2026-09-15 (Chula Vista ACH, backed
        out): "Remove Integration" opens a new dialog whose only text button
        is "Delete" (plus two icon buttons); Escape doesn't close it. Delete
        itself isn't walked yet - afterwards the method is expected to show
        no merchant, unlocked."""
        with allure.step(f"Remove the {method} integration"):
            dialogs = self.page.locator(".v-dialog--active")
            dialogs_before = dialogs.count()
            self._method_panel(method).get_by_role("button", name="Remove Integration", exact=True).click()
            expect(dialogs).to_have_count(dialogs_before + 1, timeout=self.timeout)
            confirm = dialogs.last.get_by_role("button", name="Delete", exact=True)
            expect(confirm).to_be_visible(timeout=self.timeout)
            confirm.click()
            expect(self._merchant_input(method)).to_be_enabled(timeout=self.timeout)
            self.assert_merchant(method, None)

    @log_method_exceptions
    def ensure_integration(
        self,
        method: str,
        merchant: str,
        fields: dict[str, str],
        optional: tuple[str, ...] = (),
        not_compared: tuple[str, ...] = (),
    ) -> str:
        """The user's rule (2026-09-15): not set -> add; set and matching
        config -> leave; set but different merchant or values -> remove and
        add. Returns "added", "matched" or "replaced". Only the values filled
        in in config/secrets.ini are compared, so a matching merchant passes
        while some are still empty; adding or replacing needs every value
        not named in `optional` and fails with what's missing, touching
        nothing. Empty optional fields are left empty. Fields named in
        `not_compared` aren't checked against HB, but are still filled in
        when adding."""
        with allure.step(f"Verify {method}: {merchant} as in config"):
            if not merchant:
                raise AssertionError(f"{method}: no merchant in config/secrets.ini")
            filled = {name: value for name, value in fields.items() if value.strip()}
            unfilled = [name for name in fields if name not in filled]
            empty = [name for name in unfilled if name.lower() not in optional]
            compared = {name: value for name, value in filled.items() if name.lower() not in not_compared}
            skipped = unfilled + [name for name in filled if name not in compared]
            shown = self.merchant(method)
            mismatched = self.mismatched_fields(method, compared) if shown == merchant else []
            if shown == merchant and not mismatched:
                if skipped:
                    allure.attach(
                        ", ".join(skipped),
                        name=f"{method}: not compared (empty or not_compared in config/secrets.ini)",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                return "matched"
            if empty:
                raise AssertionError(
                    f"{method}: HB shows {shown or 'no merchant'}, config wants {merchant}"
                    + (f" (differing: {', '.join(mismatched)})" if mismatched else "")
                    + f" - fill in {empty} in config/secrets.ini so it can be "
                    + ("added" if shown is None else "replaced")
                )
            if shown is not None:
                allure.attach(
                    f"shown merchant {shown!r}, config {merchant!r}; differing fields: {mismatched or 'n/a'}",
                    name=f"{method}: doesn't match config", attachment_type=allure.attachment_type.TEXT,
                )
                self.remove_integration(method)
            self.select_merchant(method, merchant)
            self.fill_integration(method, filled)
            self.save_integration(method, merchant)
            return "added" if shown is None else "replaced"

    @log_method_exceptions
    def ensure_gateways(self, gateways) -> dict[str, str]:
        """ensure_integration for each config_reader.GatewayConfig on the
        selected property, always with all of its settings (a script that
        dropped not_compared once replaced an integration, 2026-09-15).
        Returns {gateway key: "added" / "matched" / "replaced"}."""
        return {
            gateway.key: self.ensure_integration(
                gateway.method, gateway.merchant, gateway.fields, gateway.optional, gateway.not_compared
            )
            for gateway in gateways
        }

    @log_method_exceptions
    def direct_deposit_enabled(self) -> bool:
        return self._method_panel("Direct Deposit").get_by_role("switch").first.is_checked()

    @log_method_exceptions
    def assert_merchant(self, method: str, expected: str | None) -> None:
        """expected None: no merchant set."""
        with allure.step(f"Verify {method} merchant is {expected or 'not set'}"):
            selection = self._merchant_slot(method).locator(".v-select__selection")
            if expected is None:
                expect(selection).to_have_count(0, timeout=self.timeout)
            else:
                expect(selection.first).to_have_text(expected, timeout=self.timeout)

    @log_method_exceptions
    def assert_connection(self, payment_type: str, gateway: str = "tenant_payments") -> None:
        """payment_type as the connections response names it: "card" or
        "ach" - e.g. assert_connection("ach") before ACH rentals on the
        Two-Step property."""
        with allure.step(f"Verify the property has a {gateway} {payment_type} connection"):
            assert (gateway, payment_type) in self.connections, (
                f"No {gateway} {payment_type} connection - the property has {self.connections}"
            )
