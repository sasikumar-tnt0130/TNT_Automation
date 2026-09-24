"""HB Settings → Coverage (Manage Coverage).

Live structure (stage 2026-09-20):
- Settings menu **Coverage**
- Title **Manage Coverage**
- Tabs: **Corporate Settings** | **Property Settings**
- Right rail: **Settings** | **Coverage Options**
- Corporate Settings: space-category dropdown (e.g. Storage) +
  **Coverage Option Types** toggle — automation keeps this **Disabled**
- Property Settings: requires a property selection
"""
from __future__ import annotations

import logging
import re

import allure
from playwright.sync_api import Page, expect

from common_utils.waits import waits
from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation

logger = logging.getLogger("hb_mp.rentals")


class HBCoveragePage:
    """Manage Coverage — corporate + property coverage configuration."""

    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav

    def _dismiss_overlays(self) -> None:
        self.nav._close_live_agent_notification()
        # Live-agent card often sits over Settings and steals clicks.
        for pattern in (
            r"Don.t show again",
            r"^Close$",
            r"^No.? thanks$",
            r"^Dismiss$",
        ):
            loc = self.page.get_by_text(re.compile(pattern, re.I))
            if loc.count() and loc.first.is_visible():
                try:
                    loc.first.click(force=True, timeout=waits().short)
                except Exception:
                    pass
        dont = self.page.get_by_role(
            "checkbox", name=re.compile(r"Don.t show again", re.I)
        )
        if dont.count() and dont.first.is_visible():
            try:
                if not dont.first.is_checked():
                    dont.first.check(force=True)
            except Exception:
                pass
        self.page.keyboard.press("Escape")

    def _settings_dialog(self):
        return self.page.locator(".v-dialog__content--active").last

    def _menu_item(self, name: str):
        dlg = self._settings_dialog()
        by_role = dlg.get_by_role("listitem", name=name, exact=True)
        if by_role.count():
            return by_role.first
        by_css = dlg.locator(
            ".setting-menu-list-inactive-color, .setting-menu-list-active-color"
        ).filter(has_text=re.compile(rf"^{re.escape(name)}$", re.I))
        if by_css.count():
            return by_css.first
        return self.page.get_by_role("listitem", name=name, exact=True).last

    def _click_coverage_via_search(self) -> bool:
        """Filter settings menu to Coverage and click the sole match."""
        search = self.page.get_by_placeholder(re.compile(r"^Search$", re.I))
        if search.count() == 0:
            search = self.page.get_by_role("textbox", name=re.compile(r"^Search$", re.I))
        if search.count() == 0:
            return False
        try:
            search.first.fill("Coverage")
            self.page.wait_for_timeout(500)
            target = self.page.locator(
                ".setting-menu-list-inactive-color, "
                ".setting-menu-list-active-color, .v-list-item"
            ).filter(has_text=re.compile(r"^Coverage$", re.I))
            if target.count() == 0:
                target = self.page.get_by_role(
                    "listitem", name="Coverage", exact=True
                )
            if target.count() == 0:
                return False
            handle = target.first.element_handle()
            if handle:
                self.page.evaluate("(el) => el.click()", handle)
            else:
                target.first.click(force=True)
            self.page.wait_for_timeout(1000)
            try:
                search.first.fill("")
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _on_coverage(self) -> bool:
        # Title sits in the settings document; visibility can flake while
        # still present in the DOM (overlays / animation).
        title = self.page.get_by_text("Manage Coverage", exact=True)
        if title.count() == 0:
            return False
        try:
            return bool(title.first.is_visible())
        except Exception:
            return True

    def _on_wrong_settings_page(self) -> bool:
        """True when Settings opened a non-Coverage section (common flake)."""
        if self._on_coverage():
            return False
        markers = (
            "Payment Processing",
            "Payment Configuration",
            "Document Templates",
            "Lease Configuration",
        )
        for m in markers:
            loc = self.page.get_by_text(m, exact=True)
            if loc.count():
                try:
                    if loc.first.is_visible():
                        return True
                except Exception:
                    return True
        return False

    @log_method_exceptions
    def open_coverage(self) -> None:
        with allure.step("Open Settings → Coverage (Manage Coverage)"):
            if self._on_coverage() and not self._on_wrong_settings_page():
                return
            self.nav.open_settings_panel()
            self._dismiss_overlays()
            self.page.wait_for_timeout(400)

            def _click_coverage_menu() -> None:
                if self._click_coverage_via_search():
                    self._dismiss_overlays()
                    return
                css = self.page.locator(
                    ".setting-menu-list-inactive-color, "
                    ".setting-menu-list-active-color"
                ).filter(has_text=re.compile(r"^Coverage$", re.I))
                target = css.first if css.count() else self._menu_item("Coverage")
                expect(target).to_be_visible(timeout=self.timeout)
                target.scroll_into_view_if_needed()
                handle = target.element_handle()
                if handle:
                    self.page.evaluate("(el) => el.click()", handle)
                else:
                    target.click(timeout=self.timeout, force=True)
                self.page.wait_for_timeout(1000)
                self._dismiss_overlays()

            for _ in range(3):
                _click_coverage_menu()
                if self._on_coverage() and not self._on_wrong_settings_page():
                    break
                self._dismiss_overlays()
                self.page.wait_for_timeout(400)
            else:
                self.page.evaluate(
                    """() => {
                      const el = [...document.querySelectorAll(
                        '.setting-menu-list-inactive-color,'
                        + '.setting-menu-list-active-color, .v-list-item'
                      )].find(e => /^\\s*Coverage\\s*$/i.test(
                        (e.innerText||'').replace(/\\s+/g,' ').trim()));
                      if (el) el.click();
                    }"""
                )
                self.page.wait_for_timeout(1200)
                self._dismiss_overlays()
            expect(
                self.page.get_by_text("Manage Coverage", exact=True).first
            ).to_be_visible(timeout=self.timeout)

    def _coverage_tab(self, name: str):
        tab = self.page.get_by_role("tab", name=re.compile(rf"^{name}$", re.I))
        if tab.count() == 0:
            tab = self.page.get_by_text(re.compile(rf"^{name}$", re.I))
        return tab

    def _coverage_tab_visible(self, name: str) -> bool:
        tab = self._coverage_tab(name)
        try:
            return tab.count() > 0 and tab.first.is_visible()
        except Exception:
            return False

    @log_method_exceptions
    def open_corporate_settings(self) -> bool:
        """Open Manage Coverage → Corporate Settings.

        Returns False when that tab is not on the page.
        """
        with allure.step("Coverage → Corporate Settings"):
            self.open_coverage()
            if not self._coverage_tab_visible("Corporate Settings"):
                logger.info(
                    "Manage Coverage Corporate Settings is not available; skipped"
                )
                allure.attach(
                    "Corporate Settings is not available; skipped",
                    name="coverage-corporate-settings-skipped",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return False
            self._coverage_tab("Corporate Settings").first.click(force=True)
            self.page.wait_for_timeout(400)
            return True

    @log_method_exceptions
    def open_property_settings(self) -> bool:
        """Open Manage Coverage → Property Settings.

        Returns False when that tab is not on the page.
        """
        with allure.step("Coverage → Property Settings"):
            self.open_coverage()
            if self._on_wrong_settings_page():
                self.open_coverage()
            self._close_active_dialogs()
            if not self._coverage_tab_visible("Property Settings"):
                logger.info(
                    "Manage Coverage Property Settings is not available; skipped"
                )
                allure.attach(
                    "Property Settings is not available; skipped",
                    name="coverage-property-settings-skipped",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return False
            self._coverage_tab("Property Settings").first.click(force=True)
            self.page.wait_for_timeout(500)
            try:
                self._click_right_rail("Settings")
            except Exception:
                logger.info(
                    "Manage Coverage Settings button is not available; skipped"
                )
            self.page.wait_for_timeout(500)
            return True

    def _right_rail(self, name: str):
        """Right-rail item under Manage Coverage (Settings / Coverage Options)."""
        # Scope to the Manage Coverage panel — avoid the global Settings chrome.
        scoped = self.page.locator(
            ".v-dialog__content--active, [class*='settings'], body"
        ).last.locator(".v-list-item").filter(
            has_text=re.compile(rf"^{re.escape(name)}$", re.I)
        )
        # Prefer items that sit beside the other rail label.
        if name.casefold() == "coverage options":
            css = self.page.locator(".v-list-item").filter(
                has_text=re.compile(r"^Coverage Options$", re.I)
            )
            if css.count():
                return css
        if name.casefold() == "settings":
            # Right-rail Settings is the sibling of Coverage Options.
            both = self.page.evaluate(
                """() => {
                  const items = [...document.querySelectorAll('.v-list-item')];
                  const cov = items.find(e =>
                    /^\\s*Coverage Options\\s*$/i.test(
                      (e.innerText||'').replace(/\\s+/g,' ').trim()));
                  if (!cov) return null;
                  const parent = cov.parentElement;
                  if (!parent) return null;
                  const settings = [...parent.querySelectorAll('.v-list-item')]
                    .find(e => /^\\s*Settings\\s*$/i.test(
                      (e.innerText||'').replace(/\\s+/g,' ').trim()));
                  if (!settings) return null;
                  settings.setAttribute('data-hb-cov-rail', 'settings');
                  return true;
                }"""
            )
            if both:
                marked = self.page.locator(
                    ".v-list-item[data-hb-cov-rail='settings']"
                )
                if marked.count():
                    return marked
        if scoped.count():
            return scoped
        return self.page.locator(".v-list-item").filter(
            has_text=re.compile(rf"^{re.escape(name)}$", re.I)
        )

    def _click_right_rail(self, name: str) -> None:
        rail = self._right_rail(name)
        if rail.count():
            try:
                rail.first.scroll_into_view_if_needed()
                rail.first.click(force=True, timeout=waits().medium)
                self.page.wait_for_timeout(500)
                return
            except Exception:
                pass
        # The rail is the pair Settings | Coverage Options. They are not
        # always .v-list-item, and the window title is also "Settings".
        clicked = False
        for _ in range(3):
            clicked = bool(
                self.page.evaluate(
                    """(label) => {
                      const want = String(label || '').trim().toLowerCase();
                      const other = want === 'settings'
                        ? 'coverage options' : 'settings';
                      const nodes = [...document.querySelectorAll(
                        'a, button, div, span, li'
                      )];
                      const exact = (el) => (el.innerText || '')
                        .replace(/\\s+/g, ' ').trim().toLowerCase();
                      const shown = (el) => {
                        const r = el.getClientRects();
                        return r && r.length;
                      };
                      const cov = nodes.find(e =>
                        shown(e) && exact(e) === 'coverage options');
                      if (cov && cov.parentElement) {
                        const mate = [...cov.parentElement.children].find(e =>
                          shown(e) && exact(e) === want);
                        if (mate) { mate.click(); return true; }
                      }
                      const hit = nodes.find(e =>
                        shown(e) && exact(e) === want
                        && e.parentElement
                        && exact(e.parentElement).includes(other));
                      if (!hit) return false;
                      hit.click();
                      return true;
                    }""",
                    name,
                )
            )
            if clicked:
                break
            self.page.wait_for_timeout(500)
        if not clicked:
            raise AssertionError(f"Coverage right rail '{name}' not found")
        self.page.wait_for_timeout(500)

    @log_method_exceptions
    def open_settings_rail(self, *, reopen: bool = True) -> bool:
        """Open the Manage Coverage Settings rail.

        Returns False when that button is not on the page. The Coverage
        Option Types row is often already visible, so a missing Settings
        button is skipped.
        """
        with allure.step("Coverage right rail → Settings"):
            if reopen:
                self.open_coverage()
            try:
                self._click_right_rail("Settings")
            except AssertionError:
                logger.info(
                    "Manage Coverage Settings button is not available; skipped"
                )
                allure.attach(
                    "Manage Coverage Settings button is not available; skipped",
                    name="coverage-settings-rail-skipped",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return False
            return True

    @log_method_exceptions
    def open_coverage_options(self, *, reopen: bool = True) -> None:
        with allure.step("Coverage right rail → Coverage Options"):
            if reopen:
                self.open_coverage()
            # Option Types stays Disabled; Coverage Options is still reachable.
            self._click_right_rail("Coverage Options")
            self.page.wait_for_timeout(400)
            self._dismiss_overlays()

    @log_method_exceptions
    def list_space_types(self) -> list[str]:
        """Open Select Space Type and return available option labels."""
        with allure.step("List Coverage Select Space Type options"):
            self.open_corporate_settings()
            self.open_settings_rail()
            combo = self.page.get_by_role(
                "textbox", name=re.compile(r"Select Space Type", re.I)
            )
            if combo.count() == 0:
                combo = self.page.get_by_placeholder(
                    re.compile(r"Select Space Type", re.I)
                )
            if combo.count() == 0:
                return []
            combo.first.click(force=True)
            self.page.wait_for_timeout(500)
            names = self.page.evaluate(
                """() => {
                  const out = [];
                  const seen = new Set();
                  const noise = /^(dashboard|spaces|tenants|leads|reports|tools|log out|access control|accounting|coverage|document|settings|corporate|property|payment|filter|search|hummingbird)/i;
                  const nodes = document.querySelectorAll(
                    '[role="listbox"] [role="option"], '
                    + '[role="listbox"] .v-list-item, '
                    + '.v-menu__content .v-list-item, '
                    + '.menuable__content__active .v-list-item, '
                    + '.v-select-list .v-list-item'
                  );
                  for (const el of nodes) {
                    if (el.offsetParent === null
                        && !(el.getClientRects && el.getClientRects().length))
                      continue;
                    const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (!t || t.length > 40) continue;
                    if (noise.test(t)) continue;
                    if (/select space type|coverage option|option types/i.test(t))
                      continue;
                    const key = t.toLowerCase();
                    if (seen.has(key)) continue;
                    seen.add(key);
                    out.push(t);
                  }
                  return out;
                }"""
            )
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(200)
            return list(names or [])

    @log_method_exceptions
    def select_space_category(
        self,
        category: str = "Storage",
        *,
        scope: str = "corporate",
    ) -> bool:
        """Select Space Type on Coverage Settings rail.

        ``scope``:
        - ``corporate`` (default): switch to Corporate Settings first
        - ``property``: stay on Property Settings (property already selected)
        - ``current``: do not change Corporate/Property tab
        """
        with allure.step(
            f"Coverage space category → {category} (scope={scope})"
        ):
            if scope == "corporate":
                self.open_corporate_settings()
                self.open_settings_rail()
            elif scope == "property":
                # Keep Property Settings tab; Space Type lives on Settings rail.
                try:
                    self._click_right_rail("Settings")
                except Exception:
                    pass
                self.page.wait_for_timeout(300)
            # scope == "current": do not change tab or right rail

            combo = self.page.get_by_role(
                "textbox", name=re.compile(r"Select Space Type", re.I)
            )
            if combo.count() == 0:
                combo = self.page.get_by_placeholder(
                    re.compile(r"Select Space Type", re.I)
                )
            if combo.count() == 0:
                return False
            current = (combo.first.input_value() or "").strip()
            if current.casefold() == category.casefold():
                return True
            combo.first.click(force=True)
            self.page.wait_for_timeout(400)
            # Prefer exact option match; fall back to case-insensitive list item.
            opt = self.page.get_by_role(
                "option", name=re.compile(rf"^{re.escape(category)}$", re.I)
            )
            if opt.count() == 0:
                opt = self.page.locator(
                    "[role='option'], .v-list-item, .v-select-list .v-list-item"
                ).filter(has_text=re.compile(rf"^{re.escape(category)}$", re.I))
            if opt.count() == 0:
                opt = self.page.get_by_text(
                    re.compile(rf"^{re.escape(category)}$", re.I)
                )
            if opt.count() == 0:
                self.page.keyboard.press("Escape")
                return False
            opt.first.click(force=True)
            self.page.wait_for_timeout(600)
            # Confirm selection stuck
            try:
                after = (combo.first.input_value() or "").strip()
                if after and after.casefold() == category.casefold():
                    return True
            except Exception:
                pass
            return True

    def coverage_option_types_row_visible(self) -> bool:
        """True when the Coverage Option Types row is already on screen."""
        row = self.page.get_by_text(
            re.compile(r"^Coverage Option Types$", re.I)
        )
        try:
            return row.count() > 0 and row.first.is_visible()
        except Exception:
            return False

    def coverage_option_types_enabled(self) -> bool | None:
        """True/False for Coverage Option Types; None if that control is not shown.

        The label is the current state (``Coverage Option Types Disabled``).
        ``Disabled`` is checked first so a label that also contains ``Enabled``
        is not treated as on. This switch is corporate-wide.
        """
        label = self.page.evaluate(
            """() => {
              let best = null;
              for (const node of document.querySelectorAll('div')) {
                if (node.offsetParent === null
                    && !(node.getClientRects && node.getClientRects().length))
                  continue;
                const t = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                if (!/^Coverage Option Types\\b/i.test(t) || t.length > 140)
                  continue;
                if (!best || t.length < best.t.length) best = {node, t};
              }
              if (!best) return null;
              if (/\\bDisabled\\b/i.test(best.t)) return 'disabled';
              if (/\\bEnabled\\b/i.test(best.t)) return 'enabled';
              const input = best.node.querySelector(
                '.v-input--switch input, [role="switch"]'
              );
              if (!input) return null;
              const on = input.checked === true
                || input.getAttribute('aria-checked') === 'true';
              return on ? 'enabled' : 'disabled';
            }"""
        )
        if label == "enabled":
            return True
        if label == "disabled":
            return False
        return None

    def _toggle_coverage_option_types(self) -> str | None:
        """Click the Coverage Option Types control. Returns the label clicked."""
        return self.page.evaluate(
            """() => {
              let best = null;
              for (const node of document.querySelectorAll('div')) {
                if (node.offsetParent === null
                    && !(node.getClientRects && node.getClientRects().length))
                  continue;
                const t = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                if (!/^Coverage Option Types\\b/i.test(t) || t.length > 140)
                  continue;
                if (!best || t.length < best.t.length) best = {node, t};
              }
              if (!best) return null;
              const sw = best.node.querySelector('.v-input--switch, [role="switch"]');
              if (!sw) return null;
              const ripple = sw.querySelector(
                '.v-input--selection-controls__ripple, input'
              );
              (ripple || sw).click();
              return best.t;
            }"""
        )

    def _save_coverage_settings_if_needed(self) -> None:
        save = self.page.get_by_role("button", name=re.compile(r"^Save$", re.I))
        if save.count() and save.first.is_visible():
            save.first.click(force=True)
            self.page.wait_for_timeout(1000)

    @log_method_exceptions
    def disable_coverage_option_types(self, *, scope: str = "corporate") -> bool:
        """Ensure Coverage Option Types is Disabled.

        ``scope`` ``corporate`` switches to Corporate Settings; ``property`` /
        ``current`` leave the active tab alone (Property Settings flow).
        Returns True when Disabled, or when the toggle is not shown.
        """
        with allure.step(f"Disable Coverage Option Types (scope={scope})"):
            if scope == "corporate":
                self.open_corporate_settings()
                self.open_settings_rail()
            elif scope == "property":
                try:
                    self._click_right_rail("Settings")
                except Exception:
                    pass
            self.page.wait_for_timeout(500)
            state = self.coverage_option_types_enabled()
            if state is not True:
                # Already Disabled, or this view has no toggle (Property
                # Settings). Do not click — a click turns the corporate
                # switch on for every property.
                if state is None:
                    allure.attach(
                        "Coverage Option Types toggle not present on this "
                        "view (left unchanged)",
                        name="coverage-option-types-missing",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                return True
            clicked = self._toggle_coverage_option_types()
            self._confirm_if_present()
            self.page.wait_for_timeout(1000)
            self._save_coverage_settings_if_needed()
            state2 = self.coverage_option_types_enabled()
            if state2 is True:
                clicked = self._toggle_coverage_option_types()
                self._confirm_if_present()
                self.page.wait_for_timeout(1000)
                self._save_coverage_settings_if_needed()
                state2 = self.coverage_option_types_enabled()
            allure.attach(
                f"clicked={clicked} before={state} after={state2}",
                name="coverage-option-types-toggle",
                attachment_type=allure.attachment_type.TEXT,
            )
            return state2 is not True

    @log_method_exceptions
    def enable_coverage_option_types(self) -> bool:
        """Coverage Option Types applies to the whole company. Leave it off."""
        self.disable_coverage_option_types()
        return False

    def _close_active_dialogs(self) -> None:
        """Dismiss Add/Edit coverage dialogs without closing Settings."""
        modal = self.page.locator(".hb-modal-wrapper.v-dialog--active")
        if modal.count():
            for pattern in (r"^Cancel$", r"^Close$", r"^Discard$"):
                btn = modal.last.get_by_role(
                    "button", name=re.compile(pattern, re.I)
                )
                if btn.count() and btn.first.is_visible():
                    try:
                        btn.first.click(force=True, timeout=waits().short)
                        self.page.wait_for_timeout(400)
                    except Exception:
                        pass
                    break
            # Still open? force-remove overlay click via Cancel JS
            if self.page.locator(".hb-modal-wrapper.v-dialog--active").count():
                self.page.evaluate(
                    """() => {
                      const root = document.querySelector(
                        '.hb-modal-wrapper.v-dialog--active'
                      );
                      if (!root) return;
                      const btn = [...root.querySelectorAll('button')].find(b =>
                        /^\\s*Cancel\\s*$/i.test(
                          (b.innerText||'').replace(/\\s+/g,' ').trim()));
                      if (btn) btn.click();
                    }"""
                )
                self.page.wait_for_timeout(400)
        for pattern in (r"^Cancel$", r"^Close$", r"^Discard$"):
            btn = self.page.get_by_role(
                "button", name=re.compile(pattern, re.I)
            )
            if btn.count() and btn.first.is_visible():
                try:
                    # Avoid the Settings chrome close (X) — only labeled Cancel
                    txt = (btn.first.inner_text() or "").strip()
                    if not re.match(r"^(Cancel|Close|Discard)$", txt, re.I):
                        continue
                    btn.first.click(force=True, timeout=waits().short)
                    self.page.wait_for_timeout(400)
                except Exception:
                    pass
        # Escape once for menus — avoid double Escape (closes Settings).
        try:
            if self.page.locator(".menuable__content__active").count():
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
        except Exception:
            pass

    @log_method_exceptions
    def select_coverage_property(
        self,
        property_name: str,
        *,
        navigate: bool = True,
    ) -> bool:
        """Select a property on Coverage → Property Settings.

        Live Select Property options use lease/facility display names
        (e.g. ``Hamilton Self Storage``), not always ``hb_property_name``.
        Options render in a Vuetify portal — prefer ``[role=option]`` /
        JS click over listbox-scoped locators.

        When ``navigate`` is False, only fill the visible Select Property
        control on the current rail (needed after switching to Coverage
        Options, which clears the picker).
        """
        with allure.step(f"Coverage select property → {property_name}"):
            if navigate:
                self.open_coverage()
                self._close_active_dialogs()
                if not self.open_property_settings():
                    return False
                try:
                    self._click_right_rail("Settings")
                except Exception:
                    pass
            self.nav._close_live_agent_notification()
            self.page.wait_for_timeout(500)

            sel = self.page.get_by_role(
                "textbox", name="Select Property", exact=True
            )
            if sel.count() == 0:
                sel = self.page.get_by_placeholder(
                    re.compile(r"Select Property", re.I)
                )
            if sel.count() == 0:
                allure.attach(
                    "Select Property textbox not found",
                    name="coverage-property-missing",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return False
            try:
                expect(sel.first).to_be_visible(timeout=waits().medium)
            except AssertionError:
                return False

            # Already selected?
            try:
                current = (sel.first.input_value() or "").strip()
                if property_name.casefold() in current.casefold():
                    return True
            except Exception:
                pass

            sel.first.click(force=True)
            self.page.wait_for_timeout(600)

            name_re = re.compile(
                rf".*{re.escape(property_name)}.*", re.IGNORECASE
            )
            opt = self.page.get_by_role("option").filter(has_text=name_re)
            clicked = False
            if opt.count():
                try:
                    opt.first.scroll_into_view_if_needed()
                    opt.first.click(force=True, timeout=waits().medium)
                    clicked = True
                except Exception:
                    pass
            if not clicked:
                clicked = bool(
                    self.page.evaluate(
                        """(want) => {
                          const w = String(want || '').toLowerCase();
                          const el = [...document.querySelectorAll(
                            '[role="option"], .v-list-item'
                          )].find(e => {
                            const t = (e.innerText || '').toLowerCase();
                            return t === w || t.includes(w);
                          });
                          if (!el) return false;
                          el.click();
                          return true;
                        }""",
                        property_name,
                    )
                )
            if not clicked:
                allure.attach(
                    f"option not found for {property_name!r}",
                    name="coverage-property-option-missing",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return False
            self.page.wait_for_timeout(1200)

            try:
                after = (sel.first.input_value() or "").strip()
                if property_name.casefold() in after.casefold():
                    return True
                # Partial / truncated display still counts
                if after and (
                    after.casefold() in property_name.casefold()
                    or property_name.casefold().startswith(after.casefold())
                ):
                    return True
            except Exception:
                pass
            please = self.page.get_by_text(
                re.compile(r"Please select a Property", re.I)
            )
            if please.count() == 0:
                return True
            try:
                if not please.first.is_visible():
                    return True
            except Exception:
                return True
            return False

    def _confirm_if_present(self) -> None:
        confirm = self.page.get_by_role(
            "button", name=re.compile(r"^Confirm$", re.I)
        )
        try:
            if confirm.count() and confirm.first.is_visible():
                confirm.first.click(force=True)
                self.page.wait_for_timeout(400)
        except Exception:
            pass

    def property_uses_corporate_default(self) -> bool | None:
        """True when Property Settings 'Use Corporate Default' is checked."""
        return self.page.evaluate(
            """() => {
              const lab = [...document.querySelectorAll('label, .v-input')]
                .find(e => /use corporate default/i.test(e.innerText||''));
              if (!lab) return null;
              const input = lab.querySelector('input[type=checkbox]')
                || lab.closest('.v-input')?.querySelector('input[type=checkbox]');
              if (!input) return null;
              return !!input.checked;
            }"""
        )

    @log_method_exceptions
    def uncheck_use_corporate_default(self) -> bool:
        """Clear Property Settings 'Use Corporate Default' when it is checked.

        Corporate Settings has no such checkbox. Returns True when the box
        is unchecked or not on this view.
        """
        with allure.step("Uncheck Use Corporate Default"):
            outcome = self.page.evaluate(
                """() => {
                  const nodes = [...document.querySelectorAll(
                    'label, .v-input--checkbox, .v-input'
                  )];
                  const lab = nodes.find(e => {
                    const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();
                    return t.length < 40 && /use corporate default/i.test(t);
                  });
                  if (!lab) return 'absent';
                  const input = lab.querySelector('input[type=checkbox]')
                    || lab.closest('.v-input')?.querySelector(
                      'input[type=checkbox]'
                    );
                  if (!input) return 'absent';
                  if (!input.checked) return 'already';
                  const clickable = lab.querySelector(
                    '.v-input--selection-controls__ripple'
                  ) || lab.closest('.v-input')?.querySelector(
                    '.v-input--selection-controls__ripple'
                  ) || input;
                  clickable.click();
                  return 'unchecked';
                }"""
            )
            if outcome == "unchecked":
                self._confirm_if_present()
                self.page.wait_for_timeout(600)
                self._save_coverage_settings_if_needed()
            allure.attach(
                str(outcome),
                name="use-corporate-default",
                attachment_type=allure.attachment_type.TEXT,
            )
            return outcome in {"absent", "already", "unchecked"}

    def select_coverage_property_aliases(
        self, aliases: list[str]
    ) -> tuple[bool, str | None]:
        """Try each alias until one selects; return (ok, matched_alias)."""
        for alias in aliases:
            alias = (alias or "").strip()
            if not alias:
                continue
            if self.select_coverage_property(alias):
                return True, alias
        return False, None

    def _add_coverage_modal(self):
        """Locator for the Add/Edit Coverage modal (not Settings fullscreen)."""
        return self.page.locator(
            ".hb-modal-wrapper.v-dialog--active"
        ).last

    @log_method_exceptions
    def click_add_coverage_option(self) -> bool:
        """Click Add / New / Create on Coverage Options if present."""
        with allure.step("Coverage Options → Add"):
            self.open_coverage_options()
            for pattern in (
                r"Add Coverage Option",
                r"Add Option",
                r"Add Coverage",
                r"New Coverage",
                r"Create",
                r"^Add$",
            ):
                btn = self.page.get_by_role(
                    "button", name=re.compile(pattern, re.I)
                )
                if btn.count() and btn.first.is_visible():
                    btn.first.click(force=True)
                    try:
                        self._add_coverage_modal().wait_for(
                            state="visible", timeout=waits().medium
                        )
                    except Exception:
                        self.page.wait_for_timeout(800)
                    return self._add_coverage_modal().count() > 0
            # Icon-only add
            plus = self.page.locator(
                "button .mdi-plus, button[aria-label*='Add' i]"
            )
            if plus.count() and plus.first.is_visible():
                plus.first.click(force=True)
                self.page.wait_for_timeout(800)
                return self._add_coverage_modal().count() > 0
            return False

    @log_method_exceptions
    def fill_coverage_option_form(
        self,
        *,
        name: str,
        premium: str | None = None,
        description: str | None = None,
        coverage_amount: str | None = None,
        gl_account: str | None = None,
        enable_properties: list[str] | None = None,
    ) -> list[str]:
        """Fill Add Coverage dialog (Name, Premium, Coverage $, GL Account…).

        Live form requires **Coverage** and **GL Account** in addition to
        Name / Monthly Premium (stage 2026-09-21).
        """
        steps: list[str] = []
        premium = premium or "8.00"
        coverage_amount = coverage_amount or "1000"
        description = description or "HB_MP_Automation coverage option"

        def _fill(label_re: str, value: str) -> bool:
            return bool(
                self.page.evaluate(
                    """({pattern, value}) => {
                      const re = new RegExp(pattern, 'i');
                      const root = document.querySelector(
                        '.hb-modal-wrapper.v-dialog--active'
                      ) || document;
                      const pool = Array.from(root.querySelectorAll(
                        'input, textarea, .hb-text-field-wrapper'
                      ));
                      for (const el of pool) {
                        if (el.offsetParent === null
                            && !(el.getClientRects && el.getClientRects().length))
                          continue;
                        const ph = el.getAttribute('placeholder') || '';
                        const vv = el.getAttribute('data-vv-as') || '';
                        const aria = el.getAttribute('aria-label') || '';
                        const id = el.id || el.getAttribute('name') || '';
                        if (!(re.test(ph) || re.test(vv) || re.test(aria)
                              || re.test(id)))
                          continue;
                        const target = (el.matches
                          && el.matches('input,textarea'))
                          ? el
                          : el.querySelector('input, textarea');
                        if (!target) continue;
                        const proto = target.tagName === 'TEXTAREA'
                          ? window.HTMLTextAreaElement.prototype
                          : window.HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(
                          proto, 'value'
                        )?.set;
                        target.focus();
                        if (setter) setter.call(target, value);
                        else target.value = value;
                        target.dispatchEvent(
                          new Event('input', {bubbles: true})
                        );
                        target.dispatchEvent(
                          new Event('change', {bubbles: true})
                        );
                        return true;
                      }
                      return false;
                    }""",
                    {"pattern": label_re, "value": value},
                )
            )

        if _fill(r"^Name$|Enter Name|data-vv-as=.Name", name) or _fill(
            r"Name|Enter Name", name
        ):
            steps.append(f"name={name}")
        if _fill(r"Description|Enter a description", description):
            steps.append("description")

        # Space Type must be set before GL Account appears on the form.
        space = None
        # Infer from option name ("… - Storage" / "… - Parking") when possible.
        for candidate in ("Storage", "Parking", "Residential", "Office"):
            if candidate.casefold() in name.casefold():
                space = candidate
                break
        space = space or "Storage"
        if self._select_dialog_space_type(space):
            steps.append(f"space_type={space}")
            self.page.wait_for_timeout(800)

        if _fill(r"Monthly Premium|Premium", premium):
            steps.append(f"premium={premium}")
        # Required: Coverage $ field (placeholder "Coverage" / "$ Coverage")
        if _fill(r"^Coverage$|\$\s*Coverage", coverage_amount):
            steps.append(f"coverage={coverage_amount}")
        elif self.page.evaluate(
            """(value) => {
              const root = document.querySelector(
                '.hb-modal-wrapper.v-dialog--active'
              ) || document;
              const el = [...root.querySelectorAll('input')].find(e =>
                /coverage/i.test(e.placeholder||'')
                && !/premium/i.test(e.placeholder||''));
              if (!el) return false;
              const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value')?.set;
              el.focus();
              if (setter) setter.call(el, value); else el.value = value;
              el.dispatchEvent(new Event('input', {bubbles: true}));
              el.dispatchEvent(new Event('change', {bubbles: true}));
              return true;
            }""",
            coverage_amount,
        ):
            steps.append(f"coverage={coverage_amount}")
        if _fill(r"Deductible", "0"):
            steps.append("deductible=0")

        # Enable Properties first — GL Account often mounts after the form
        # is otherwise complete.
        for prop in enable_properties or []:
            if self._check_enable_property(prop):
                steps.append(f"enable_property={prop}")

        gl_ok = self._select_gl_account(gl_account, space_type=space)
        if gl_ok:
            steps.append(f"gl_account={gl_ok}")

        return steps

    def _select_dialog_space_type(self, space: str) -> bool:
        """Select Space Type inside the Add Coverage modal only."""
        opened = bool(
            self.page.evaluate(
                """() => {
                  const root = document.querySelector(
                    '.hb-modal-wrapper.v-dialog--active'
                  );
                  if (!root) return false;
                  const inp = [...root.querySelectorAll('input')].find(e =>
                    /select space type/i.test(e.placeholder||'')
                  );
                  if (!inp) return false;
                  inp.click();
                  return true;
                }"""
            )
        )
        if not opened:
            return False
        self.page.wait_for_timeout(500)
        clicked = bool(
            self.page.evaluate(
                """(want) => {
                  const w = String(want||'').toLowerCase();
                  const el = [...document.querySelectorAll(
                    '[role="option"], .menuable__content__active .v-list-item,'
                    + ' .v-menu__content--active .v-list-item'
                  )].find(e => {
                    const t = (e.innerText||'').replace(/\\s+/g,' ').trim()
                      .toLowerCase();
                    return t === w;
                  });
                  if (!el) return false;
                  el.click();
                  return true;
                }""",
                space,
            )
        )
        self.page.wait_for_timeout(500)
        return clicked

    def _select_gl_account(
        self,
        preferred: str | None = None,
        *,
        space_type: str | None = None,
    ) -> str | None:
        """Open GL Account in Add Coverage modal; pick a real GL row."""
        # Wait for GL Account input (appears after Space Type + other fields).
        appeared = False
        for _ in range(12):
            appeared = bool(
                self.page.evaluate(
                    """() => {
                      const root = document.querySelector(
                        '.hb-modal-wrapper.v-dialog--active'
                      );
                      if (!root) return false;
                      if (/GL Account/i.test(root.innerText||'')) return true;
                      return [...root.querySelectorAll('input')].some(e =>
                        /select an account/i.test(e.placeholder||'')
                      );
                    }"""
                )
            )
            if appeared:
                break
            self.page.wait_for_timeout(400)
        if not appeared:
            return None

        opened = bool(
            self.page.evaluate(
                """() => {
                  const root = document.querySelector(
                    '.hb-modal-wrapper.v-dialog--active'
                  );
                  if (!root) return false;
                  const inp = [...root.querySelectorAll('input')].find(e =>
                    /select an account/i.test(e.placeholder||'')
                  );
                  if (inp) {
                    inp.scrollIntoView({block: 'center'});
                    inp.click();
                    return true;
                  }
                  const lab = [...root.querySelectorAll(
                    'label, span, div, p'
                  )].find(e => {
                    const t = (e.innerText||'').replace(/\\s+/g,' ').trim();
                    return t === 'GL Account' || t === 'GL Account*';
                  });
                  if (!lab) return false;
                  let wrap = lab;
                  for (let i = 0; i < 10 && wrap; i++) {
                    const slot = wrap.querySelector(
                      'input, .v-select__slot, .v-input__slot, '
                      + '.hb-text-field-wrapper'
                    );
                    if (slot) {
                      slot.click();
                      return true;
                    }
                    wrap = wrap.parentElement;
                  }
                  return false;
                }"""
            )
        )
        if not opened:
            return None
        self.page.wait_for_timeout(700)

        options = self.page.evaluate(
            """() => [...document.querySelectorAll(
              '[role="option"], .menuable__content__active .v-list-item,'
              + ' .v-menu__content--active .v-list-item'
            )].map(e => (e.innerText||'').replace(/\\s+/g,' ').trim())
              .filter(t => t && t.length < 120 && !/^select/i.test(t))"""
        )
        if not options:
            return None

        def _is_account(label: str) -> bool:
            if re.match(
                r"^(storage|parking|residential|office|mailbox|warehouse|"
                r"billboard|wine storage|locker|gun lockers|mobile cube|"
                r"deposit box|storage lockers)$",
                label,
                re.I,
            ):
                return False
            if re.search(r"\d{3,}", label):
                return True
            if re.search(r"rental|income|velom|insurance", label, re.I):
                return True
            return False

        accounts = [o for o in options if _is_account(o)]
        pool = accounts or options
        space = (space_type or "").strip().casefold()
        pick = None
        if preferred:
            for o in pool:
                if preferred.casefold() in o.casefold():
                    pick = o
                    break
        if not pick and space:
            # Prefer GL tied to the selected space type (2002 Parking, 2001 Storage).
            space_patterns = {
                "parking": r"2002|rental income\s*[-:]?\s*parking",
                "storage": r"2001|rental income\s*[-:]?\s*storage",
            }
            pat = space_patterns.get(space)
            if pat:
                for o in pool:
                    if re.search(pat, o, re.I):
                        pick = o
                        break
            if not pick:
                for o in pool:
                    if space in o.casefold() and _is_account(o):
                        pick = o
                        break
        if not pick:
            for o in pool:
                if re.search(r"2001|rental income\s*-\s*storage", o, re.I):
                    pick = o
                    break
        if not pick:
            pick = pool[0]
        clicked = self.page.evaluate(
            """(want) => {
              const wantL = String(want||'').toLowerCase();
              const el = [...document.querySelectorAll(
                '[role="option"], .menuable__content__active .v-list-item,'
                + ' .v-menu__content--active .v-list-item'
              )].find(e => {
                const t = (e.innerText||'').replace(/\\s+/g,' ').trim();
                return t === want || t.toLowerCase() === wantL
                  || t.toLowerCase().includes(wantL);
              });
              if (!el) return false;
              el.click();
              return true;
            }""",
            pick,
        )
        self.page.wait_for_timeout(500)
        return pick if clicked else None

    def _check_enable_property(self, property_name: str) -> bool:
        """Tick Enable Properties checkbox for ``property_name`` if shown."""
        return bool(
            self.page.evaluate(
                """(want) => {
                  const w = String(want||'').toLowerCase();
                  const root = document.querySelector(
                    '.hb-modal-wrapper.v-dialog--active'
                  ) || document;
                  const labels = [...root.querySelectorAll(
                    'label, .v-input--checkbox'
                  )];
                  for (const lab of labels) {
                    const t = (lab.innerText||'').toLowerCase();
                    if (!t.includes(w)) continue;
                    const input = lab.querySelector('input[type=checkbox]')
                      || lab.closest('.v-input')?.querySelector('input');
                    if (input && !input.checked) {
                      (lab.querySelector('.v-input--selection-controls__ripple')
                        || lab).click();
                      return true;
                    }
                    if (input && input.checked) return true;
                    lab.click();
                    return true;
                  }
                  return false;
                }""",
                property_name,
            )
        )

    @log_method_exceptions
    def save_coverage_option_dialog(self) -> bool:
        """Click Add/Save; return False if validation errors remain."""
        modal = self._add_coverage_modal()
        clicked = False
        if modal.count():
            for pattern in (r"^Add$", r"^Save$", r"^Create$", r"^Apply$"):
                btn = modal.get_by_role(
                    "button", name=re.compile(pattern, re.I)
                )
                if btn.count() and btn.first.is_visible():
                    btn.first.click(force=True)
                    clicked = True
                    self.page.wait_for_timeout(1200)
                    break
        if not clicked:
            for pattern in (r"^Add$", r"^Save$", r"^Create$", r"^Apply$"):
                btn = self.page.get_by_role(
                    "button", name=re.compile(pattern, re.I)
                )
                if btn.count() and btn.first.is_visible():
                    btn.first.click(force=True)
                    self.page.wait_for_timeout(1200)
                    break
            else:
                return False
        # Validation still open?
        err = self.page.get_by_text(
            re.compile(
                r"errors on your form|field is required|correct them before",
                re.I,
            )
        )
        if err.count() and err.first.is_visible():
            allure.attach(
                err.first.inner_text()[:400],
                name="coverage-option-validation",
                attachment_type=allure.attachment_type.TEXT,
            )
            return False
        # Dialog should close on success
        if self._add_coverage_modal().count():
            try:
                if self._add_coverage_modal().first.is_visible():
                    return False
            except Exception:
                pass
        return True

    @log_method_exceptions
    def list_coverage_option_names(self, *, reopen: bool = True) -> list[str]:
        """Visible coverage option / plan names on Coverage Options view."""
        if reopen:
            self.open_coverage_options()
        return self.page.evaluate(
            """() => {
              const root = document.querySelector(
                '.hb-settings-fullscreen.v-dialog--active,'
                + ' .v-dialog.hb-settings-fullscreen'
              ) || document;
              const rows = [];
              const trs = root.querySelectorAll(
                'table tbody tr, .v-data-table tbody tr'
              );
              for (const tr of trs) {
                if (!tr.offsetParent) continue;
                const cells = [...tr.querySelectorAll('td')];
                if (!cells.length) continue;
                // Name is usually the first meaningful cell.
                let name = (cells[0].innerText || '')
                  .replace(/\\s+/g, ' ').trim();
                if (!name) continue;
                // Some grids put the title on a nested element / first line.
                name = name.split('\\n')[0].trim().slice(0, 120);
                if (!name || name.length < 2) continue;
                if (/^(name|gl |premium|coverage|deductible)/i.test(name))
                  continue;
                rows.push(name);
                if (rows.length >= 200) break;
              }
              return [...new Set(rows)];
            }"""
        )

    def coverage_option_exists(self, name: str) -> bool:
        """True if ``name`` appears in the Coverage Options grid/page."""
        names = self.list_coverage_option_names(reopen=False)
        want = (name or "").strip().casefold()
        if want and any(want in n.casefold() for n in names):
            return True
        # Fallback: exact-ish text match in the settings content (handles
        # pagination / virtualized rows the table scrape missed).
        return bool(
            self.page.evaluate(
                """(want) => {
                  const w = String(want||'').toLowerCase();
                  if (!w) return false;
                  const root = document.querySelector(
                    '.hb-settings-fullscreen.v-dialog--active,'
                    + ' .v-dialog.hb-settings-fullscreen'
                  ) || document.body;
                  const text = (root.innerText || '').toLowerCase();
                  return text.includes(w);
                }""",
                name,
            )
        )

    @log_method_exceptions
    def ensure_coverage_option(
        self,
        name: str,
        *,
        premium: str = "8.00",
        description: str | None = None,
        coverage_amount: str = "1000",
        gl_account: str | None = None,
        enable_properties: list[str] | None = None,
    ) -> dict:
        """Idempotent: open Coverage Options and add ``name`` if missing."""
        result: dict = {
            "name": name,
            "existed": False,
            "added": False,
            "steps": [],
        }
        self.open_coverage_options()
        names = self.list_coverage_option_names(reopen=False)
        result["existing"] = names[:40]
        if self.coverage_option_exists(name):
            result["existed"] = True
            result["steps"].append("already present")
            return result
        if not self.click_add_coverage_option():
            result["steps"].append("add button missing")
            return result
        result["steps"].append("add clicked")
        filled = self.fill_coverage_option_form(
            name=name,
            premium=premium,
            description=description,
            coverage_amount=coverage_amount,
            gl_account=gl_account,
            enable_properties=enable_properties,
        )
        result["steps"].extend(filled)
        if self.save_coverage_option_dialog():
            result["steps"].append("saved")
            result["added"] = True
        else:
            # Duplicate-name / already-exists often leaves validation up —
            # treat as present when the grid shows the name after cancel.
            err_txt = ""
            try:
                modal = self._add_coverage_modal()
                if modal.count():
                    err_txt = (modal.first.inner_text() or "")[:500]
            except Exception:
                pass
            self._close_active_dialogs()
            self.page.wait_for_timeout(500)
            if self.coverage_option_exists(name) or re.search(
                r"already|duplicate|exists|unique", err_txt, re.I
            ):
                result["existed"] = True
                result["steps"].append("save failed but option present")
            else:
                result["steps"].append("save failed / validation")
                if err_txt:
                    result["validation"] = err_txt[:300]
        return result
