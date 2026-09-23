"""HB Settings → Document Templates (corporate template library).

Live structure (stage 2026-09-20):
- Settings menu item **Document Templates**
- Tabs: Corporate Settings | Property Settings
- List: Name | Type | Signed | # of Properties | Created | Last Modified
- Editor: TinyMCE ``#editor_primary`` / ``.mce-content-body``
- Tokens: **Merge Fields** sidebar (Search Merge Fields → click name);
  render as blue pills like ``[Total Move-In Cost]``
- Persist with **Save Template**; dismiss with Cancel or close X
"""
from __future__ import annotations

import re
from pathlib import Path

import allure
from playwright.sync_api import Page, expect

from common_utils.waits import waits
from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation


class HBDocumentTemplatesPage:
    """Corporate Document Templates list + TinyMCE editor."""

    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav

    def _norm(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip())

    @log_method_exceptions
    def open_document_templates(self) -> None:
        with allure.step("Open Settings → Document Templates"):
            self.close_editor()
            if self._on_list():
                return
            self.nav.open_settings_panel()
            items = self.page.locator(
                ".setting-menu-list-inactive-color, .setting-menu-list-active-color"
            )
            target = items.filter(
                has_text=re.compile(r"^Document Templates$", re.I)
            ).first
            expect(target).to_be_visible(timeout=self.timeout)
            target.click(timeout=self.timeout)
            expect(
                self.page.get_by_role(
                    "button", name=re.compile(r"Create New Template", re.I)
                )
            ).to_be_visible(timeout=self.timeout)

    def _on_list(self) -> bool:
        create = self.page.get_by_role(
            "button", name=re.compile(r"Create New Template", re.I)
        )
        return create.count() > 0 and create.first.is_visible()

    @log_method_exceptions
    def close_editor(self) -> None:
        """Leave TinyMCE / create wizard so list clicks are not intercepted."""
        try:
            if self.page.is_closed():
                return
        except Exception:
            return
        try:
            for label in ("Cancel", "Close", "Discard"):
                btn = self.page.get_by_role(
                    "button", name=re.compile(rf"^{re.escape(label)}$", re.I)
                )
                if btn.count() and btn.first.is_visible():
                    try:
                        btn.first.click(timeout=waits().short, force=True)
                        self.page.wait_for_timeout(400)
                    except Exception:
                        pass
            close_x = self.page.locator(
                'button[name="QA-v-card-HbIcon-mdi-close"], '
                'button[aria-label="Close"]'
            )
            header_close = self.page.locator(
                ".v-toolbar button, .v-card button"
            ).filter(has=self.page.locator(".mdi-close"))
            for loc in (close_x, header_close):
                if loc.count() and loc.first.is_visible():
                    try:
                        loc.first.click(timeout=waits().short, force=True)
                        self.page.wait_for_timeout(300)
                    except Exception:
                        pass
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(200)
        except Exception:
            # Page/context may have been closed mid-flow (manual close / crash).
            return

    @log_method_exceptions
    def search(self, text: str) -> None:
        box = self.page.get_by_placeholder(re.compile(r"search", re.I))
        if box.count() == 0:
            return
        box.first.fill(text)
        self.page.wait_for_timeout(500)

    @log_method_exceptions
    def list_rows(self) -> list[dict[str, str]]:
        self.open_document_templates()
        table = self.page.locator("table").first
        expect(table).to_be_visible(timeout=self.timeout)
        rows: list[dict[str, str]] = []
        body = table.locator("tbody tr")
        for i in range(min(body.count(), 200)):
            cells = [
                self._norm(c) for c in body.nth(i).locator("td").all_inner_texts()
            ]
            if len(cells) < 2:
                continue
            rows.append(
                {
                    "name": cells[0],
                    "type": cells[1],
                    "signed": cells[2] if len(cells) > 2 else "",
                    "properties": cells[3] if len(cells) > 3 else "",
                }
            )
        return rows

    @log_method_exceptions
    def template_exists(self, name: str) -> bool:
        self.open_document_templates()
        self.search(name)
        row = self.page.locator("table tbody tr").filter(has_text=name)
        found = row.count() > 0 and name in (
            self._norm(row.first.locator("td").first.inner_text())
        )
        self.search("")
        return found

    def _row_actions_button(self, row):
        btn = row.locator(
            "button:has(.mdi-dots-vertical), button:has(.mdi-dots-horizontal)"
        )
        if btn.count() == 0:
            btn = row.locator("td").last.locator("button")
        return btn.first if btn.count() else None

    @log_method_exceptions
    def delete_template_by_name(self, name: str) -> bool:
        """Corporate list: row Actions → Delete → Delete Document. Returns True if gone."""
        with allure.step(f"Delete Document Template: {name}"):
            self.open_document_templates()
            self.close_editor()
            corp = self.page.get_by_role(
                "tab", name=re.compile(r"Corporate Settings", re.I)
            )
            if corp.count() and corp.first.is_visible():
                corp.first.click(force=True)
                self.page.wait_for_timeout(400)
            # Short search so long names still match the list.
            self.search("Autotest HB MP" if name.lower().startswith("autotest") else name[:40])
            self.page.wait_for_timeout(700)
            body = self.page.locator("table tbody tr")
            target = None
            want = self._norm(name)
            for i in range(min(body.count(), 60)):
                try:
                    cell = self._norm(body.nth(i).locator("td").first.inner_text())
                except Exception:
                    continue
                if cell == want or want.startswith(cell) or cell.startswith(want[:50]):
                    target = body.nth(i)
                    break
            if target is None:
                self.search("")
                return False
            buttons = target.locator("button")
            if buttons.count() == 0:
                self.search("")
                return False
            buttons.last.click(force=True)
            self.page.wait_for_timeout(500)
            delete_item = self.page.get_by_role(
                "menuitem", name=re.compile(r"Delete", re.I)
            )
            if delete_item.count() == 0:
                delete_item = self.page.locator(
                    ".menuable__content__active .v-list-item, [role='menuitem']"
                ).filter(has_text=re.compile(r"^Delete$", re.I))
            if delete_item.count() == 0:
                self.page.keyboard.press("Escape")
                self.search("")
                return False
            delete_item.first.click(force=True)
            self.page.wait_for_timeout(700)
            confirm = self.page.get_by_role(
                "button", name=re.compile(r"Delete Document", re.I)
            )
            if confirm.count() == 0:
                confirm = self.page.locator(
                    ".v-dialog--active button, .v-overlay--active button"
                ).filter(has_text=re.compile(r"Delete", re.I))
            if confirm.count() == 0 or not confirm.last.is_visible():
                self.page.keyboard.press("Escape")
                self.search("")
                return False
            confirm.last.click(force=True)
            self.page.wait_for_timeout(1500)
            # Re-search and confirm the exact title is gone.
            self.search(want[:40])
            self.page.wait_for_timeout(700)
            remaining = False
            body = self.page.locator("table tbody tr")
            for i in range(min(body.count(), 40)):
                try:
                    cell = self._norm(body.nth(i).locator("td").first.inner_text())
                except Exception:
                    continue
                if cell == want:
                    remaining = True
                    break
            self.search("")
            return not remaining

    @log_method_exceptions
    def delete_templates_matching(self, name_prefix: str, *, limit: int = 80) -> list[dict]:
        """Delete Corporate templates whose name starts with ``name_prefix``."""
        results: list[dict] = []
        with allure.step(f"Delete Document Templates matching '{name_prefix}'"):
            self.open_document_templates()
            self.close_editor()
            corp = self.page.get_by_role(
                "tab", name=re.compile(r"Corporate Settings", re.I)
            )
            if corp.count() and corp.first.is_visible():
                corp.first.click(force=True)
                self.page.wait_for_timeout(500)
            # Search short needle so virtualized list loads matches.
            needle = name_prefix.strip()[:40]
            self.search(needle)
            self.page.wait_for_timeout(800)
            for _ in range(limit):
                body = self.page.locator("table tbody tr")
                match_name = None
                for i in range(min(body.count(), 50)):
                    try:
                        cell = self._norm(body.nth(i).locator("td").first.inner_text())
                    except Exception:
                        continue
                    if cell.lower().startswith(name_prefix.strip().lower()):
                        match_name = cell
                        break
                if not match_name:
                    break
                deleted = self.delete_template_by_name(match_name)
                results.append({"name": match_name, "deleted": deleted})
                if not deleted:
                    # Avoid infinite loop on a stuck row.
                    break
                self.search(needle)
                self.page.wait_for_timeout(600)
            self.search("")
        return results

    # Merge Field API name → body label keys (first match wins).
    # Keys match <strong>…</strong> / plain labels in HB_MP template bodies.
    # API merge-field name → body label keys (longest / most specific first).
    # Labels come from document_template_bodies.py specialist + generic HTML.
    TOKEN_LABEL_KEYS: dict[str, list[str]] = {
        "Total Move-In Cost": [
            "Total Cost To Move-In / Total Move-In Cost",
            "Total Move-In Cost (initial)",
            "Total Cost To Move-In",
            "Total Move-In Cost",
            "Total Cost",
        ],
        "Property Security Deposit": [
            "Property Security Deposit",
            "Security Deposit",
        ],
        "Tenant Insurance Premium": [
            "Insurance / Protection Premium",
            "Tenant Insurance Premium",
            "Insurance Premium",
            "Premium",
        ],
        "Tenant Insurance Name": [
            "Tenant Insurance Name / Plan",
            "Protection / Insurance Name",
            "Tenant Insurance Name",
        ],
        "Property Address Line 1": [
            "New Address — Line 1",
            "New Address - Line 1",
            "Property Address Line 1",
            "Facility Address",
            "Property Address",
        ],
        "Property Address Line 2": [
            "New Address — Line 2",
            "New Address - Line 2",
            "Property Address Line 2",
        ],
        "Lease Signed Date": [
            "Lease Signed Date",
        ],
        "Routing Number": [
            "Routing Number",
            "ABA / Routing Number",
        ],
        "Bank Account Number": [
            "Bank Account Number",
            "Account Number",
        ],
        "Tenant Account Type": [
            "Tenant Account Type",
            "Account Type (Checking / Savings)",
            "Account Type",
        ],
        "Bank City": [
            "Bank City",
        ],
        "Bank State": [
            "Bank State",
        ],
        "Bank Postal Code": [
            "Bank Postal Code",
            "Bank ZIP / Postal Code",
        ],
        "Driver License Number": [
            "Driver License Number",
            "Driver's License Number",
            "License Number",
        ],
        "Driver License State": [
            "Driver License State",
            "Driver's License State",
            "License State",
        ],
        "Driver License Expiration Date": [
            "Driver License Expiration Date",
            "License Expiration Date",
        ],
        "Tenant Insurance Policy Number": [
            "Tenant Insurance Policy Number",
            "Insurance Policy Number",
            "Policy Number",
        ],
        "Tenant Insurance Expiration Date": [
            "Tenant Insurance Expiration Date",
            "Insurance Expiration Date",
            "Policy Expiration Date",
        ],
        "Authorized Access Person Name": [
            "Authorized Access Person Name",
            "Authorized Person Name",
        ],
        "Authorized Access Person Phone": [
            "Authorized Access Person Phone",
            "Authorized Person Phone",
        ],
        "Vehicle License Plate Number": [
            "Vehicle License Plate Number",
            "License Plate Number",
        ],
        "Vehicle VIN": [
            "Vehicle VIN",
            "VIN",
        ],
        "Vehicle Make": [
            "Vehicle Make",
            "Make",
        ],
        "Vehicle Model": [
            "Vehicle Model",
            "Model",
        ],
        "Military Branch Name": [
            "Military Branch Name",
            "Branch Name",
            "Branch",
        ],
        "Servicemember Name": [
            "Servicemember Name",
            "Service Member Name",
        ],
        "Protected Property": [
            "Protected Property description",
            "Protected Property",
        ],
        "Protection Plan Consent": [
            "Protection Plan Consent",
        ],
        "Notice Delivery Method": [
            "Notice Delivery Method",
        ],
    }

    def _editor(self):
        """Primary document body — not header/footer TinyMCE clones.

        Stage Document Templates has three ``.mce-content-body`` nodes
        (``editor_header``, ``editor_primary``, ``editor_footer``). Matching
        ``.mce-content-body`` alone returns the empty header and merge-field
        tokens never land in the real document.
        """
        return self.page.locator("#editor_primary").first

    def _focus_primary_editor(self) -> bool:
        """Focus ``#editor_primary`` without moving the caret to the end."""
        ed = self._editor()
        try:
            expect(ed).to_be_visible(timeout=waits().medium)
        except AssertionError:
            return False
        try:
            ed.click(timeout=waits().medium, force=True)
            self.page.evaluate(
                """() => {
                  const el = document.querySelector('#editor_primary');
                  if (!el) return;
                  el.focus();
                  if (window.tinymce) {
                    const ed = window.tinymce.get('editor_primary')
                      || (window.tinymce.editors || []).find(
                        e => e && e.id === 'editor_primary'
                      );
                    if (ed) ed.focus();
                  }
                }"""
            )
            self.page.wait_for_timeout(150)
            return True
        except Exception:
            return False

    def _token_already_beside_label(self, token: str, keys: list[str]) -> bool:
        """True when a merge pill for *this* token already sits on its label line."""
        return bool(
            self.page.evaluate(
                """({ token, keys }) => {
                  const root = document.querySelector('#editor_primary');
                  if (!root) return false;
                  const norm = (s) => (s || '').toLowerCase()
                    .replace(/[–—]/g, '-').replace(/\\s+/g, ' ').trim();
                  const keyNorms = keys.map(norm).filter(Boolean);
                  const tokenNorm = norm(token);
                  const isOurPill = (el) => {
                    const t = norm(el.innerText || el.textContent || '');
                    if (!t) return false;
                    if (t === tokenNorm || t.includes(tokenNorm)) return true;
                    return keyNorms.some(k => t === k || t === '[' + k + ']'
                      || t.includes(k));
                  };
                  for (const el of root.querySelectorAll('p, li, td, div, h2, h3')) {
                    const et = norm(el.innerText || '');
                    if (!keyNorms.some(k => et.includes(k))) continue;
                    const pills = [...el.querySelectorAll(
                      '[contenteditable="false"], [class*=merge], [class*=token],'
                      + ' [data-merge], [data-mce-token], [data-field]'
                    )];
                    if (pills.some(isOurPill)) return true;
                    if (et.includes('[' + tokenNorm + ']')) return true;
                    if (keyNorms.some(k => et.includes('[' + k + ']'))) return true;
                  }
                  return false;
                }""",
                {"token": token, "keys": keys},
            )
        )

    def _find_label_key(self, token: str, keys: list[str]) -> str:
        """Return ``present:<key>`` if a body label exists; else ``missing``."""
        return self.page.evaluate(
            """({ keys }) => {
              const root = document.querySelector('#editor_primary');
              if (!root) return 'missing-editor';
              const norm = (s) => (s || '').toLowerCase()
                .replace(/[–—]/g, '-').replace(/\\s+/g, ' ').trim();
              const body = norm(root.innerText || '');
              const ordered = [...keys].sort((a, b) =>
                norm(b).length - norm(a).length
              );
              for (const k of ordered) {
                if (body.includes(norm(k))) return 'present:' + k;
              }
              return 'missing';
            }""",
            {"keys": keys},
        )

    def _ensure_label_key(
        self, token: str, keys: list[str], *, allow_add: bool = False
    ) -> str:
        """Locate a body label for ``token``.

        By default does **not** invent orphan labels — missing keys are
        skipped by the insert path. Set ``allow_add=True`` only for
        deliberate backfills.
        """
        found = self._find_label_key(token, keys)
        if found.startswith("present") or found.startswith("missing-editor"):
            return found
        if not allow_add:
            return "missing"
        return self.page.evaluate(
            """({ token, keys }) => {
              const root = document.querySelector('#editor_primary');
              if (!root) return 'missing-editor';
              const norm = (s) => (s || '').toLowerCase()
                .replace(/[–—]/g, '-').replace(/\\s+/g, ' ').trim();
              const ordered = [...keys].sort((a, b) =>
                norm(b).length - norm(a).length
              );
              const key = ordered[0] || token;
              const p = document.createElement('p');
              p.innerHTML = '<strong>' + key + ':</strong> ';
              root.appendChild(p);
              return 'added:' + key;
            }""",
            {"token": token, "keys": keys},
        )

    def _place_caret_for_token(self, token: str) -> str:
        """Place caret after the matching body label key for ``token``.

        Preference:
        1. Select plain ``[Token]`` placeholder (replace)
        2. Caret after matching label key (``Key:``)
        3. ``missing-label`` when no intentional key exists (do not EOF-dump)
        """
        keys = list(self.TOKEN_LABEL_KEYS.get(token) or [token])
        if token not in keys:
            keys = [*keys, token]
        keys = sorted(set(keys), key=lambda k: (-len(k), k))
        label_state = self._ensure_label_key(token, keys, allow_add=False)
        if label_state == "missing" or label_state.startswith("missing"):
            # Still allow placeholder replace if [Token] text exists
            pass
        return self.page.evaluate(
            """({ token, keys, labelState }) => {
              const root = document.querySelector('#editor_primary');
              if (!root) return 'missing';

              const norm = (s) => (s || '').toLowerCase()
                .replace(/[–—]/g, '-')
                .replace(/\\s+/g, ' ')
                .trim();
              const keyNorms = keys.map(norm);

              const setRange = (range, collapseEnd) => {
                const sel = window.getSelection();
                if (!sel) return;
                if (collapseEnd) range.collapse(false);
                sel.removeAllRanges();
                sel.addRange(range);
                root.focus();
                if (window.tinymce) {
                  const ed = window.tinymce.get('editor_primary');
                  if (ed) {
                    ed.focus();
                    try { ed.selection.setRng(range); } catch (e) {}
                  }
                }
              };

              // 1) Select plain [Token] / [Key] placeholder
              const walker1 = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
              let node;
              while ((node = walker1.nextNode())) {
                const raw = node.nodeValue || '';
                if (!raw) continue;
                for (const k of keys.concat([token])) {
                  const needle = '[' + k + ']';
                  const idx = raw.toLowerCase().indexOf(needle.toLowerCase());
                  if (idx >= 0) {
                    const range = document.createRange();
                    range.setStart(node, idx);
                    range.setEnd(node, idx + needle.length);
                    setRange(range, false);
                    return 'replaced-placeholder:' + k;
                  }
                }
              }

              // 2) Caret after label key text
              let best = null;
              const walker2 = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
              while ((node = walker2.nextNode())) {
                const raw = node.nodeValue || '';
                if (!raw.trim()) continue;
                const n = norm(raw);
                for (let i = 0; i < keyNorms.length; i++) {
                  const k = keyNorms[i];
                  if (!k) continue;
                  const naked = n.replace(/:+\\s*$/, '');
                  const isExact = naked === k;
                  const isLabelLine = naked.endsWith(k) || n === k + ':'
                    || n.startsWith(k + ':') || n.startsWith(k + ' :');
                  const shortEnough = naked.length <= k.length + 8;
                  if (!(isExact || (isLabelLine && shortEnough))) continue;
                  const score = (n.includes(k + ':') || /:$/.test(n.trim()) ? 20 : 0)
                    + (isExact ? 10 : 0)
                    + k.length;
                  if (!best || score > best.score) {
                    best = { node, score, key: keys[i] };
                  }
                }
              }
              if (best) {
                const range = document.createRange();
                range.setStart(best.node, best.node.nodeValue.length);
                range.setEnd(best.node, best.node.nodeValue.length);
                setRange(range, false);
                const parent = best.node.parentElement;
                if (parent && parent.tagName === 'STRONG' && parent.parentNode) {
                  const after = document.createRange();
                  after.setStartAfter(parent);
                  after.collapse(true);
                  setRange(after, false);
                }
                return 'after-label:' + best.key;
              }

              // 3) No intentional label — do not dump at EOF
              return 'missing-label';
            }""",
            {"token": token, "keys": keys, "labelState": label_state},
        )

    def _merge_search_input(self):
        wrap = self.page.locator(
            'div[placeholder="Search Merge Fields"], '
            '.hb-text-field-wrapper[placeholder="Search Merge Fields"]'
        )
        if wrap.count() and wrap.first.is_visible():
            inp = wrap.first.locator("input")
            if inp.count():
                return inp.first
        inp = self.page.locator('input[placeholder*="Search Merge" i]')
        return inp.first if inp.count() else None

    @log_method_exceptions
    def open_merge_fields(self) -> bool:
        if self.page.get_by_text(re.compile(r"All Merge Fields", re.I)).count():
            return True
        candidates = [
            self.page.get_by_role(
                "button", name=re.compile(r"merge\s*fields?", re.I)
            ),
            self.page.locator(
                "[aria-label*='merge' i], [title*='merge' i], "
                "[aria-label*='token' i], [title*='token' i]"
            ),
            self.page.locator("button").filter(
                has=self.page.locator(".mdi-auto-fix, .mdi-wand, .mdi-magic")
            ),
        ]
        for loc in candidates:
            if loc.count() == 0:
                continue
            try:
                if not loc.first.is_visible():
                    continue
                loc.first.click(timeout=waits().medium, force=True)
                self.page.wait_for_timeout(600)
                if self.page.get_by_text(
                    re.compile(r"All Merge Fields|Search Merge Fields", re.I)
                ).count():
                    return True
            except Exception:
                continue
        for sel in (".tox-tbtn", ".mce-btn button"):
            btns = self.page.locator(sel)
            for i in range(min(btns.count(), 40)):
                btn = btns.nth(i)
                try:
                    label = (
                        btn.get_attribute("aria-label")
                        or btn.get_attribute("title")
                        or ""
                    )
                    if re.search(r"merge|token|field", label, re.I):
                        btn.click(timeout=waits().short, force=True)
                        self.page.wait_for_timeout(600)
                        if self.page.get_by_text(
                            re.compile(r"All Merge Fields", re.I)
                        ).count():
                            return True
                except Exception:
                    continue
        return (
            self.page.get_by_text(re.compile(r"All Merge Fields", re.I)).count() > 0
        )

    def _strip_end_dumped_tokens(self) -> int:
        """Remove merge-field pills piled at the end of ``#editor_primary``.

        Earlier inserts collapsed the caret to EOF so tokens clustered at the
        bottom / under ``Merge field anchors``. Strip those before placing
        tokens next to body labels.
        """
        return int(
            self.page.evaluate(
                """() => {
                  const root = document.querySelector('#editor_primary');
                  if (!root) return 0;
                  let removed = 0;
                  const isPill = (el) => {
                    if (!el || el.nodeType !== 1) return false;
                    const cls = (el.className || '') + '';
                    const txt = (el.innerText || '').trim();
                    if (!txt || txt.length > 80) return false;
                    if (/merge|token|mceNonEditable|hb-pill|field-pill/i.test(cls))
                      return true;
                    // Blue HB merge pills often look like [Name]
                    if (/^\\[.+\\]$/.test(txt) && el.children.length === 0)
                      return /background|pill|chip|merge/i.test(
                        getComputedStyle(el).backgroundColor + cls
                      ) || el.getAttribute('contenteditable') === 'false';
                    if (el.getAttribute('data-merge-field')
                        || el.getAttribute('data-mce-token')
                        || el.getAttribute('data-field'))
                      return true;
                    return false;
                  };
                  // Remove trailing empty / pill-only paragraphs at end
                  while (root.lastElementChild) {
                    const last = root.lastElementChild;
                    const pills = [...last.querySelectorAll('*')].filter(isPill);
                    const text = (last.innerText || '').trim();
                    const onlyPills = pills.length && pills.every(p =>
                      last.contains(p)
                    ) && text.replace(/\\[.*?\\]/g, '').trim().length < 3;
                    const isAnchorHeading = /merge field anchors/i.test(text);
                    if (isAnchorHeading || onlyPills || isPill(last)) {
                      // Also remove following sibling pills inside last
                      pills.forEach(p => { p.remove(); removed++; });
                      if (isAnchorHeading || onlyPills
                          || (!(last.innerText || '').trim())) {
                        last.remove();
                        removed++;
                        continue;
                      }
                    }
                    break;
                  }
                  // Remove orphan plain [Token] text under anchors section
                  const walker = document.createTreeWalker(
                    root, NodeFilter.SHOW_ELEMENT
                  );
                  const toRemove = [];
                  let n;
                  while ((n = walker.nextNode())) {
                    if (isPill(n)) {
                      // Keep pills that sit in the same block as a label ':'
                      const block = n.closest('p, li, td, h1, h2, h3, div') || n.parentElement;
                      const bt = (block && block.innerText) || '';
                      if (/merge field anchors/i.test(bt)) {
                        toRemove.push(n);
                        continue;
                      }
                      // Trailing-only blocks with just pills
                      if (block && /^\\s*(\\[[^\\]]+\\]\\s*)+$/.test(bt.trim()))
                        toRemove.push(block);
                    }
                  }
                  toRemove.forEach(el => { try { el.remove(); removed++; } catch (e) {} });
                  return removed;
                }"""
            )
            or 0
        )

    @log_method_exceptions
    def insert_merge_fields(self, tokens: list[str]) -> dict:
        """Insert HB Merge Field tokens next to matching body labels.

        For each token: place caret at ``[Token]`` placeholder or after the
        matching label in ``#editor_primary``, then click the Merge Fields
        list item. Tokens without an intentional body label are skipped
        (no orphan labels, no EOF dump).

        Returns ``{inserted, skipped, placements}``.
        """
        inserted: list[str] = []
        skipped: list[str] = []
        placements: list[str] = []
        empty = {"inserted": inserted, "skipped": skipped, "placements": placements}
        if not self.open_merge_fields():
            self.page.wait_for_timeout(500)
            self._focus_primary_editor()
            if not self.open_merge_fields():
                allure.attach(
                    "Merge Fields sidebar did not open",
                    name="merge-fields-missing",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return empty
        if not self._focus_primary_editor():
            allure.attach(
                "#editor_primary not focused",
                name="merge-fields-editor-focus-failed",
                attachment_type=allure.attachment_type.TEXT,
            )
            return empty
        stripped = self._strip_end_dumped_tokens()
        if stripped:
            allure.attach(
                f"stripped_end_tokens={stripped}",
                name="merge-field-strip",
                attachment_type=allure.attachment_type.TEXT,
            )
        search = self._merge_search_input()
        for token in tokens:
            try:
                if not self._focus_primary_editor():
                    skipped.append(f"{token}@no-focus")
                    continue
                keys = list(self.TOKEN_LABEL_KEYS.get(token) or [token])
                if token not in keys:
                    keys = [*keys, token]
                if self._token_already_beside_label(token, keys):
                    placements.append(f"{token}@already-beside-label")
                    inserted.append(token)
                    continue
                where = self._place_caret_for_token(token) or "missing-label"
                if where == "missing-label" or where.startswith("missing"):
                    # Prefer adding the intended body label over skipping.
                    added = self._ensure_label_key(token, keys, allow_add=True)
                    where = self._place_caret_for_token(token) or "missing-label"
                    if where.startswith("after-label") or where.startswith(
                        "replaced"
                    ):
                        placements.append(f"{token}@{added}->{where}")
                    else:
                        placements.append(f"{token}@{where}")
                        skipped.append(f"{token}@{where}")
                        continue
                else:
                    placements.append(f"{token}@{where}")
                if search is not None:
                    search.fill(token)
                    self.page.wait_for_timeout(450)
                where2 = self._place_caret_for_token(token) or where
                if where2 == "missing-label" or where2.startswith("missing"):
                    placements[-1] = f"{token}@{where}->{where2}"
                    skipped.append(f"{token}@{where2}")
                    continue
                if where2 != where:
                    placements[-1] = f"{token}@{where}->{where2}"
                item = self.page.locator(
                    ".menuable__content__active .v-list-item, "
                    "[role='listbox'] .v-list-item, .v-list-item"
                ).filter(has_text=re.compile(rf"^{re.escape(token)}$", re.I))
                if item.count() == 0:
                    item = self.page.locator(
                        ".v-list-item.theme--light, .v-list-item"
                    ).filter(has_text=re.compile(rf"^{re.escape(token)}$", re.I))
                if item.count() == 0:
                    item = self.page.get_by_text(token, exact=True)
                clicked = False
                for i in range(min(item.count(), 6)):
                    cand = item.nth(i)
                    try:
                        if not cand.is_visible():
                            continue
                        before = self._primary_editor_html()
                        cand.click(timeout=waits().medium, force=True)
                        self.page.wait_for_timeout(400)
                        after = self._primary_editor_html()
                        if after != before or token.casefold() in after.casefold():
                            inserted.append(token)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked and item.count() and item.first.is_visible():
                    before = self._primary_editor_html()
                    item.first.click(timeout=waits().medium, force=True)
                    self.page.wait_for_timeout(400)
                    after = self._primary_editor_html()
                    if after != before or token.casefold() in after.casefold():
                        inserted.append(token)
                        clicked = True
                if not clicked:
                    skipped.append(f"{token}@click-failed")
            except Exception as exc:
                skipped.append(f"{token}@{type(exc).__name__}")
                continue
        if placements:
            allure.attach(
                "\n".join(placements),
                name="merge-field-placements",
                attachment_type=allure.attachment_type.TEXT,
            )
        if search is not None:
            try:
                search.fill("")
            except Exception:
                pass
        return {
            "inserted": inserted,
            "skipped": skipped,
            "placements": placements,
        }

    def _primary_editor_html(self) -> str:
        try:
            return self.page.evaluate(
                """() => {
                  const el = document.querySelector('#editor_primary');
                  return el ? (el.innerHTML || '') : '';
                }"""
            ) or ""
        except Exception:
            return ""

    @log_method_exceptions
    def set_editor_html(self, html: str) -> None:
        """Replace ``#editor_primary`` content (TinyMCE-aware, wipe prior dumps)."""
        ok = self.page.evaluate(
            """(html) => {
              const applyDom = () => {
                const el = document.querySelector('#editor_primary');
                if (el) {
                  el.innerHTML = html;
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                }
                return !!el;
              };
              if (window.tinymce) {
                const ed = window.tinymce.get('editor_primary')
                  || (window.tinymce.editors || []).find(
                    e => e && (e.id === 'editor_primary'
                      || (e.targetElm && e.targetElm.id === 'editor_primary'))
                  );
                if (ed) {
                  try {
                    ed.focus();
                    ed.setContent(html, { format: 'html' });
                    try { ed.undoManager.clear(); } catch (e) {}
                    try { ed.nodeChanged(); } catch (e) {}
                    applyDom();
                    return 'tinymce:' + (ed.getContent({ format: 'text' }) || '').length;
                  } catch (e) {
                    applyDom();
                    return 'tinymce-err:' + e;
                  }
                }
              }
              return applyDom() ? 'dom' : 'missing';
            }""",
            html,
        )
        self.page.wait_for_timeout(400)
        # Verify old EOF anchor dumps are gone; force DOM overwrite if not.
        still_dirty = self.page.evaluate(
            """() => {
              const el = document.querySelector('#editor_primary');
              const text = (el && el.innerText) || '';
              return /merge field anchors/i.test(text);
            }"""
        )
        if still_dirty:
            self.page.evaluate(
                """(html) => {
                  const el = document.querySelector('#editor_primary');
                  if (el) el.innerHTML = html;
                  if (window.tinymce) {
                    const ed = window.tinymce.get('editor_primary');
                    if (ed) ed.setContent(html, { format: 'html' });
                  }
                }""",
                html,
            )
            self.page.wait_for_timeout(300)
        allure.attach(
            str(ok),
            name="set-editor-html",
            attachment_type=allure.attachment_type.TEXT,
        )

    @log_method_exceptions
    def save_template(self) -> bool:
        btn = self.page.get_by_role(
            "button", name=re.compile(r"Save Template", re.I)
        )
        if btn.count() == 0:
            btn = self.page.locator("button").filter(
                has_text=re.compile(r"Save Template", re.I)
            )
        if btn.count() == 0 or not btn.first.is_visible():
            return False
        btn.first.click(timeout=self.timeout, force=True)
        self.page.wait_for_timeout(1200)
        return True

    def _template_name_input(self):
        """Name field on Create/Edit form — never the list table 'Name' header."""
        by_ph = self.page.locator('input[placeholder="Template Name"]')
        if by_ph.count() and by_ph.first.is_visible():
            return by_ph.first
        for loc in (
            self.page.get_by_role(
                "textbox",
                name=re.compile(r"template\s*name|document\s*name|^name$", re.I),
            ),
            self.page.locator(
                '.v-dialog input[type="text"], '
                '.v-overlay--active input[type="text"], '
                'input[placeholder*="Name" i], '
                'input[aria-label*="Name" i]'
            ),
        ):
            if loc.count() == 0:
                continue
            for i in range(min(loc.count(), 8)):
                el = loc.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    ph = (el.get_attribute("placeholder") or "").lower()
                    aria = (el.get_attribute("aria-label") or "").lower()
                    if "search" in ph or "search" in aria:
                        continue
                    if "template name" in ph or "name" in ph:
                        return el
                except Exception:
                    continue
        return None

    def _category_select_trigger(self):
        """Vuetify wraps a readonly input; click the selections / select root."""
        inp = self.page.locator('input[placeholder="Select Category"]')
        if inp.count() == 0:
            return None
        # Prefer the visible select shell that intercepts clicks.
        shell = inp.first.locator(
            "xpath=ancestor::div[contains(@class,'v-select')][1]"
        )
        if shell.count() and shell.first.is_visible():
            return shell.first
        selections = inp.first.locator(
            "xpath=ancestor::div[contains(@class,'v-input')][1]"
            "//div[contains(@class,'v-select__selections')]"
        )
        if selections.count():
            return selections.first
        return inp.first

    def _select_type(self, type_label: str) -> bool:
        """Document type is the Create form 'Select Category' control."""
        return self._select_category_label(type_label)

    def _select_category_label(self, type_label: str) -> bool:
        inp = self.page.locator('input[placeholder="Select Category"]')
        if inp.count() == 0:
            return False
        shell = inp.first.locator(
            "xpath=ancestor::div[contains(@class,'v-select')][1]"
        )
        trigger = shell.first if shell.count() else inp.first
        try:
            trigger.click(timeout=waits().medium, force=True)
        except Exception:
            return False
        self.page.wait_for_timeout(400)

        filter_text = type_label.strip()
        if "(" in filter_text:
            filter_text = filter_text.split("(", 1)[0].strip()
        # Vuetify category select often needs real keystrokes (fill is ignored).
        try:
            inp.first.click(force=True)
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.keyboard.type(filter_text[:40], delay=35)
            self.page.wait_for_timeout(500)
        except Exception:
            pass

        patterns = [
            re.compile(rf"^{re.escape(type_label)}$", re.I),
            re.compile(rf"^{re.escape(filter_text)}", re.I),
            re.compile(re.escape(type_label), re.I),
        ]
        menu = self.page.locator(
            ".menuable__content__active, [role='listbox'], .v-select-list"
        ).last
        short = waits().short
        for _ in range(40):
            if menu.count() == 0:
                break
            for pat in patterns:
                opt = menu.locator(
                    "[role='option'], .v-list-item__title, .v-list-item"
                ).filter(has_text=pat)
                for i in range(min(opt.count(), 6)):
                    try:
                        text = self._norm(opt.nth(i).inner_text(timeout=400))
                    except Exception:
                        continue
                    if text.lower() in {
                        "dashboard",
                        "spaces",
                        "tenants",
                        "leads",
                        "reports",
                        "tools",
                        "log out",
                    }:
                        continue
                    if not pat.search(text):
                        continue
                    try:
                        opt.nth(i).click(timeout=short, force=True)
                        self.page.wait_for_timeout(400)
                        return True
                    except Exception:
                        continue
            try:
                menu.evaluate("el => { el.scrollTop += 220 }")
                self.page.wait_for_timeout(100)
            except Exception:
                try:
                    self.page.keyboard.press("PageDown")
                    self.page.wait_for_timeout(100)
                except Exception:
                    break
        return False

    def select_category_any(self, preferred: list[str]) -> str | None:
        """Try each preferred category label; return the one that worked."""
        seen: set[str] = set()
        for label in preferred:
            key = (label or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            if self._select_category_label(label):
                return label
        return None

    @log_method_exceptions
    def scrape_type_options(self) -> list[str]:
        """Open Create New, collect every Select Category option.

        Vuetify category lists are virtualized. Collect by typing each
        a–z filter prefix once (and empty) and harvesting visible options.
        """
        with allure.step("Scrape all Document Template category options"):
            self.open_document_templates()
            self.close_editor()
            self.page.get_by_role(
                "button", name=re.compile(r"Create New Template", re.I)
            ).click(timeout=self.timeout)
            self.page.wait_for_timeout(1000)
            trigger = self._category_select_trigger()
            if trigger is None:
                self.close_editor()
                return []
            seen: set[str] = set()

            def _harvest() -> None:
                opts = self.page.locator(
                    "[role='listbox'] [role='option'], "
                    ".v-menu__content .v-list-item, "
                    ".v-select-list .v-list-item"
                )
                for i in range(opts.count()):
                    try:
                        text = self._norm(opts.nth(i).inner_text(timeout=300))
                    except Exception:
                        continue
                    if (
                        text
                        and len(text) < 80
                        and text.lower() not in ("", "select category")
                    ):
                        seen.add(text)

            try:
                trigger.click(timeout=self.timeout, force=True)
                self.page.wait_for_timeout(400)
                cat_input = self.page.locator(
                    'input[placeholder="Select Category"]'
                )
                listbox = self.page.locator(
                    "[role='listbox'], .v-menu__content, .v-select-list"
                ).last

                # Empty filter + scroll the open list once.
                _harvest()
                for _ in range(30):
                    before = len(seen)
                    try:
                        listbox.evaluate("el => { el.scrollTop += 280 }")
                    except Exception:
                        self.page.keyboard.press("PageDown")
                    self.page.wait_for_timeout(100)
                    _harvest()
                    if len(seen) == before:
                        break

                # Letter prefixes force virtualization to load other buckets.
                if cat_input.count() and cat_input.first.is_visible():
                    for prefix in "abcdefghijklmnopqrstuvwxyz":
                        try:
                            cat_input.first.fill(prefix)
                            self.page.wait_for_timeout(280)
                            _harvest()
                            # Small scroll within filtered bucket.
                            for _ in range(6):
                                before = len(seen)
                                try:
                                    listbox.evaluate(
                                        "el => { el.scrollTop += 200 }"
                                    )
                                except Exception:
                                    break
                                self.page.wait_for_timeout(80)
                                _harvest()
                                if len(seen) == before:
                                    break
                        except Exception:
                            continue
                    try:
                        cat_input.first.fill("")
                    except Exception:
                        pass
                self.page.keyboard.press("Escape")
            except Exception as exc:
                allure.attach(
                    repr(exc)[:400],
                    name="category-scrape-failed",
                    attachment_type=allure.attachment_type.TEXT,
                )
            self.close_editor()
            return sorted(seen, key=str.lower)

    @log_method_exceptions
    def open_template_by_name(self, name: str) -> bool:
        self.open_document_templates()
        self.close_editor()
        self.page.wait_for_timeout(800)
        # Prefer exact first-cell match after search.
        needle = name.replace("\u2014", "-").strip()
        self.search(needle[:40] if len(needle) > 40 else needle)
        self.page.wait_for_timeout(700)
        rows = self.page.locator("table tbody tr")
        target = None
        for i in range(min(rows.count(), 40)):
            cell = self._norm(rows.nth(i).locator("td").first.inner_text())
            if cell == name or cell == needle or name in cell or needle in cell:
                target = rows.nth(i)
                break
        if target is None:
            self.search("")
            return False
        target.locator("td").first.click(timeout=self.timeout, force=True)
        self.page.wait_for_timeout(1500)
        try:
            expect(self._editor()).to_be_visible(timeout=waits().long)
            return True
        except AssertionError:
            # Try row action menu → Edit if direct click only selected the row.
            try:
                menu = target.locator("button").last
                if menu.count():
                    menu.click(force=True)
                    self.page.wait_for_timeout(400)
                    edit = self.page.get_by_role(
                        "menuitem", name=re.compile(r"edit|open|view", re.I)
                    )
                    if edit.count() == 0:
                        edit = self.page.get_by_text(re.compile(r"^edit$", re.I))
                    if edit.count():
                        edit.first.click(force=True)
                        self.page.wait_for_timeout(1200)
            except Exception:
                pass
            visible = False
            try:
                expect(self._editor()).to_be_visible(timeout=waits().medium)
                visible = True
            except AssertionError:
                visible = False
            self.search("")
            return visible

    @log_method_exceptions
    def create_template(
        self,
        *,
        name: str,
        type_label: str,
        signed: bool,
        intro_html: str,
        tokens: list[str],
        docx_path: str | Path | None = None,
        preferred_types: list[str] | None = None,
    ) -> dict:
        """Create via Save Document modal: name, category, upload .docx, Save.

        Live Create New (stage 2026-09-20) opens a **Save Document** dialog
        that requires a Word (.docx) upload — TinyMCE alone returns Error.
        After a successful Save, optionally reopen to insert Merge Fields.
        """
        result: dict = {
            "name": name,
            "type": type_label,
            "saved": False,
            "inserted_tokens": [],
            "steps": [],
        }
        with allure.step(f"Create Document Template: {name} ({type_label})"):
            docx = Path(docx_path) if docx_path else None
            if docx is None or not docx.is_file():
                result["steps"].append("docx missing")
                return result

            self.open_document_templates()
            self.close_editor()
            self.page.get_by_role(
                "button", name=re.compile(r"Create New Template", re.I)
            ).click(timeout=self.timeout)
            expect(
                self.page.locator('input[placeholder="Template Name"]')
            ).to_be_visible(timeout=self.timeout)
            result["steps"].append("opened create")

            name_input = self._template_name_input()
            if name_input is None:
                result["steps"].append("name input not found")
                self.close_editor()
                return result
            name_input.click(force=True)
            name_input.fill(name)
            result["steps"].append("name")
            self.page.wait_for_timeout(400)

            cat_inp = self.page.locator('input[placeholder="Select Category"]')
            expect(cat_inp.first).to_be_visible(timeout=waits().medium)

            ordered: list[str] = []
            for lab in [type_label] + list(preferred_types or []):
                if lab and lab not in ordered:
                    ordered.append(lab)
            chosen = self.select_category_any(ordered[:4])
            if chosen:
                result["steps"].append(f"category={chosen}")
                result["type"] = chosen
            else:
                # Diagnostics: what is actually in the open category menu?
                try:
                    shell = cat_inp.first.locator(
                        "xpath=ancestor::div[contains(@class,'v-select')][1]"
                    )
                    shell.click(force=True)
                    self.page.wait_for_timeout(500)
                    visible = []
                    menu = self.page.locator(
                        ".menuable__content__active, [role='listbox'], "
                        ".v-select-list"
                    ).last
                    items = menu.locator("[role='option'], .v-list-item")
                    for i in range(min(items.count(), 40)):
                        try:
                            visible.append(
                                self._norm(items.nth(i).inner_text(timeout=300))
                            )
                        except Exception:
                            pass
                    allure.attach(
                        "\n".join(visible) or "(none)",
                        name="category-menu-visible",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    result["steps"].append(
                        f"category missing={ordered[:4]}; menu={visible[:15]}"
                    )
                except Exception as exc:
                    result["steps"].append(
                        f"category missing={ordered[:4]}; diag={type(exc).__name__}"
                    )
                self.close_editor()
                return result

            # Upload required .docx (paperclip / file input on Save Document modal).
            file_input = self.page.locator('input[type="file"]')
            if file_input.count() == 0:
                result["steps"].append("file input missing")
                self.close_editor()
                return result
            file_input.first.set_input_files(str(docx))
            self.page.wait_for_timeout(800)
            result["steps"].append(f"uploaded {docx.name}")

            # Modal primary is "Save" inside Save Document dialog.
            saved = False
            modal_save = self.page.locator(".v-dialog, .v-overlay--active").get_by_role(
                "button", name=re.compile(r"^Save$", re.I)
            )
            if modal_save.count() and modal_save.first.is_visible():
                modal_save.first.click(timeout=self.timeout, force=True)
                self.page.wait_for_timeout(2500)
                result["steps"].append("clicked modal Save")
                saved = True
            else:
                for label in ("Save", "Save Template"):
                    btn = self.page.get_by_role(
                        "button", name=re.compile(rf"^{re.escape(label)}$", re.I)
                    )
                    if btn.count() and btn.first.is_visible():
                        btn.first.click(timeout=self.timeout, force=True)
                        self.page.wait_for_timeout(2500)
                        result["steps"].append(f"clicked {label}")
                        saved = True
                        break
            if not saved:
                result["steps"].append("Save button missing")
                self.close_editor()
                return result

            # Detect error toast.
            err = self.page.get_by_text(re.compile(r"^Error$", re.I))
            if err.count() and err.first.is_visible():
                result["steps"].append("save error toast")
                self.close_editor()
                return result

            result["saved"] = True
            result["steps"].append("saved with docx")
            self.page.wait_for_timeout(1000)
            self.close_editor()

            # Best-effort: reopen and attach Merge Fields pills when editor allows.
            if tokens and self.open_template_by_name(name):
                result["steps"].append("reopened for tokens")
                try:
                    expect(self._editor()).to_be_visible(timeout=waits().medium)
                    inserted_result = self.insert_merge_fields(tokens)
                    inserted = (
                        inserted_result.get("inserted", [])
                        if isinstance(inserted_result, dict)
                        else list(inserted_result or [])
                    )
                    result["inserted_tokens"] = inserted
                    result["steps"].append(f"tokens={inserted}")
                    if self.save_template():
                        result["steps"].append("saved tokens")
                except Exception as exc:
                    result["steps"].append(f"token pass skipped: {type(exc).__name__}")
                self.close_editor()
        return result

    @log_method_exceptions
    def open_property_settings_tab(self) -> bool:
        """Best-effort open Property Settings (overlays may block)."""
        with allure.step("Document Templates → Property Settings"):
            self.open_document_templates()
            tab = self.page.get_by_role(
                "tab", name=re.compile(r"Property Settings", re.I)
            )
            if tab.count() == 0 or not tab.first.is_visible():
                return False
            try:
                tab.first.click(timeout=waits().medium, force=True)
                self.page.wait_for_timeout(800)
                return True
            except Exception as exc:
                allure.attach(
                    repr(exc)[:500],
                    name="property-settings-tab-failed",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return False

    def _editor_header_dots_button(self):
        """Template editor header ⋮ (next to 'N Properties' / close).

        HB clones many ``QA-v-menu-HbIcon-mdi-dots-vertical`` nodes; pick the
        rightmost visible one in the template title bar (y ~80).
        """
        named = self.page.locator(
            'button[name="QA-v-menu-HbIcon-mdi-dots-vertical"]'
        )
        best = None
        best_x = -1.0
        for i in range(named.count()):
            btn = named.nth(i)
            try:
                if not btn.is_visible():
                    continue
                box = btn.bounding_box()
                if not box:
                    continue
                # Template editor title bar (not app chrome at y~9)
                if 60 <= box["y"] <= 120 and box["x"] > best_x:
                    best = btn
                    best_x = box["x"]
            except Exception:
                continue
        if best is not None:
            return best
        dots = self.page.locator("button:has(.mdi-dots-vertical)")
        for i in range(dots.count()):
            btn = dots.nth(i)
            try:
                if not btn.is_visible():
                    continue
                box = btn.bounding_box()
                if not box:
                    continue
                if 60 <= box["y"] <= 120 and box["x"] > best_x:
                    best = btn
                    best_x = box["x"]
            except Exception:
                continue
        return best

    def _click_active_menu_edit(self) -> bool:
        """Click Edit in the open Vuetify menu (menuable__content__active)."""
        # Prefer Playwright on active menu overlay
        edit = self.page.locator(
            ".menuable__content__active .v-list-item, "
            ".v-menu__content.menuable__content__active .v-list-item"
        ).filter(has_text=re.compile(r"^Edit$", re.I))
        if edit.count():
            try:
                edit.first.click(force=True, timeout=waits().medium)
                return True
            except Exception:
                pass
        # JS fallback — Playwright sometimes sees the item as not visible
        return bool(
            self.page.evaluate(
                """() => {
                  const nodes = document.querySelectorAll(
                    '.menuable__content__active .v-list-item, '
                    + '.v-menu__content.menuable__content__active .v-list-item, '
                    + '[role=menuitem]'
                  );
                  for (const n of nodes) {
                    if ((n.innerText || '').trim() === 'Edit') {
                      n.click();
                      return true;
                    }
                  }
                  return false;
                }"""
            )
        )

    @log_method_exceptions
    def open_save_document_dialog_from_editor(self) -> bool:
        """Editor header ⋮ → Edit → opens Save Document (name / category / properties)."""
        with allure.step("Document template editor ⋮ → Edit"):
            save_tpl = self.page.get_by_role(
                "button", name=re.compile(r"Save Template", re.I)
            )
            try:
                if save_tpl.count():
                    save_tpl.first.wait_for(state="visible", timeout=waits().long)
            except Exception:
                pass

            def _dialog_open() -> bool:
                name_inp = self.page.locator('input[placeholder="Template Name"]')
                enable = self.page.get_by_text(
                    re.compile(r"Enable\s+Hummingbird\s+Propert", re.I)
                )
                try:
                    if name_inp.count() and name_inp.first.is_visible():
                        return True
                except Exception:
                    pass
                try:
                    if enable.count() and enable.first.is_visible():
                        return True
                except Exception:
                    pass
                return False

            for _attempt in range(2):
                dots = self._editor_header_dots_button()
                if dots is None:
                    break
                dots.click(force=True, timeout=waits().medium)
                self.page.wait_for_timeout(500)
                if not self._click_active_menu_edit():
                    self.page.keyboard.press("Escape")
                    continue
                self.page.wait_for_timeout(1000)
                if _dialog_open():
                    return True
            return False

    def _save_document_dialog(self):
        return self.page.locator(
            ".v-dialog--active, [role='dialog']"
        ).filter(has_text=re.compile(r"Save Document|Template Name", re.I))

    @log_method_exceptions
    def assign_hummingbird_properties(
        self, property_names: list[str]
    ) -> dict:
        """In open Save Document dialog: Enable Hummingbird Properties multi-select.

        Picks each ``property_names`` entry (e.g. Hamilton County, Rutland),
        then clicks modal Save. Caller should already have the dialog open
        via ``open_save_document_dialog_from_editor``.
        """
        result: dict = {"selected": [], "steps": []}
        with allure.step(
            f"Enable Hummingbird Properties: {', '.join(property_names)}"
        ):
            dialog = self._save_document_dialog()
            if dialog.count() == 0 or not dialog.first.is_visible():
                # Broaden: any visible dialog with Template Name
                dialog = self.page.locator(".v-dialog--active, [role='dialog']")
            if dialog.count() == 0:
                result["steps"].append("Save Document dialog missing")
                return result
            dlg = dialog.first

            # Enable Hummingbird Properties uses .v-input.hb-combobox (no input
            # placeholder). Non-Hummingbird is the second identical control.
            hb_label = dlg.get_by_text(
                re.compile(r"^Enable\s+Hummingbird\s+Propert", re.I)
            )
            trigger = None
            if hb_label.count():
                following = hb_label.first.locator(
                    "xpath=following::*[contains(@class,'hb-combobox') "
                    "or @role='combobox'][1]"
                )
                if following.count() and following.first.is_visible():
                    trigger = following.first
            if trigger is None:
                combos = dlg.locator(".v-input.hb-combobox")
                if combos.count():
                    trigger = combos.first
            if trigger is None:
                result["steps"].append("Select properties control missing")
                return result

            def _combo_input():
                inp = trigger.locator("input[type='text']")
                if inp.count():
                    return inp.first
                return trigger

            def _already_selected_text() -> str:
                try:
                    return (trigger.inner_text() or "").strip()
                except Exception:
                    return ""

            already_text = _already_selected_text()
            result["steps"].append(f"combo before: {already_text[:120]!r}")

            for prop_name in property_names:
                needle = prop_name.strip()
                if not needle:
                    continue
                # Bypass if chip / selected text already shows this property
                if needle.casefold() in already_text.casefold():
                    result["selected"].append(needle)
                    result["steps"].append(f"already selected {needle}")
                    continue

                trigger.click(force=True, timeout=waits().medium)
                self.page.wait_for_timeout(500)
                inp = _combo_input()
                try:
                    # Append filter text only — never Ctrl+A/fill (wipes chips)
                    inp.click(force=True)
                    self.page.keyboard.type(needle.split()[0], delay=30)
                except Exception:
                    self.page.keyboard.type(needle.split()[0], delay=30)
                self.page.wait_for_timeout(700)
                clicked = self.page.evaluate(
                    """(needle) => {
                      const nodes = document.querySelectorAll(
                        '[role=option], .menuable__content__active .v-list-item, '
                        + '.v-autocomplete__content .v-list-item, '
                        + '.v-menu__content .v-list-item'
                      );
                      const want = needle.toLowerCase();
                      let fallback = null;
                      for (const el of nodes) {
                        const raw = (el.innerText || '').trim().replace(/\\s+/g, ' ');
                        if (!raw || raw.length > 160) continue;
                        const low = raw.toLowerCase()
                          .replace(/check_box_outline_blank/g, ' unchecked ')
                          .replace(/check_box/g, ' checked ')
                          .replace(/\\s+/g, ' ')
                          .trim();
                        if (!el.offsetParent
                            && getComputedStyle(el).display === 'none') continue;
                        const matches = low.includes(want)
                          || (want.split(/\\s+/)[0].length >= 4
                              && low.includes(want.split(/\\s+/)[0])
                              && /storage|county|self|lightning/i.test(low));
                        if (!matches) continue;
                        // Already checked — bypass click
                        if (/\\bchecked\\b/.test(low) && !/unchecked/.test(low)) {
                          return {status: 'already', text: raw};
                        }
                        if (low.includes(want)) {
                          el.click();
                          return {status: 'selected', text: raw};
                        }
                        fallback = fallback || el;
                      }
                      if (fallback) {
                        const raw = (fallback.innerText || '').trim();
                        fallback.click();
                        return {status: 'selected', text: raw};
                      }
                      return null;
                    }""",
                    needle,
                )
                if isinstance(clicked, dict) and clicked.get("status") == "already":
                    result["selected"].append(needle)
                    result["steps"].append(f"already selected {needle}")
                elif isinstance(clicked, dict) and clicked.get("status") == "selected":
                    result["selected"].append(needle)
                    result["steps"].append(f"selected {clicked.get('text')}")
                    self.page.wait_for_timeout(500)
                elif clicked:
                    result["selected"].append(needle)
                    result["steps"].append(f"selected {clicked}")
                    self.page.wait_for_timeout(500)
                else:
                    result["steps"].append(f"missed {needle}")
                # Close dropdown between picks so chip state settles; reopen next
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(400)
                already_text = _already_selected_text()
                result["steps"].append(f"combo now: {already_text[:120]!r}")

            already_text = _already_selected_text()
            result["steps"].append(f"combo after: {already_text[:160]!r}")

            # Success if every requested property is present (selected or already)
            result["all_present"] = all(
                any(
                    p.casefold() in (s or "").casefold()
                    or (s or "").casefold() in p.casefold()
                    for s in result["selected"]
                )
                or p.casefold() in already_text.casefold()
                for p in property_names
                if p.strip()
            )

            save = dlg.get_by_role("button", name=re.compile(r"^Save$", re.I))
            if save.count() and save.first.is_visible():
                save.first.click(force=True, timeout=self.timeout)
                self.page.wait_for_timeout(1500)
                result["steps"].append("modal Save")
                result["saved"] = True
            else:
                result["steps"].append("modal Save missing")
                result["saved"] = False
        return result

    @log_method_exceptions
    def assign_template_to_properties(
        self, template_name: str, property_names: list[str]
    ) -> dict:
        """Corporate list: Edit template → ⋮ Edit → Enable Hummingbird Properties.

        Skips callers that pass an empty property list. Does not select a
        dashboard property — assignment is multi-property on the corporate template.
        """
        result: dict = {
            "name": template_name,
            "selected": [],
            "steps": [],
            "saved": False,
        }
        with allure.step(
            f"Assign template properties: {template_name} → {property_names}"
        ):
            self.open_document_templates()
            corp = self.page.get_by_role(
                "tab", name=re.compile(r"Corporate Settings", re.I)
            )
            if corp.count() and corp.first.is_visible():
                corp.first.click(force=True)
                self.page.wait_for_timeout(400)
            # Prefer list ⋮ → Edit (same path as live probe)
            self.search(template_name[:40])
            self.page.wait_for_timeout(600)
            row = self.page.locator("table tbody tr").filter(
                has_text=template_name
            ).first
            opened = False
            if row.count():
                menu = row.locator(
                    "button:has(.mdi-dots-vertical), "
                    "button:has(.mdi-dots-horizontal)"
                )
                if menu.count() == 0:
                    menu = row.locator("td").last.locator("button")
                if menu.count():
                    menu.first.click(force=True)
                    self.page.wait_for_timeout(400)
                    edit = self.page.locator(
                        ".menuable__content__active .v-list-item, "
                        "[role='menuitem']"
                    ).filter(has_text=re.compile(r"^Edit$", re.I))
                    if edit.count():
                        edit.first.click(force=True)
                        self.page.wait_for_timeout(1500)
                        opened = True
                        result["steps"].append("list ⋮ → Edit")
            if not opened and not self.open_template_by_name(template_name):
                result["steps"].append("row missing")
                return result
            if not opened:
                result["steps"].append("opened editor")

            if not self.open_save_document_dialog_from_editor():
                result["steps"].append("Save Document dialog failed")
                self.close_editor()
                return result
            result["steps"].append("editor ⋮ → Edit")

            assign = self.assign_hummingbird_properties(property_names)
            result["selected"] = list(assign.get("selected") or [])
            result["steps"].extend(assign.get("steps") or [])
            result["saved"] = bool(assign.get("saved"))

            # Persist editor if still open
            if self.save_template():
                result["steps"].append("Save Template")
            self.close_editor()
            self.search("")
        return result
