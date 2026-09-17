from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


CONFIG_FILE = Path(__file__).resolve().parent / "environments.ini"


@dataclass(frozen=True)
class PropertyConfig:
    """One property's identity, read from its own `[environment.key]`
    subsection in environments.ini. A single environment can have more
    than one property section (e.g. stage has both hamilton_garden_grove
    and lightning_rutland) - see load_property/list_properties."""

    key: str
    # HB's Lease Configuration & State Compliance picker and its FMS
    # Initial Setup picker show different display text for the same
    # physical property (confirmed live, e.g. "Hamilton Self Storage" vs
    # "GARDEN GROVE") - both are kept so callers always use the
    # picker-specific name instead of guessing one works for both.
    lease_configuration_property_name: str | None
    fms_property_name: str | None
    # HB's property picker (Leads/Tenants/Quick Launch #search-box) shows
    # yet another name on stage ("Rutland", "Hamilton County") - optional
    # `hb_property_name` key, falling back to the lease configuration name
    # (which matches the picker on uat_storoutlet).
    hb_property_name: str | None
    mp_state: str | None
    mp_city: str | None
    # Landing Page Layout / Value Tier Layout / Advance Reservation Days
    # (HB Settings > Website > FMS Initial Setup) - this property's
    # current/baseline value for each setting, restored to after a test
    # changes it.
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
    # This environment's default property (see [environment] section's
    # own default_property key) - None when no property is configured yet
    # (dev/uat). Use load_property()/list_properties() directly for any
    # other property this environment declares.
    lease_configuration_property_name: str | None
    fms_property_name: str | None
    mp_state: str | None
    mp_city: str | None
    landing_page_layout: str | None
    value_tier_layout: str | None
    advance_reservation_days: int | None
    # Comma-separated in the ini, per environment - kept for reference/
    # potential future use, not read by the current layout test matrix
    # (tests/mp/reservation/test_legacy_landing_page_layout.py and
    # test_legacy_value_tier_layout.py hardcode their own full value
    # lists directly instead, so every environment always exercises all
    # of them regardless of this config).
    landing_page_layouts: list[str]
    value_tier_layouts: list[str]
    # Payment scenario data for rental tests (MPLegacyReservationSetup.
    # convert_reservation_to_rental) - merged in from environments.ini's
    # own global `[payment]` section (see load_environment), not
    # per-environment, since it's the same sandbox/test values (not real
    # financial data) everywhere.
    card_number: str | None
    card_expiry: str | None
    card_cvc: str | None
    card_zip_code: str | None
    ach_routing_number: str | None
    ach_account_number: str | None
    ach_account_type: str | None


def load_config() -> ConfigParser:
    config = ConfigParser()
    if not config.read(CONFIG_FILE):
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")
    return config


def _list_option(section, key: str) -> list[str]:
    raw = section.get(key, "")
    return [v.strip() for v in raw.split(",") if v.strip()]


def list_properties(config: ConfigParser, environment: str) -> list[str]:
    """Every property key this environment declares (its own
    `[environment.key]` subsections), from the environment section's own
    `properties` list."""
    environment = environment.strip()
    if not config.has_section(environment):
        return []
    return _list_option(config[environment], "properties")


def load_property(
    config: ConfigParser, environment: str, property_key: str
) -> PropertyConfig:
    """Reads one property's identity from its `[environment.property_key]`
    subsection."""
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
        mp_state=section.get("mp_state", "") or None,
        mp_city=section.get("mp_city", "") or None,
        landing_page_layout=section.get("landing_page_layout", "") or None,
        value_tier_layout=section.get("value_tier_layout", "") or None,
        advance_reservation_days=section.getint(
            "advance_reservation_days", fallback=None
        ),
        notes=section.get("notes", "") or None,
    )


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
    # property) or via `default_property` pointing at a
    # `[environment.key]` subsection (for environments tracking more than
    # one property - see list_properties/load_property). Direct fields
    # win when present.
    if section.get("lease_configuration_property_name"):
        default_property = PropertyConfig(
            key=environment,
            lease_configuration_property_name=section.get(
                "lease_configuration_property_name", ""
            )
            or None,
            fms_property_name=section.get("fms_property_name", "") or None,
            hb_property_name=section.get("hb_property_name", "")
            or section.get("lease_configuration_property_name", "")
            or None,
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
        default_property_key = section.get("default_property", "") or None
        default_property = (
            load_property(config, environment, default_property_key)
            if default_property_key
            else None
        )

    return EnvironmentConfig(
        name=environment,
        mp_base_url=mp_base_url.rstrip("/"),
        hb_base_url=hb_base_url.rstrip("/"),
        hb_username=hb_username,
        hb_password=hb_password,
        lease_configuration_property_name=(
            default_property.lease_configuration_property_name
            if default_property
            else None
        ),
        fms_property_name=(
            default_property.fms_property_name if default_property else None
        ),
        mp_state=default_property.mp_state if default_property else None,
        mp_city=default_property.mp_city if default_property else None,
        landing_page_layout=(
            default_property.landing_page_layout if default_property else None
        ),
        value_tier_layout=(
            default_property.value_tier_layout if default_property else None
        ),
        advance_reservation_days=(
            default_property.advance_reservation_days if default_property else None
        ),
        landing_page_layouts=_list_option(section, "landing_page_layouts"),
        value_tier_layouts=_list_option(section, "value_tier_layouts"),
        **_payment_fields(config),
    )


def _payment_fields(config: ConfigParser) -> dict:
    """Reads environments.ini's global `[payment]` section, merged into
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
