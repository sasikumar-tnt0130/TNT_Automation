"""Non-Tenant-Payments gateway folder — overrides parent gateway_profile.

Do not remove: tests/mp/rentals/conftest.py defaults gateway_profile to
None; this file is what selects Authorize.Net (non_tenant_payments) for
every test here. That profile has no ACH gateway.
"""

import pytest


@pytest.fixture
def gateway_profile() -> str:
    """Authorize.Net / non-Tenant-Payments (environments.ini profile=non_tenant_payments)."""
    return "non_tenant_payments"
