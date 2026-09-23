"""Shared helpers for tests/mp/reservations (preconditions aligned with rentals)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Reuse rentals ensure_* (APW + days + signing + one Clear Cache).
_helpers_spec = importlib.util.spec_from_file_location(
    "mp_rentals_helpers_for_reservations",
    Path(__file__).resolve().parent.parent / "rentals" / "_helpers.py",
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)

ensure_legacy_traditional = _helpers.ensure_legacy_traditional
ensure_two_step_superlease = _helpers.ensure_two_step_superlease
ensure_property_advanced_reservations = _helpers.ensure_property_advanced_reservations
ensure_advance_reservation_days = _helpers.ensure_advance_reservation_days
legacy_signing_setup = _helpers.legacy_signing_setup
_flush_or_close_settings = _helpers._flush_or_close_settings
_legacy_property_keys = _helpers._legacy_property_keys


def ensure_legacy_reservation_flow(
    hb_login_page, environment_config, app_config
) -> None:
    """Once: APW + Advance Days + Two-Step/CW/SL off + landing layout + Clear Cache.

    Same package as rentals ``ensure_legacy_traditional``, plus optional
    ``landing_page_layout`` from the environment/property config (reservation
    suites historically set this so Default/Grid/List matches expectations).
    """
    keys = _legacy_property_keys(environment_config)
    ensure_property_advanced_reservations(
        hb_login_page,
        environment_config,
        app_config,
        property_keys=keys,
    )
    days_dirty = ensure_advance_reservation_days(
        hb_login_page,
        environment_config,
        app_config,
        property_keys=keys,
        close_settings=False,
    )
    with legacy_signing_setup(
        hb_login_page, environment_config, app_config
    ) as signing:
        changed = signing.disable_two_step_clickwrap_and_super_lease()
        layout = environment_config.landing_page_layout
        if layout:
            signing.set_landing_page_layout(layout)
            changed = True
        _flush_or_close_settings(signing, dirty=changed or days_dirty)
