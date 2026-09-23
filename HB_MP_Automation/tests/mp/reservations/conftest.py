"""Reservations suite fixtures.

Signing / APW / Advance Days / Clear Cache match rentals via
``tests/mp/reservations/_helpers.py`` and shared
``two_step_superlease_checked`` in ``tests/mp/conftest.py``.

Each reservation test module owns a module-scoped ``precondition`` (or
``usefixtures``) so one file = one ensure package — same shape as
``tests/mp/rentals/tenant_payments_gateway/test_*.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_helpers_spec = importlib.util.spec_from_file_location(
    "mp_reservations_helpers", Path(__file__).with_name("_helpers.py")
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)

ensure_legacy_reservation_flow = _helpers.ensure_legacy_reservation_flow
ensure_legacy_traditional = _helpers.ensure_legacy_traditional
ensure_two_step_superlease = _helpers.ensure_two_step_superlease


@pytest.fixture(scope="module")
def legacy_reservation_checked(
    hb_admin_session, environment_config, app_config
) -> None:
    """Once: Legacy reservation flow (APW + traditional signing + layout + cache)."""
    ensure_legacy_reservation_flow(
        hb_admin_session, environment_config, app_config
    )
