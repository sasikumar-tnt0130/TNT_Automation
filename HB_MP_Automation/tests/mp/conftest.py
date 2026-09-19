"""Shared MP fixtures (reservations, rentals, account)."""

from __future__ import annotations

import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup


@pytest.fixture(scope="module")
def two_step_superlease_checked(
    hb_admin_session, environment_config, app_config, two_step_property
) -> None:
    """Ensure Two-Step property has Super Lease + Clickwrap + Two-Step on.

    Enables (and flushes website cache) when needed so the storefront
    serves ``Reserve Now`` rather than Legacy ``Reserve This Space``.
    Used by gateway rental matrices and standalone Two-Step smoke tests.
    """
    signing = LeaseConfigurationSetup(
        hb_admin_session,
        environment_config,
        app_config,
        property_name=two_step_property.lease_configuration_property_name,
        fms_property_name=two_step_property.fms_property_name,
        hb_property_name=two_step_property.hb_property_name,
    )
    signing.enable_two_step_clickwrap_and_super_lease()
    signing.flush_website_cache()


# Clearer alias for callers that want the enable semantics spelled out.
# Safe when legacy_property == two_step_property: each suite's signing
# fixture reconfigures Two-Step on/off for that module before the run.
ensure_two_step_superlease = two_step_superlease_checked
