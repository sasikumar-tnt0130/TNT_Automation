"""Document-suite fixtures shared by Traditional + Superlease document tests.

Ensures Autotest V2 professional Document Templates (Lease AZ-style,
Military, Vehicle, Autopay, COA, coverage, etc.). Signing mode stays on
each test class.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("ensure_autotest_document_templates")
