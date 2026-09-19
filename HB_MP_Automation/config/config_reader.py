from configparser import ConfigParser
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal


CONFIG_DIR = Path(__file__).resolve().parent
# Load order: runtime tuning → per-env property catalogs → credentials.
ENVIRONMENTS_FILE = CONFIG_DIR / "environments.ini"
PROPERTIES_DIR = CONFIG_DIR / "properties"
SECRETS_FILE = CONFIG_DIR / "secrets.ini"

PropertyRole = Literal["legacy", "two_step"]
_ROLE_SETTING = {
    "legacy": "legacy_property",
    "two_step": "two_step_property",
}


@dataclass(frozen=True)
class PropertyConfig:
    """One property from `[environment.key]` in config/properties/<env>.ini."""

    key: str
    # Distinct picker labels for the same property (lease config vs FMS vs HB).
    lease_configuration_property_name: str | None
    fms_property_name: str | None
    # HB Leads/Tenants/Quick Launch picker; falls back to lease config name.
    hb_property_name: str | None
    # Lead Management → Property Settings facility label (optional override).
    # APW fixture prefers lease_configuration_property_name with contains-match
    # (same as Lease Configuration); set this only when that is not enough.
    lead_management_property_settings_name: str | None
    # APW Advanced Reservations property override (True=ON, False=OFF).
    # None = skip ensuring the toggle for this property.
    apw_advance_reservation_enable: bool | None
    mp_state: str | None
    mp_city: str | None
    # Baseline FMS Initial Setup values restored after a test changes them.
    landing_page_layout: str | None
    value_tier_layout: str | None
    advance_reservation_days: int | None
    notes: str | None


@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    mp_base_url: str
    hb_base_url: str
    hb_username: str
    hb_password: str
    # Flat fields are Legacy (legacy_property) aliases for older callers.
    # Prefer legacy_property / two_step_property (or property_for_role) when
    # a suite must target a specific facility in a multi-property env.
    lease_configuration_property_name: str | None
    fms_property_name: str | None
    mp_state: str | None
    mp_city: str | None
    landing_page_layout: str | None
    value_tier_layout: str | None
    advance_reservation_days: int | None
    legacy_property: PropertyConfig | None
    two_step_property: PropertyConfig | None
    # Shared sandbox payment values from secrets.ini [payment].
    card_number: str | None
    card_expiry: str | None
    card_cvc: str | None
    card_zip_code: str | None
    ach_routing_number: str | None
    ach_account_number: str | None
    ach_account_type: str | None


@lru_cache(maxsize=1)
def load_config() -> ConfigParser:
    """Merge environments.ini, config/properties/*.ini, then secrets.ini."""
    config = ConfigParser()
    if not config.read(ENVIRONMENTS_FILE):
        raise FileNotFoundError(f"Configuration file not found: {ENVIRONMENTS_FILE}")
    if not PROPERTIES_DIR.is_dir():
        raise FileNotFoundError(f"Properties directory not found: {PROPERTIES_DIR}")
    property_files = sorted(PROPERTIES_DIR.glob("*.ini"))
    if not property_files:
        raise FileNotFoundError(
            f"No property catalogs in {PROPERTIES_DIR} - add one .ini per environment"
        )
    for path in property_files:
        if not config.read(path):
            raise FileNotFoundError(f"Could not read property catalog: {path}")
    if not config.read(SECRETS_FILE) and not SECRETS_FILE.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {SECRETS_FILE} - copy "
            f"{SECRETS_FILE.with_name('secrets.example.ini')} to it and fill it in"
        )
    return config


def _list_option(section, key: str) -> list[str]:
    raw = section.get(key, "")
    return [v.strip() for v in raw.split(",") if v.strip()]


def list_properties(config: ConfigParser, environment: str) -> list[str]:
    """Every property key this environment declares (its own
    `[environment.key]` subsections), from the environment section's own
    `properties` list.

    Dedupes so ``properties = Bellflower, Bellflower`` (same key used for
    both ``legacy_property`` and ``two_step_property``) only appears once.
    """
    environment = environment.strip()
    if not config.has_section(environment):
        return []
    return list(dict.fromkeys(_list_option(config[environment], "properties")))


