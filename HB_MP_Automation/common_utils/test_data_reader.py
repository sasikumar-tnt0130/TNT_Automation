import json
import os
from pathlib import Path


TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "config" / "test_data"

# Sandbox property inventory/signing-config health is volatile - repeated
# automated runs deplete a specific space type/size, or a property turns
# out to use a document-signing flow the pilot page objects don't handle
# yet. Switching which property a test targets used to mean hand-editing
# the checked-in JSON every time (this exact file, more than once in one
# session) - HB_PROPERTY_OVERRIDE lets that be a command-line/CI concern
# instead, e.g.:
#   $env:HB_PROPERTY_OVERRIDE = "Rutland"; pytest tests/hb/test_pay_tenant_bill_cash.py
# Known stage properties as of 2026-09-11 (occupancy, from the HB
# dashboard's property picker - check live before relying on this, it
# drifts): Rutland ~66%, Hamilton County ~29% (most headroom, but has a
# historical move-in invoice bug on a stray "addingnewstaging" fee, and a
# much larger 6-document signing set), Honolulu ~79%, Tustin ~80%.
PROPERTY_OVERRIDE_ENV_VAR = "HB_PROPERTY_OVERRIDE"


def load_test_data(feature: str, environment: str | None = None) -> dict:
    """Load a feature's test data from config/test_data/<feature>.json.

    Any new feature just needs a new JSON file dropped into config/test_data/ —
    no code changes required here.

    If `environment` is given and the JSON has a top-level key matching it,
    that environment's sub-object is returned instead of the whole file —
    for test data (like property/unit names) that only exists on one
    environment's live inventory. Files without environment keys are
    returned unchanged, so this stays backward compatible.

    If the resolved data has a `property_name` key and the
    HB_PROPERTY_OVERRIDE environment variable is set, that env var's value
    replaces it - see the module docstring above for why.
    """
    path = TEST_DATA_DIR / f"{feature}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Test data file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if environment and environment in data:
        data = data[environment]
    property_override = os.environ.get(PROPERTY_OVERRIDE_ENV_VAR)
    if property_override and isinstance(data, dict) and "property_name" in data:
        data = {**data, "property_name": property_override}
    return data
