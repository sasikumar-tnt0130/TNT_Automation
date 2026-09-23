"""Ensure HB Manage Coverage is configured for automation properties.

Opens Settings → Coverage, keeps Coverage Option Types **Disabled**,
ensures an automation coverage option exists per space type
(Storage, Parking, …), and visits Property Settings for legacy +
two-step HB properties.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

import allure

from common_utils.wrapper_methods import log_method_exceptions
from config.config_reader import EnvironmentConfig
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_coverage_page import HBCoveragePage

DEFAULT_OPTION_NAME = "HB_MP_Automation Coverage"
DEFAULT_PREMIUM = "8.00"
# Preferred space types to configure when present in Select Space Type.
DEFAULT_SPACE_CATEGORIES = ("Storage", "Parking")


class CoverageSetup:
    """Hummingbird Manage Coverage setup for rental / document validations."""

    @log_method_exceptions
    def __init__(
        self,
        hb_login_page: HBLoginPage,
        environment: EnvironmentConfig,
        timeout: float,
    ) -> None:
        self.hb_login_page = hb_login_page
        self.environment = environment
        self.timeout = timeout
        self.nav = HBSettingsNavigation(hb_login_page.page, timeout)
        self.coverage = HBCoveragePage(hb_login_page.page, timeout, self.nav)

    def _target_properties(self) -> list[dict]:
        """Property targets with Select Property aliases.

        Coverage / Settings ``Select Property`` uses lease/facility display
        names (e.g. Hamilton Self Storage), not always ``hb_property_name``
        (Hamilton County).
        """
        out: list[dict] = []
        seen: set[str] = set()
        for role in (self.environment.legacy_property, self.environment.two_step_property):
            if not role:
                continue
            aliases: list[str] = []
            for cand in (
                role.lease_configuration_property_name,
                role.hb_property_name,
                role.fms_property_name,
            ):
                c = (cand or "").strip()
                if c and c.casefold() not in {a.casefold() for a in aliases}:
                    aliases.append(c)
            if not aliases:
                continue
            key = aliases[0].casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "label": aliases[0],
                    "aliases": aliases,
                    "hb_property_name": role.hb_property_name,
                }
            )
        return out

    def _option_name_for_space(self, base: str, space_category: str) -> str:
        """Distinct option name per space type (Storage / Parking / …)."""
        base = (base or DEFAULT_OPTION_NAME).strip()
        space = (space_category or "").strip()
        if not space:
            return base
        # Avoid "… Coverage - Storage - Storage" if caller already baked it in.
        if space.casefold() in base.casefold():
            return base
        return f"{base} - {space}"

    def resolve_space_categories(
        self,
        requested: Sequence[str] | None = None,
    ) -> list[str]:
        """Intersect requested types with live Select Space Type options."""
        wanted = [
            s.strip()
            for s in (requested or DEFAULT_SPACE_CATEGORIES)
            if s and str(s).strip()
        ]
        if not wanted:
            wanted = list(DEFAULT_SPACE_CATEGORIES)
        available = self.coverage.list_space_types()
        self._last_space_types = list(available)
        if not available:
            # Dropdown empty / flaky — still try requested names.
            return wanted
        resolved: list[str] = []
        avail_map = {a.casefold(): a for a in available}
        for w in wanted:
            hit = avail_map.get(w.casefold())
            if hit and hit not in resolved:
                resolved.append(hit)
        # If none of the preferred types exist, configure whatever is available.
        if not resolved:
            resolved = list(available)
        return resolved

    @log_method_exceptions
    def ensure_coverage_for_space(
        self,
        space_category: str,
        *,
        option_name: str = DEFAULT_OPTION_NAME,
        premium: str = DEFAULT_PREMIUM,
        progress: Callable[..., None] | None = None,
    ) -> dict:
        """Configure corporate coverage for one space type (Storage / Parking)."""
        log = progress or (lambda *_a, **_k: None)
        named = self._option_name_for_space(option_name, space_category)
        entry: dict = {
            "space_category": space_category,
            "option_name": named,
            "space_category_selected": False,
            "option": {},
            "steps": [],
        }
        with allure.step(f"CoverageSetup space={space_category}"):
            cat_ok = self.coverage.select_space_category(space_category)
            entry["space_category_selected"] = cat_ok
            entry["steps"].append(f"space_category={space_category} ok={cat_ok}")
            log(f"[{space_category}] selected={cat_ok}")
            if not cat_ok:
                entry["steps"].append("skip — space type not selectable")
                return entry

            disabled = self.coverage.disable_coverage_option_types()
            entry["option_types_disabled"] = disabled
            entry["steps"].append(f"option_types_disabled={disabled}")
            log(f"[{space_category}] option types disabled={disabled}")

            opt = self.coverage.ensure_coverage_option(
                named,
                premium=premium,
                enable_properties=[
                    a
                    for p in self._target_properties()
                    for a in p.get("aliases", [])[:1]
                ],
            )
            entry["option"] = opt
            entry["steps"].append(f"option={opt}")
            log(
                f"[{space_category}] option "
                f"existed={opt.get('existed')} added={opt.get('added')}"
            )
        return entry

    @log_method_exceptions
    def ensure_coverage(
        self,
        *,
        option_name: str = DEFAULT_OPTION_NAME,
        premium: str = DEFAULT_PREMIUM,
        space_category: str | Sequence[str] = DEFAULT_SPACE_CATEGORIES,
        progress: Callable[..., None] | None = None,
    ) -> dict:
        """End-to-end Manage Coverage ensure for corporate + properties.

        ``space_category`` may be a single type (``\"Storage\"``) or a sequence
        (``(\"Storage\", \"Parking\")``). Preferred defaults are Storage + Parking.
        """
        log = progress or (lambda *_a, **_k: None)
        if isinstance(space_category, str):
            requested: list[str] = [space_category]
        else:
            requested = list(space_category)

        result: dict = {
            "option_name": option_name,
            "space_categories_requested": requested,
            "space_categories": [],
            "corporate_by_space": [],
            "corporate": {},
            "option": {},
            "properties": [],
            "steps": [],
        }
        with allure.step("CoverageSetup.ensure_coverage"):
            self.coverage.open_coverage()
            result["steps"].append("opened Manage Coverage")
            log("opened Manage Coverage")

            spaces = self.resolve_space_categories(requested)
            result["space_categories"] = spaces
            # Reuse types from resolve (already listed) — avoid a second dropdown open.
            result["space_types_available"] = list(
                getattr(self, "_last_space_types", None) or spaces
            )
            result["steps"].append(f"space_categories={spaces}")
            log(f"space categories → {spaces}")

            for space in spaces:
                entry = self.ensure_coverage_for_space(
                    space,
                    option_name=option_name,
                    premium=premium,
                    progress=progress,
                )
                result["corporate_by_space"].append(entry)
                result["steps"].extend(
                    f"[{space}] {s}" for s in entry.get("steps", [])
                )

            # Backward-compatible summary from the first successful space.
            first_ok = next(
                (
                    e
                    for e in result["corporate_by_space"]
                    if e.get("space_category_selected")
                ),
                result["corporate_by_space"][0]
                if result["corporate_by_space"]
                else {},
            )
            result["corporate"] = {
                "space_category": first_ok.get("space_category"),
                "space_category_selected": first_ok.get(
                    "space_category_selected"
                ),
                "option_types_disabled": first_ok.get("option_types_disabled"),
                "option_types_enabled": (
                    False
                    if first_ok.get("option_types_disabled")
                    else self.coverage.coverage_option_types_enabled()
                ),
            }
            result["option"] = first_ok.get("option") or {}

            # Reset UI before Property Settings — corporate Coverage Options /
            # Add dialog leftovers clear the Property Select Property control.
            try:
                self.coverage._close_active_dialogs()
                self.coverage.open_coverage()
                self.coverage.open_corporate_settings()
                self.coverage._close_active_dialogs()
            except Exception as exc:
                result["steps"].append(f"pre_property_reset={exc!r}"[:120])

            for prop in self._target_properties():
                label = prop["label"]
                aliases = prop["aliases"]
                entry_p: dict = {
                    "property": label,
                    "aliases": aliases,
                    "hb_property_name": prop.get("hb_property_name"),
                    "selected": False,
                    "matched_alias": None,
                    "steps": [],
                    "by_space": [],
                    "coverage_options_ok": False,
                }
                # Fresh Coverage → Property Settings before each property.
                selected, matched = False, None
                for attempt in range(3):
                    try:
                        self.coverage._close_active_dialogs()
                        self.coverage.open_coverage()
                        self.coverage.open_property_settings()
                        selected, matched = (
                            self.coverage.select_coverage_property_aliases(
                                aliases
                            )
                        )
                        if selected:
                            break
                        entry_p["steps"].append(
                            f"select_attempt={attempt + 1} failed"
                        )
                        self.coverage.page.wait_for_timeout(800)
                    except Exception as exc:
                        entry_p["steps"].append(
                            f"nav_error={exc!r}"[:120]
                        )
                        self.coverage.page.wait_for_timeout(800)
                entry_p["selected"] = selected
                entry_p["matched_alias"] = matched
                entry_p["steps"].append(
                    f"selected={selected} matched={matched}"
                )
                log(
                    f"property {label} selected={selected} matched={matched}"
                )
                if not selected:
                    result["properties"].append(entry_p)
                    result["steps"].append(
                        f"property {label}: {entry_p['steps']}"
                    )
                    continue

                # Stay on Property Settings and verify Coverage Options
                # for each space type (do NOT bounce back to Corporate).
                # Coverage Options rail clears Select Property — re-select
                # with navigate=False. Space Type is configured on Settings.
                spaces_ok = 0
                for space in spaces:
                    named = self._option_name_for_space(option_name, space)
                    space_entry: dict = {
                        "space_category": space,
                        "option_name": named,
                        "space_selected": False,
                        "option_types_disabled": None,
                        "use_corporate_default": None,
                        "option_present": False,
                        "options": [],
                        "steps": [],
                    }
                    with allure.step(
                        f"Property {label} → Coverage Options ({space})"
                    ):
                        try:
                            self.coverage.open_property_settings()
                        except Exception as exc:
                            space_entry["steps"].append(
                                f"nav_err={exc!r}"[:100]
                            )

                        # Settings rail: property + space + option types
                        prop_ok = self.coverage.select_coverage_property(
                            matched or label, navigate=False
                        )
                        space_ok = self.coverage.select_space_category(
                            space, scope="property"
                        )
                        space_entry["space_selected"] = space_ok
                        space_entry["steps"].append(
                            f"settings_prop={prop_ok} space_selected={space_ok}"
                        )
                        if not (prop_ok and space_ok):
                            entry_p["by_space"].append(space_entry)
                            continue

                        disabled = self.coverage.disable_coverage_option_types(
                            scope="property"
                        )
                        space_entry["option_types_disabled"] = disabled
                        space_entry["use_corporate_default"] = (
                            self.coverage.property_uses_corporate_default()
                        )
                        space_entry["steps"].append(
                            f"option_types_disabled={disabled} "
                            f"use_corporate_default="
                            f"{space_entry['use_corporate_default']}"
                        )

                        # Coverage Options: re-select property only (space
                        # type stays from Settings; do not click Settings rail).
                        self.coverage.open_coverage_options(reopen=False)
                        re_ok = self.coverage.select_coverage_property(
                            matched or label, navigate=False
                        )
                        space_entry["steps"].append(
                            f"options_prop_reselect={re_ok}"
                        )
                        if not re_ok:
                            entry_p["by_space"].append(space_entry)
                            continue

                        self.coverage.page.wait_for_timeout(800)
                        opts = self.coverage.list_coverage_option_names(
                            reopen=False
                        )
                        space_entry["options"] = opts[:40]
                        present = self.coverage.coverage_option_exists(named)
                        if (
                            not present
                            and space_entry.get("use_corporate_default")
                        ):
                            # Corporate default inherits corporate options.
                            present = True
                            space_entry["steps"].append(
                                "corporate_default_inherits_options"
                            )
                        space_entry["option_present"] = present
                        space_entry["steps"].append(
                            f"option_present={present} name={named} "
                            f"option_rows={len(opts)}"
                        )
                        log(
                            f"  [{label}/{space}] option_present={present} "
                            f"types_disabled={disabled} "
                            f"corp_default="
                            f"{space_entry['use_corporate_default']} "
                            f"rows={len(opts)}"
                        )
                        if re_ok and space_ok and disabled:
                            spaces_ok += 1
                    entry_p["by_space"].append(space_entry)

                entry_p["coverage_options_ok"] = spaces_ok == len(spaces) and bool(
                    spaces
                )
                entry_p["steps"].append(
                    f"coverage_options_ok={entry_p['coverage_options_ok']} "
                    f"({spaces_ok}/{len(spaces)})"
                )
                result["properties"].append(entry_p)
                result["steps"].append(f"property {label}: {entry_p['steps']}")

            self.nav.close_settings_panel()
        return result