def load_property(
    config: ConfigParser, environment: str, property_key: str
) -> PropertyConfig:
    """Load `[environment.property_key]` from config/properties/<env>.ini."""
    environment = environment.strip()
    section_name = f"{environment}.{property_key}"
    if not config.has_section(section_name):
        available = ", ".join(list_properties(config, environment)) or "none configured"
        raise ValueError(
            f"No property {property_key!r} configured for environment "
            f"{environment!r}. Available properties: {available}"
        )
    section = config[section_name]
    return PropertyConfig(
        key=property_key,
        lease_configuration_property_name=section.get(
            "lease_configuration_property_name", ""
        )
        or None,
        fms_property_name=section.get("fms_property_name", "") or None,
        hb_property_name=section.get("hb_property_name", "")
        or section.get("lease_configuration_property_name", "")
        or None,
        lead_management_property_settings_name=section.get(
            "lead_management_property_settings_name", ""
        )
        or None,
        apw_advance_reservation_enable=(
            section.getboolean("apw_advance_reservation_enable")
            if section.get("apw_advance_reservation_enable", "").strip()
            else None
        ),
        mp_state=section.get("mp_state", "") or None,
        mp_city=section.get("mp_city", "") or None,
        landing_page_layout=section.get("landing_page_layout", "") or None,
        value_tier_layout=section.get("value_tier_layout", "") or None,
        advance_reservation_days=section.getint(
            "advance_reservation_days", fallback=None
        ),
        notes=section.get("notes", "") or None,
    )


def property_for_role(
    config: ConfigParser, environment: str, role: PropertyRole
) -> PropertyConfig:
    """Resolve Legacy (`legacy_property`) or Two-Step (`two_step_property`)
    for an environment into its `[environment.key]` PropertyConfig."""
    environment = environment.strip()
    if not config.has_section(environment):
        available = config.get("application", "environments", fallback="")
        raise ValueError(
            f"Unknown environment '{environment}'. "
            f"Available environments: {available or 'none configured'}"
        )
    setting = _ROLE_SETTING[role]
    property_key = config.get(environment, setting, fallback="").strip()
    if not property_key:
        raise ValueError(
            f"No {setting} configured for environment {environment!r} "
            f"in config/properties/"
        )
    return load_property(config, environment, property_key)


@dataclass(frozen=True)
class GatewayConfig:
    """One HB Settings -> Payment Processing integration, from a
    `[gateway.key]` section: the method panel ("Credit Cards" or
    "ACH"), its merchant ("Tenant Payments", "Authorize.Net") and its HB
    fields - keys are HB's input names (api_key, public_api_key,
    account_number, deviceId, authnetLogin, authnetKey), values the
    gateway's secrets, so they're left out of the repr. `optional` names the
    fields that may stay empty when the integration is added, `not_compared`
    the fields whose value isn't checked against HB (still filled in when
    adding) - the section's comma-separated `optional` / `not_compared`
    keys. `billing_address_required` (the section's `billing_address =
    required`): the storefront payment must show and take a billing address
    for this gateway, else the test fails (Authorize.Net, user 2026-09-15)."""

    key: str
    method: str
    merchant: str
    fields: dict[str, str] = field(repr=False)
    optional: tuple[str, ...] = ()
    not_compared: tuple[str, ...] = ()
    billing_address_required: bool = False


def load_gateways(config: ConfigParser, profile: str) -> list[GatewayConfig]:
    """Every `[gateway.*]` section of this gateway profile - its `profile`
    key: "tenant_payments" or "non_tenant_payments", named after the rentals
    folder (tests/mp/rentals/<profile>_gateway) that uses it. The same
    details serve every environment and property (user, 2026-09-15)."""
    prefix = "gateway."
    gateways = []
    for section_name in config.sections():
        if not section_name.startswith(prefix):
            continue
        section = config[section_name]
        if section.get("profile", "").strip() != profile:
            continue
        gateways.append(
            GatewayConfig(
                key=section_name[len(prefix):],
                method=section.get("method", "").strip(),
                merchant=section.get("merchant", "").strip(),
                fields={
                    name: value.strip()
                    for name, value in section.items()
                    if name not in ("method", "merchant", "profile", "optional", "not_compared", "billing_address")
                },
                optional=tuple(name.lower() for name in _list_option(section, "optional")),
                not_compared=tuple(name.lower() for name in _list_option(section, "not_compared")),
                billing_address_required=section.get("billing_address", "").strip().lower() == "required",
            )
        )
    return gateways


