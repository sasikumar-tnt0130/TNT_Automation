"""Ensure Autotest Document Templates exist for rental document validations.

Creates **one Autotest template per live Template Category** (scraped from
Select Category). Specialist AZ-style bodies are used when the category
matches known types; otherwise a professional generic body is used.

Idempotent by template **name**. Signing mode stays in ``LeaseConfigurationSetup``.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from configparser import ConfigParser

import allure

from common_utils.document_template_bodies import html_for_category
from common_utils.document_template_docx import TEMPLATE_BRAND, write_template_docx
from common_utils.wrapper_methods import log_method_exceptions
from config.config_reader import EnvironmentConfig
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_document_templates_page import HBDocumentTemplatesPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

CORE_MERGE_TOKENS = [
    "Total Move-In Cost",
    "Property Security Deposit",
    "Tenant Insurance Premium",
    "Tenant Insurance Name",
    "Property Address Line 1",
    "Property Address Line 2",
    "Lease Signed Date",
]

# Default for charge-style categories (wine, discount, rent change, etc.).
GENERIC_CHARGE_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Property Security Deposit",
    "Tenant Insurance Premium",
    "Total Move-In Cost",
]

# Party/facility addenda: address + signed date only (Occupant name is
# display-only — never map Tenant Insurance Name onto it).
PARTY_FACILITY_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
]

# Key / security deposit documents.
DEPOSIT_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Property Security Deposit",
]

# Bank / ACH enrollment fields (live HB Merge Field names).
ACH_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Routing Number",
    "Bank Account Number",
    "Tenant Account Type",
    "Bank City",
    "Bank State",
    "Bank Postal Code",
]

# Driver's license document fields.
DRIVERS_LICENSE_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Driver License Number",
    "Driver License State",
    "Driver License Expiration Date",
]

# Insurance certificate fields.
INSURANCE_CERTIFICATE_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Tenant Insurance Name",
    "Tenant Insurance Policy Number",
    "Tenant Insurance Expiration Date",
    "Tenant Insurance Premium",
]

# Authorized-access addendum person contacts.
AUTHORIZED_ACCESS_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Authorized Access Person Name",
    "Authorized Access Person Phone",
]

# Vehicle / parking / valet / no-tag titled-property fields.
VEHICLE_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Vehicle License Plate Number",
    "Vehicle VIN",
    "Vehicle Make",
    "Vehicle Model",
]

# Military service addendum fields.
MILITARY_TOKENS = [
    "Property Address Line 1",
    "Lease Signed Date",
    "Military Branch Name",
    "Servicemember Name",
]

COVERAGE_TOKENS = [
    "Tenant Insurance Name",
    "Tenant Insurance Premium",
    "Protected Property",
    "Protection Plan Consent",
]

# Welcome-letter catalog only — intentional multi-domain token checklist.
CATALOG_TOKENS = CORE_MERGE_TOKENS + [
    "Protected Property",
    "Protection Plan Consent",
    "Notice Delivery Method",
    "Routing Number",
    "Bank Account Number",
    "Tenant Account Type",
    "Driver License Number",
    "Tenant Insurance Policy Number",
    "Vehicle License Plate Number",
    "Military Branch Name",
]

# Acknowledgement / waiver / shipment / move-out style categories — no
# charge or bank fields.
_PARTY_CATEGORY_NEEDLES = (
    "access liability",
    "authorization receive",
    "receive shipment",
    "move-out",
    "move out",
    "welcome card",
)

# Charge / fee style categories that keep deposit + premium + move-in cost.
_CHARGE_CATEGORY_NEEDLES = (
    "wine",
    "discount",
    "rent change",
    "delinquency",
    "lien",
)

# Optional richer overrides for known categories (name / tokens / signed).
# Keys are matched case-insensitively against the live category label.
CATEGORY_OVERRIDES: dict[str, dict] = {
    "lease": {
        "name_suffix": "Rental Agreement (Lease)",
        "tenant_file_name": "Lease Agreement",
        "signed": True,
        "tokens": CORE_MERGE_TOKENS,
    },
    "military": {
        "name_suffix": "Military Service Addendum",
        "tenant_file_name": "Military Waiver",
        "signed": True,
        "tokens": list(MILITARY_TOKENS),
    },
    "military tenant form": {
        "name_suffix": "Military Tenant Form",
        "tenant_file_name": "Military Waiver",
        "signed": True,
        "tokens": list(MILITARY_TOKENS),
    },
    "vehicle": {
        "name_suffix": "Vehicle Addendum",
        "tenant_file_name": "Vehicle Addendum",
        "signed": True,
        "preferred_types": ["Vehicle", "Vehicle Addendum", "Valet Addendum"],
        "tokens": list(VEHICLE_TOKENS),
    },
    "vehicle addendum": {
        "name_suffix": "Vehicle Addendum",
        "tenant_file_name": "Vehicle Addendum",
        "signed": True,
        "preferred_types": ["Vehicle", "Vehicle Addendum", "Valet Addendum"],
        "tokens": list(VEHICLE_TOKENS),
    },
    "valet addendum": {
        "name_suffix": "Valet Addendum",
        "tenant_file_name": "Vehicle Addendum",
        "signed": True,
        "preferred_types": ["Valet Addendum", "Vehicle", "Vehicle Addendum"],
        "tokens": list(VEHICLE_TOKENS),
    },
    "parking": {
        "name_suffix": "Parking",
        "tenant_file_name": "Parking",
        "signed": True,
        "tokens": list(VEHICLE_TOKENS),
    },
    "no tag": {
        "name_suffix": "No Tag",
        "tenant_file_name": "No Tag",
        "signed": True,
        "tokens": list(VEHICLE_TOKENS),
    },
    "key deposit agreement": {
        "name_suffix": "Key Deposit Agreement",
        "tenant_file_name": "Key Deposit Agreement",
        "signed": True,
        "tokens": list(DEPOSIT_TOKENS),
    },
    "access liability waiver": {
        "name_suffix": "Access Liability Waiver",
        "tenant_file_name": "Access Liability Waiver",
        "signed": True,
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "authorization receive shipment": {
        "name_suffix": "Authorization Receive Shipment",
        "tenant_file_name": "Authorization Receive Shipment",
        "signed": True,
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "move-out": {
        "name_suffix": "Move-out",
        "tenant_file_name": "Move-out",
        "signed": True,
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "move out": {
        "name_suffix": "Move-out",
        "tenant_file_name": "Move-out",
        "signed": True,
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "delinquency": {
        "name_suffix": "Delinquency",
        "tenant_file_name": "Delinquency",
        "signed": True,
        "tokens": list(GENERIC_CHARGE_TOKENS),
    },
    "lien": {
        "name_suffix": "Lien",
        "tenant_file_name": "Lien",
        "signed": True,
        "tokens": list(GENERIC_CHARGE_TOKENS),
    },
    "discount addendum": {
        "name_suffix": "Discount Addendum",
        "tenant_file_name": "Discount Addendum",
        "signed": True,
        "tokens": list(GENERIC_CHARGE_TOKENS),
    },
    "rent change": {
        "name_suffix": "Rent Change",
        "tenant_file_name": "Rent Change",
        "signed": True,
        "tokens": list(GENERIC_CHARGE_TOKENS),
    },
    "autopay": {
        "name_suffix": "Autopay Enrollment",
        "tenant_file_name": "Autopay Enrollment Document",
        "signed": True,
        "tokens": list(ACH_TOKENS),
    },
    "ach": {
        "name_suffix": "ACH",
        "tenant_file_name": "ACH",
        "signed": True,
        "tokens": list(ACH_TOKENS),
    },
    "auto debit enrollment form": {
        "name_suffix": "Auto Debit Enrollment Form",
        "tenant_file_name": "Auto Debit Enrollment Form",
        "signed": True,
        "tokens": list(ACH_TOKENS),
    },
    "drivers license": {
        "name_suffix": "Drivers License",
        "tenant_file_name": "Drivers License",
        "signed": True,
        "tokens": list(DRIVERS_LICENSE_TOKENS),
    },
    "insurance certificate": {
        "name_suffix": "Insurance Certificate",
        "tenant_file_name": "Insurance Certificate",
        "signed": True,
        "tokens": list(INSURANCE_CERTIFICATE_TOKENS),
    },
    "change of address notice": {
        "name_suffix": "Change of Address Notice",
        "tenant_file_name": "Change of address",
        "signed": True,
        "tokens": [
            "Property Address Line 1",
            "Property Address Line 2",
        ],
    },
    "enroll coverage": {
        "name_suffix": "Coverage Enrollment",
        "tenant_file_name": "Enroll Coverage",
        "signed": True,
        "tokens": COVERAGE_TOKENS,
    },
    "coverage enrollment": {
        "name_suffix": "Coverage Enrollment",
        "tenant_file_name": "Enroll Coverage",
        "signed": True,
        "tokens": COVERAGE_TOKENS,
    },
    "deny coverage": {
        "name_suffix": "Coverage Decline",
        "tenant_file_name": "Deny Coverage",
        "signed": True,
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "coverage decline": {
        "name_suffix": "Coverage Decline",
        "tenant_file_name": "Deny Coverage",
        "signed": True,
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "authorized access addendum": {
        "name_suffix": "Authorized Access Addendum",
        "tenant_file_name": "Authorized Access Addendum",
        "signed": True,
        "tokens": list(AUTHORIZED_ACCESS_TOKENS),
    },
    "other (with signature)": {
        "name_suffix": "Other Signed Acknowledgement",
        "tenant_file_name": "Other (With Signature)",
        "signed": True,
        "preferred_types": [
            "Other (With Signature)",
            "Other",
            "Other (Without Signature)",
        ],
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "other (without signature)": {
        "name_suffix": "Other (Without Signature)",
        "tenant_file_name": "Other (Without Signature)",
        "signed": False,
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "welcome letter": {
        "name_suffix": "Merge Field Catalog",
        "tenant_file_name": "Welcome Letter",
        "signed": False,
        "preferred_types": ["Welcome Letter", "Welcome Card", "Welcome"],
        "tokens": list(CATALOG_TOKENS),
    },
    "welcome card": {
        "name_suffix": "Welcome Card",
        "tenant_file_name": "Welcome Card",
        "signed": False,
        "preferred_types": ["Welcome Card", "Welcome Letter"],
        "tokens": list(PARTY_FACILITY_TOKENS),
    },
    "wine": {
        "name_suffix": "Wine Addendum",
        "tenant_file_name": "Wine Addendum",
        "signed": True,
        "tokens": list(GENERIC_CHARGE_TOKENS),
    },
}


def tokens_for_category(category: str) -> list[str]:
    """Meaningful HB Merge Field tokens for a template category.

    Only returns tokens that have intentional matching labels in
    ``html_for_category`` for that category. Never maps insurance-plan
    tokens onto Occupant / Tenant Name.
    """
    key = _category_key(category)
    if not key:
        return list(GENERIC_CHARGE_TOKENS)

    ov = CATEGORY_OVERRIDES.get(key)
    if ov and ov.get("tokens") is not None:
        return list(ov["tokens"])

    # Fuzzy: override key contained in category (or vice versa).
    # Require word-ish boundaries so short keys like "ach" do not match
    # "Authorization Receive Shipment".
    best: dict | None = None
    best_len = -1
    for k, v in CATEGORY_OVERRIDES.items():
        if v.get("tokens") is None:
            continue
        if _key_matches(key, k) and len(k) > best_len:
            best = v
            best_len = len(k)
    if best is not None:
        return list(best["tokens"])

    # Body-matcher heuristics for categories without an explicit override.
    if any(n in key for n in ("military",)):
        return list(MILITARY_TOKENS)
    if any(n in key for n in ("vehicle", "valet", "parking", "no tag")):
        return list(VEHICLE_TOKENS)
    if "key deposit" in key or (key.startswith("key ") and "deposit" in key):
        return list(DEPOSIT_TOKENS)
    if "enroll coverage" in key or "coverage enrollment" in key or (
        "enroll" in key and "coverage" in key
    ):
        return list(COVERAGE_TOKENS)
    if "deny coverage" in key or "coverage decline" in key or (
        key.startswith("deny") and "coverage" in key
    ):
        return list(PARTY_FACILITY_TOKENS)
    if "authorized access" in key:
        return list(AUTHORIZED_ACCESS_TOKENS)
    if "auto debit" in key or "autopay" in key or _key_matches(key, "ach"):
        return list(ACH_TOKENS)
    if "driver" in key and "license" in key:
        return list(DRIVERS_LICENSE_TOKENS)
    if "insurance certificate" in key or (
        "insurance" in key and "certificate" in key
    ):
        return list(INSURANCE_CERTIFICATE_TOKENS)
    if any(n in key for n in _PARTY_CATEGORY_NEEDLES):
        return list(PARTY_FACILITY_TOKENS)
    if any(n in key for n in _CHARGE_CATEGORY_NEEDLES):
        return list(GENERIC_CHARGE_TOKENS)
    if key.startswith("other") or "other (" in key:
        return list(PARTY_FACILITY_TOKENS)
    if "welcome" in key:
        return list(CATALOG_TOKENS) if "letter" in key else list(PARTY_FACILITY_TOKENS)
    if "merge field catalog" in key or key.endswith("catalog"):
        return list(CATALOG_TOKENS)
    if key == "lease" or key.startswith("lease ") or key.endswith(" lease"):
        return list(CORE_MERGE_TOKENS)

    # Unknown categories: party-only (never dump charge/bank fields).
    return list(PARTY_FACILITY_TOKENS)


# Full Template Category catalog (stage walk + prior scrapes). Merged with
# any types seen on the Document Templates grid so new categories are picked up.
KNOWN_TEMPLATE_CATEGORIES: list[str] = [
    "Access Liability Waiver",
    "ACH",
    "Authorization Receive Shipment",
    "Authorized Access Addendum",
    "Auto Debit Enrollment Form",
    "Autopay",
    "Change of Address Notice",
    "Change Of Address Notice",
    "Delinquency",
    "Deny Coverage",
    "Discount Addendum",
    "Drivers License",
    "Enroll Coverage",
    "Insurance Certificate",
    "Key Deposit Agreement",
    "Lease",
    "Lien",
    "Military",
    "Military Tenant Form",
    "Move-out",
    "Move-Out",
    "No Tag",
    "Other (With Signature)",
    "Other (Without Signature)",
    "Rent Change",
    "Valet Addendum",
    "Vehicle",
    "Vehicle Addendum",
    "Welcome Card",
    "Welcome Letter",
    "Wine Addendum",
]


def _category_key(label: str) -> str:
    """Normalize category labels so 'Deny Coverage' == 'Deny-Coverage'."""
    return re.sub(r"[\s\-_/]+", " ", (label or "").strip()).lower()


def _key_matches(category_key: str, override_key: str) -> bool:
    """True when override applies — word-boundary aware for short keys."""
    cat = (category_key or "").strip().lower()
    ov = (override_key or "").strip().lower()
    if not cat or not ov:
        return False
    if cat == ov or cat.startswith(ov + " ") or cat.endswith(" " + ov):
        return True
    if f" {ov} " in f" {cat} ":
        return True
    # Longer overrides may be substrings (e.g. "change of address" in notice).
    if len(ov) >= 8 and (ov in cat or cat in ov):
        return True
    return False


def _is_plausible_category(label: str) -> bool:
    """Drop grid noise (slugs, empty, overly long)."""
    text = (label or "").strip()
    if not text or len(text) > 60:
        return False
    if text.lower() in ("select category", "type", "category", "notag"):
        return False
    known_keys = {_category_key(k) for k in KNOWN_TEMPLATE_CATEGORIES}
    if _category_key(text) in known_keys:
        return True
    # Prefer human labels; drop slug-only grid noise (Deny-Coverage).
    if "-" in text and " " not in text:
        return False
    return True


def _safe_name_fragment(category: str) -> str:
    cleaned = re.sub(r"[^\w\s\-()]+", "", category).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:70] or "Category"


def _override_for(category: str) -> dict:
    key = category.strip().lower()
    if key in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[key]
    return {}


def _spec_for_category(category: str) -> dict:
    """Build create/refresh spec for one live Template Category."""
    ov = _override_for(category)
    suffix = ov.get("name_suffix") or _safe_name_fragment(category)
    name = f"{TEMPLATE_BRAND} - {suffix}"
    # Avoid duplicate names when two categories share the same override suffix.
    if not ov.get("name_suffix"):
        name = f"{TEMPLATE_BRAND} - {_safe_name_fragment(category)}"
    elif suffix.lower() != category.strip().lower():
        # Keep override display name for known types.
        name = f"{TEMPLATE_BRAND} - {suffix}"
    tokens = tokens_for_category(category)
    signed = bool(ov.get("signed", True))
    # Welcome / letter-style unsigned
    if "welcome" in category.lower() or "letter" in category.lower():
        if "signed" not in ov:
            signed = False
    return {
        "name": name,
        "type": category,
        "preferred_types": list(ov.get("preferred_types") or [category]),
        "signed": signed,
        "tenant_file_name": ov.get("tenant_file_name") or category,
        "intro_html": html_for_category(category),
        "tokens": tokens,
    }


def _specs_for_all_categories(categories: list[str]) -> list[dict]:
    """One Autotest template per category; unique names if collisions."""
    specs: list[dict] = []
    used_names: set[str] = set()
    used_keys: set[str] = set()
    for cat in categories:
        if not cat or cat.lower() == "select category":
            continue
        # Bare "Other" is not a Select Category option on stage.
        if cat.strip().lower() == "other":
            continue
        key = _category_key(cat)
        # Vehicle / Vehicle Addendum share one Autotest template.
        if key in ("vehicle addendum",) and "vehicle" in used_keys:
            continue
        if key in used_keys and key not in ("other with signature", "other without signature"):
            # Already covered by a normalized sibling.
            continue
        spec = _spec_for_category(cat)
        base = spec["name"]
        if base in used_names:
            # Same display name already queued (e.g. Vehicle + Vehicle Addendum).
            continue
        used_names.add(spec["name"])
        used_keys.add(key)
        specs.append(spec)
    return specs


def _pick_type(available: list[str], spec: dict) -> str:
    preferred = list(spec.get("preferred_types") or []) + [spec["type"]]
    lower = {a.lower(): a for a in available}
    for want in preferred:
        if want.lower() in lower:
            return lower[want.lower()]
        for a in available:
            if want.lower() in a.lower():
                return a
    return spec["type"]


class DocumentTemplatesSetup:
    """Ensure professional Autotest Document Templates for every category."""

    @log_method_exceptions
    def __init__(
        self,
        hb_login_page: HBLoginPage,
        environment_config: EnvironmentConfig,
        app_config: ConfigParser,
        *,
        hb_property_name: str | None = None,
    ) -> None:
        self.hb_login_page = hb_login_page
        self.environment_config = environment_config
        self.app_config = app_config
        legacy = environment_config.legacy_property
        self.hb_property_name = (
            hb_property_name
            or (legacy.hb_property_name if legacy else None)
            or environment_config.lease_configuration_property_name
        )
        self.timeout = app_config.getint("browser", "timeout")
        self.nav = HBSettingsNavigation(hb_login_page.page, self.timeout)
        self.docs = HBDocumentTemplatesPage(
            hb_login_page.page, self.timeout, self.nav
        )

    @log_method_exceptions
    def _ensure_dashboard_property(self) -> None:
        if not self.hb_property_name:
            return
        with allure.step(
            f"HB dashboard property for Document Templates: {self.hb_property_name}"
        ):
            self.hb_login_page.ensure_on_dashboard()
            HBQuickLaunchPage(self.hb_login_page.page, self.timeout).select_property(
                self.hb_property_name
            )

    @log_method_exceptions
    def _refresh_template_body(self, spec: dict) -> dict:
        """Open an existing Autotest template and rewrite professional body + tokens."""
        name = spec["name"]
        result: dict = {
            "name": name,
            "type": spec["type"],
            "saved": False,
            "already_existed": True,
            "inserted_tokens": [],
            "steps": ["refresh existing"],
            "tenant_file_name": spec.get("tenant_file_name"),
        }
        if not self.docs.open_template_by_name(name):
            result["steps"].append("open failed")
            return result
        result["steps"].append("opened")
        self.docs.set_editor_html(spec["intro_html"])
        result["steps"].append("intro")
        inserted_result = self.docs.insert_merge_fields(list(spec.get("tokens") or []))
        inserted = (
            inserted_result.get("inserted", [])
            if isinstance(inserted_result, dict)
            else list(inserted_result or [])
        )
        result["inserted_tokens"] = inserted
        result["skipped_tokens"] = (
            inserted_result.get("skipped", [])
            if isinstance(inserted_result, dict)
            else []
        )
        result["steps"].append(f"tokens={inserted}")
        if self.docs.save_template():
            result["saved"] = True
            result["steps"].append("Save Template body")
        else:
            result["steps"].append("Save Template missing")
        self.docs.close_editor()
        return result

    @log_method_exceptions
    def ensure_project_templates(
        self,
        specs: list[dict] | None = None,
        *,
        refresh_existing: bool = False,
        scrape_categories: bool = False,
        progress: Callable[..., None] | None = None,
    ) -> list[dict]:
        """Create missing Autotest templates for every Template Category.

        Categories come from ``KNOWN_TEMPLATE_CATEGORIES`` plus types on the
        Document Templates grid. Live Select Category scrape is optional
        (``scrape_categories=True``) — virtualized menus often hang.
        """
        log = progress or (lambda *_a, **_k: None)
        results: list[dict] = []
        with allure.step(
            "Ensure Autotest Document Templates (all categories)"
        ):
            self.hb_login_page.ensure_logged_in()
            self._ensure_dashboard_property()

            available: list[str] = []
            if scrape_categories:
                log("Scraping Template Categories (live Select Category)…")
                try:
                    available = self.docs.scrape_type_options()
                except Exception as exc:
                    allure.attach(
                        repr(exc)[:500],
                        name="category-scrape-error",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    log(f"Scrape failed: {exc}"[:200])

            log("Reading categories from Document Templates grid…")
            grid_types: set[str] = set()
            try:
                for row in self.docs.list_rows():
                    if row.get("type"):
                        grid_types.add(str(row["type"]).strip())
            except Exception as exc:
                log(f"Grid read failed: {exc}"[:200])

            merged: dict[str, str] = {}  # key → display label
            for src in (KNOWN_TEMPLATE_CATEGORIES, available, sorted(grid_types)):
                for cat in src:
                    if not _is_plausible_category(cat):
                        continue
                    key = _category_key(cat)
                    if not key:
                        continue
                    # Prefer spaced/known spelling over hyphenated grid noise.
                    if key not in merged:
                        merged[key] = cat.strip()
                    elif "-" in merged[key] and " " in cat:
                        merged[key] = cat.strip()
            available = sorted(merged.values(), key=str.lower)
            log(f"Found {len(available)} categories")
            for cat in available:
                log(f"  category: {cat}")
            allure.attach(
                "\n".join(available) or "(none)",
                name="document-template-types",
                attachment_type=allure.attachment_type.TEXT,
            )

            if specs is None:
                specs = _specs_for_all_categories(available)
                lease_cats = [c for c in available if c.strip().lower() == "lease"]
                if lease_cats:
                    extra = _spec_for_category(lease_cats[0])
                    extra["name"] = (
                        "HB_MP_Automation - Superlease-Style Agreement (Lease)"
                    )
                    extra["intro_html"] = html_for_category("Super Lease")
                    extra["tenant_file_name"] = "Superlease"
                    if extra["name"] not in {s["name"] for s in specs}:
                        specs.append(extra)

            global PROJECT_TEMPLATES
            PROJECT_TEMPLATES = list(specs)
            log(f"Ensuring {len(specs)} Autotest templates…")

            existing = {r["name"] for r in self.docs.list_rows()}
            for idx, spec in enumerate(specs, start=1):
                name = spec["name"]
                type_label = _pick_type(available, spec)
                log(f"[{idx}/{len(specs)}] {type_label} → {name}")
                if name in existing:
                    if refresh_existing:
                        with allure.step(
                            f"Refresh body on existing template: {name}"
                        ):
                            refreshed = self._refresh_template_body(spec)
                            results.append(refreshed)
                            log(f"  refreshed saved={refreshed.get('saved')}")
                    else:
                        results.append(
                            {
                                "name": name,
                                "type": type_label,
                                "saved": True,
                                "already_existed": True,
                                "inserted_tokens": [],
                                "steps": ["skipped existing"],
                                "tenant_file_name": spec.get("tenant_file_name"),
                            }
                        )
                        log("  already exists — skipped")
                    continue
                docx_path = write_template_docx(
                    name,
                    spec["intro_html"],
                    list(spec.get("tokens") or []),
                )
                try:
                    result = self.docs.create_template(
                        name=name,
                        type_label=type_label,
                        signed=bool(spec.get("signed")),
                        intro_html=spec["intro_html"],
                        tokens=list(spec.get("tokens") or []),
                        docx_path=docx_path,
                        preferred_types=list(spec.get("preferred_types") or []),
                    )
                except Exception as exc:
                    allure.attach(
                        repr(exc)[:800],
                        name=f"create-failed-{name[:40]}",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    self.docs.close_editor()
                    result = {
                        "name": name,
                        "type": type_label,
                        "saved": False,
                        "already_existed": False,
                        "inserted_tokens": [],
                        "steps": [f"error: {type(exc).__name__}: {exc}"[:300]],
                        "tenant_file_name": spec.get("tenant_file_name"),
                    }
                    results.append(result)
                    log(f"  ERROR {type(exc).__name__}: {exc}"[:200])
                    continue
                result["already_existed"] = False
                result["tenant_file_name"] = spec.get("tenant_file_name")
                results.append(result)
                log(
                    f"  saved={result.get('saved')} "
                    f"tokens={result.get('inserted_tokens')} "
                    f"steps={result.get('steps')}"
                )
                if result.get("saved") or "saved shell" in (result.get("steps") or []):
                    existing.add(name)

            opened = self.docs.open_property_settings_tab()
            allure.attach(
                (
                    "Property Settings tab opened — assign Autotest templates "
                    f"to {self.hb_property_name} so rentals use them."
                    if opened
                    else "Property Settings tab not opened; templates remain "
                    "in the corporate library until assigned."
                ),
                name="document-templates-assignment-note",
                attachment_type=allure.attachment_type.TEXT,
            )
            by_cat: dict[str, list[str]] = {}
            for r in results:
                by_cat.setdefault(str(r.get("type") or "?"), []).append(
                    f"{r.get('name')}: saved={r.get('saved')} "
                    f"existed={r.get('already_existed')}"
                )
            summary_lines = []
            for cat in sorted(by_cat, key=str.lower):
                summary_lines.append(f"[{cat}]")
                summary_lines.extend(f"  {line}" for line in by_cat[cat])
            allure.attach(
                "\n".join(summary_lines) or "(none)",
                name="autotest-document-templates-ensure-by-category",
                attachment_type=allure.attachment_type.TEXT,
            )
            self.nav.close_settings_panel()
        return results
