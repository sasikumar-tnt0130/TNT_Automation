import uuid


def new_hb_lead_guest() -> dict:
    """A fresh HB contact identity - see conftest.hb_lead_guest: a unique
    Mailinator email, and a number from (707) 555-0100..0199, the range
    reserved for fictional use (HB texts new contacts)."""
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "PilotAutomation",
        "last_name": f"SmokeTest{suffix[:6]}",
        "email": f"hb-auto-{suffix}@mailinator.com",
        "phone_number": f"70755501{int(suffix[:2], 16) % 100:02d}",
    }


def new_additional_contact() -> dict:
    """A fresh Additional Contact for a test tenant, on the same terms as
    new_hb_lead_guest: a Mailinator email and a fictional (707) 555-01xx
    number."""
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "QA",
        "last_name": f"Alt{suffix[:6]}",
        "email": f"hb-auto-alt-{suffix}@mailinator.com",
        "phone_number": f"70755501{int(suffix[2:4], 16) % 100:02d}",
    }