def load_environment(config: ConfigParser, environment: str) -> EnvironmentConfig:
    environment = environment.strip()
    if not config.has_section(environment):
        available = config.get("application", "environments", fallback="")
        raise ValueError(
            f"Unknown environment '{environment}'. "
            f"Available environments: {available or 'none configured'}"
        )

    section = config[environment]
    mp_base_url = section.get("mp_base_url", "")
    hb_base_url = section.get("hb_base_url", "")
    hb_username = section.get("hb_username", "")
    hb_password = section.get("hb_password", "")
    if not mp_base_url:
        raise ValueError(f"mp_base_url is missing for environment '{environment}'")

    # An environment can declare its one active property's fields directly
    # on its own section (e.g. [stage], which only ever runs against one
    # property) or via `legacy_property` pointing at a
    # `[environment.key]` subsection (for environments tracking more than
    # one property - see list_properties/load_property). Direct fields
    # win when present.
    if section.get("lease_configuration_property_name"):
        legacy_property = PropertyConfig(
            key=environment,
            lease_configuration_property_name=section.get(
                "lease_configuration_property_name", ""
            )
            or None,
            fms_property_name=section.get("fms_property_name", "") or None,
            hb_property_name=section.get("hb_property_name", "")
            or section.get("lease_configuration_property_name", "")
            or None,
            lead_management_property_settings_name=section.get(
                "lead_management_property_settings_name", ""
            )
            or None,
            apw_advance_reservation_enable=(
                section.getboolean("apw_advance_reservation_enable")
                if section.get("apw_advance_reservation_enable", "").strip()
                else None
            ),
            mp_state=section.get("mp_state", "") or None,
            mp_city=section.get("mp_city", "") or None,
            landing_page_layout=section.get("landing_page_layout", "") or None,
            value_tier_layout=section.get("value_tier_layout", "") or None,
            advance_reservation_days=section.getint(
                "advance_reservation_days", fallback=None
            ),
            notes=section.get("notes", "") or None,
        )
    else:
        legacy_property_key = section.get("legacy_property", "") or None
        legacy_property = (
            load_property(config, environment, legacy_property_key)
            if legacy_property_key
            else None
        )

    two_step_property_key = section.get("two_step_property", "") or None
    two_step_property = (
        load_property(config, environment, two_step_property_key)
        if two_step_property_key
        else None
    )

    return EnvironmentConfig(
        name=environment,
        mp_base_url=mp_base_url.rstrip("/"),
        hb_base_url=hb_base_url.rstrip("/"),
        hb_username=hb_username,
        hb_password=hb_password,
        lease_configuration_property_name=(
            legacy_property.lease_configuration_property_name
            if legacy_property
            else None
        ),
        fms_property_name=(
            legacy_property.fms_property_name if legacy_property else None
        ),
        mp_state=legacy_property.mp_state if legacy_property else None,
        mp_city=legacy_property.mp_city if legacy_property else None,
        landing_page_layout=(
            legacy_property.landing_page_layout if legacy_property else None
        ),
        value_tier_layout=(
            legacy_property.value_tier_layout if legacy_property else None
        ),
        advance_reservation_days=(
            legacy_property.advance_reservation_days if legacy_property else None
        ),
        legacy_property=legacy_property,
        two_step_property=two_step_property,
        **_payment_fields(config),
    )


def _payment_fields(config: ConfigParser) -> dict:
    """Reads the merged `[payment]` section (from secrets.ini), attached to
    every EnvironmentConfig by load_environment() - same sandbox/test
    values regardless of environment, so kept as one shared section
    rather than duplicated per environment."""
    if not config.has_section("payment"):
        return {
            "card_number": None,
            "card_expiry": None,
            "card_cvc": None,
            "card_zip_code": None,
            "ach_routing_number": None,
            "ach_account_number": None,
            "ach_account_type": None,
        }
    section = config["payment"]
    return {
        "card_number": section.get("card_number", "") or None,
        "card_expiry": section.get("card_expiry", "") or None,
        "card_cvc": section.get("card_cvc", "") or None,
        "card_zip_code": section.get("card_zip_code", "") or None,
        "ach_routing_number": section.get("ach_routing_number", "") or None,
        "ach_account_number": section.get("ach_account_number", "") or None,
        "ach_account_type": section.get("ach_account_type", "") or None,
    }
