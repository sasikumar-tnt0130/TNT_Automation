import json
import os
from pathlib import Path


TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "config" / "test_data"

# Override property_name without editing JSON, e.g.:
#   $env:HB_PROPERTY_OVERRIDE = "Rutland"; pytest tests/hb/test_pay_tenant_bill_cash.py
PROPERTY_OVERRIDE_ENV_VAR = "HB_PROPERTY_OVERRIDE"


def _deep_merge(base: dict, override: dict) -> dict:
    """Shallow-merge top-level keys; nested dicts are merged one level deep
    so per-env address/driver_license blocks can override only what they
    need without repeating the whole object."""
    merged = {**base}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _is_env_structured(data: dict) -> bool:
    """True when the file is keyed by environment (and optional defaults),
    not a flat feature payload like mp_rental.json."""
    reserved = {"defaults"}
    return any(key not in reserved for key in data) and all(
        key in reserved or isinstance(value, dict) for key, value in data.items()
    )


def _hb_property_name_for_role(environment: str, role: str) -> str | None:
    """HB picker name for legacy_property or two_step_property."""
    from config.config_reader import load_config, load_property

    config = load_config()
    if not config.has_section(environment):
        return None
    key = config.get(environment, role, fallback="").strip()
    if not key:
        return None
    return load_property(config, environment, key).hb_property_name


def load_test_data(feature: str, environment: str | None = None) -> dict:
    """Load a feature's test data from config/test_data/<feature>.json.

    Any new feature just needs a new JSON file dropped into config/test_data/ —
    no code changes required here.

    If `environment` is given and the JSON has a top-level key matching it,
    that environment's sub-object is returned instead of the whole file —
    for test data (like property/unit names) that only exists on one
    environment's live inventory. Files without environment keys are
    returned unchanged, so this stays backward compatible.

    Optional top-level `defaults` are merged under the environment slice
    first (env wins), so shared guest/address/notes fields live once.
    An env-structured file may omit an environment entirely; the caller
    then gets `defaults` alone (empty strings stay empty so tests can
    skip).

    For environments present in the file, empty `property_name` /
    `lead_property` resolve from properties.ini. HB_PROPERTY_OVERRIDE
    replaces `property_name` last when set.
    """
    path = TEST_DATA_DIR / f"{feature}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Test data file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return raw

    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    env_structured = _is_env_structured(raw)
    resolved_slice = False

    env_explicit = bool(environment and env_structured and environment in raw)
    if env_explicit:
        env_slice = raw[environment]
        data = (
            _deep_merge(defaults, env_slice)
            if isinstance(env_slice, dict)
            else env_slice
        )
        resolved_slice = isinstance(data, dict)
    elif environment and env_structured:
        # Environment omitted from an env-keyed file -> defaults only
        # (keeps skip-when-empty behaviour for unset envs).
        data = dict(defaults)
        resolved_slice = True
    else:
        data = {key: value for key, value in raw.items() if key != "defaults"}
        if defaults and not data:
            data = dict(defaults)

    if resolved_slice and environment and isinstance(data, dict):
        if env_explicit and not data.get("property_name"):
            resolved = _hb_property_name_for_role(environment, "legacy_property")
            if resolved:
                data = {**data, "property_name": resolved}
        if env_explicit and "lead_property" in data and not data.get("lead_property"):
            resolved = _hb_property_name_for_role(environment, "two_step_property")
            if resolved:
                data = {**data, "lead_property": resolved}

    property_override = os.environ.get(PROPERTY_OVERRIDE_ENV_VAR)
    if property_override and isinstance(data, dict) and "property_name" in data:
        data = {**data, "property_name": property_override}
    return data
