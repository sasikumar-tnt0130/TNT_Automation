"""Shared MP fixtures (reservations, rentals, account)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Rentals helpers — same loader as tests/mp/rentals/conftest.
_helpers_spec = importlib.util.spec_from_file_location(
    "mp_rentals_helpers_for_mp",
    Path(__file__).resolve().parent / "rentals" / "_helpers.py",
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)
_ensure_two_step_superlease = _helpers.ensure_two_step_superlease
_ensure_legacy_traditional = _helpers.ensure_legacy_traditional


@pytest.fixture(scope="module")
def two_step_superlease_checked(
    hb_admin_session,
    environment_config,
    app_config,
    two_step_property,
) -> None:
    """Once: APW + Two-Step/Clickwrap/Super Lease + Advance Days + Clear Cache."""
    import os

    # SKIP_LEASE_ENSURE=1: storefront already serves Two-Step (e.g. shared
    # legacy/two_step property). Avoids hanging Lease Configuration UI.
    if os.environ.get("SKIP_LEASE_ENSURE", "").strip() in {"1", "true", "yes"}:
        return
    _ensure_two_step_superlease(
        hb_admin_session,
        environment_config,
        app_config,
        two_step_property,
    )


@pytest.fixture(scope="module")
def legacy_traditional_checked(
    hb_admin_session, environment_config, app_config
) -> None:
    """Once: APW + Advance Days + Traditional (Two-Step/CW/SL off) + Clear Cache."""
    _ensure_legacy_traditional(
        hb_admin_session, environment_config, app_config
    )


# Historical alias — same fixture (usefixtures / reservations / account).
ensure_two_step_superlease = two_step_superlease_checked
