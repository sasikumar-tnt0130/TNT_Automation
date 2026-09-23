"""Tenant Payments gateway folder — overrides parent gateway_profile.

Do not remove: tests/mp/rentals/conftest.py defaults gateway_profile to
None; this file is what selects Tenant Payments for every test here.
"""

import pytest


@pytest.fixture(scope="module")
def gateway_profile() -> str:
    """Tenant Payments card + ACH (environments.ini profile=tenant_payments)."""
    return "tenant_payments"
