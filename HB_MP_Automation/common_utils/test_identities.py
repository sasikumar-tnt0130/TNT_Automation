import uuid

from common_utils.email_providers import test_inbox_address


def new_hb_lead_guest() -> dict:
    """A fresh HB contact identity - see conftest.hb_lead_guest: a unique
    test-inbox email, and a number from (707) 555-0100..0199, the range
    reserved for fictional use (HB texts new contacts)."""
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "PilotAutomation",
        "last_name": f"SmokeTest{suffix[:6]}",
        "email": test_inbox_address(f"hb-auto-{suffix}"),
        "phone_number": f"70755501{int(suffix[:2], 16) % 100:02d}",
    }


def new_additional_contact() -> dict:
    """A fresh Additional Contact for a test tenant, on the same terms as
    new_hb_lead_guest: a test-inbox email and a fictional (707) 555-01xx
    number."""
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "QA",
        "last_name": f"Alt{suffix[:6]}",
        "email": test_inbox_address(f"hb-auto-alt-{suffix}"),
        "phone_number": f"70755501{int(suffix[2:4], 16) % 100:02d}",
    }


def new_mp_guest() -> dict:
    """A fresh storefront guest: unique test-inbox email and a fictional
    (714) 555-01xx mobile (see conftest.mp_guest)."""
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "Auto",
        "last_name": "Tester",
        "email": test_inbox_address(f"mp-auto-{suffix}"),
        "mobile": f"(714) 555-01{int(suffix[:2], 16) % 100:02d}",
    }
