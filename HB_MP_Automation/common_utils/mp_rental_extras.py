"""Shared Legacy rental-application extras payloads (military / lien / vehicle /
emergency / authorized access).

Walked live 2026-09-16 stage/Garden Grove for TestRail smoke 2967 extras,
documents, and Super Lease content cases.
"""
from __future__ import annotations

import uuid


def letter_suffix(raw: str) -> str:
    return "".join("abcdefghij"[int(ch)] if ch.isdigit() else ch for ch in raw)


def _contact(prefix: str, rental_data: dict) -> dict:
    suffix = letter_suffix(uuid.uuid4().hex[:6])
    return {
        "first_name": prefix,
        "last_name": f"Contact{suffix}",
        "email": f"{prefix.lower()}-{suffix}@mailinator.com",
        "phone": f"(714) 555-01{int(uuid.uuid4().hex[:2], 16) % 100:02d}",
        "address1": rental_data["address1"],
        "address2": rental_data.get("address2", ""),
        "city": rental_data["city"],
        "state": rental_data["state"],
        "state_code": rental_data["state_code"],
        "zip": rental_data["zip"],
    }


def rental_extras(
    rental_data: dict,
    *,
    military: bool = False,
    lien_holder: bool = False,
    vehicle: bool = False,
    coverage: bool = True,
    emergency: bool = False,
    authorized_access: bool = False,
) -> dict:
    """extras= dict for MPLegacyReservationFormPage.fill_rental_application."""
    suffix = letter_suffix(uuid.uuid4().hex[:6])
    extras: dict = {"coverage": coverage}
    if military:
        extras["military"] = {
            "identification_number": "DOD-AUTO-001",
            "dob": "01/15/1990",
            "ssn": "900-11-2233",
            "ets": "12/31/2028",
            "branch": "Army",
            "unit_name": "Automation Unit",
            "unit_phone": "(714) 555-0188",
            "officer_first_name": "Officer",
            "officer_last_name": f"Lead{suffix}",
        }
    if lien_holder:
        extras["lien_holder"] = {
            "first_name": "Lien",
            "last_name": f"Bank{suffix}",
            "email": f"lien-{suffix}@mailinator.com",
            "phone": "(714) 555-0177",
            "address1": rental_data["address1"],
            "address2": rental_data.get("address2", ""),
            "city": rental_data["city"],
            "state": rental_data["state"],
            "state_code": rental_data["state_code"],
            "zip": rental_data["zip"],
        }
    if vehicle:
        extras["vehicle_type"] = "Car"
        extras["vehicle"] = {
            "vin": "1HGBH41JXMN109186",
            "license_plate": "AUTO123",
            "approximate_value": "5000",
            "insurance_provider": "State Farm",
            "policy_number": "POL-AUTO-001",
        }
    if emergency:
        extras["emergency"] = _contact("Emerg", rental_data)
    if authorized_access:
        extras["authorized_access"] = _contact("Auth", rental_data)
    return extras
