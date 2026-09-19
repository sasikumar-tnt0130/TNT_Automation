"""Hosted card payment variants for full rental + confirmation (MRECOM-323).

Each case pays with valid sandbox card data in a specific format (PAN length,
expiry YY/YYYY, CVV 3/4) and expects rental confirmation — not UI-only typing.
"""

from __future__ import annotations

import re

from pages.mariposa.mp_rental_payment_form import (
    card_pan_digits,
    expected_cvv_length,
    normalize_expiry_digits,
)

# Sandbox PANs for format coverage (must be accepted by the gateway under test).
PAN_16 = "4111111111111111"  # Visa → 3-digit CVV
PAN_19 = "6210945888040000007"  # up to 19 digits
PAN_AMEX = "378282246310005"  # Amex → 4-digit CVV
CVV_3 = "123"
CVV_4 = "1234"


def expiry_as_mmyy(card_expiry: str) -> str:
    """MMYY digits (2-digit year) for hosted expiry typing."""
    digits = normalize_expiry_digits(card_expiry)
    if len(digits) == 6:
        return digits[:2] + digits[4:]
    return digits


def expiry_as_mmyyyy(card_expiry: str) -> str:
    """MMYYYY digits (4-digit year) for hosted expiry typing."""
    digits = normalize_expiry_digits(card_expiry)
    if len(digits) == 4:
        return digits[:2] + "20" + digits[2:]
    return digits


def card_for_pan_16(environment_config) -> dict:
    """16-digit PAN + 3-digit CVV; uses secrets when they already match."""
    pan = card_pan_digits(environment_config.card_number or "")
    cvc = re.sub(r"\D", "", environment_config.card_cvc or "")
    if len(pan) == 16 and expected_cvv_length(pan) == 3 and len(cvc) == 3:
        return {
            "card_number": pan,
            "card_expiry": environment_config.card_expiry,
            "card_cvc": cvc,
        }
    return {
        "card_number": PAN_16,
        "card_expiry": environment_config.card_expiry,
        "card_cvc": CVV_3,
    }


def card_for_pan_19(environment_config) -> dict:
    return {
        "card_number": PAN_19,
        "card_expiry": environment_config.card_expiry,
        "card_cvc": CVV_3,
    }


def card_for_expiry_yy(environment_config) -> dict:
    base = card_for_pan_16(environment_config)
    return {**base, "card_expiry": expiry_as_mmyy(base["card_expiry"])}


def card_for_expiry_yyyy(environment_config) -> dict:
    base = card_for_pan_16(environment_config)
    return {**base, "card_expiry": expiry_as_mmyyyy(base["card_expiry"])}


def card_for_cvv_3(environment_config) -> dict:
    return card_for_pan_16(environment_config)


def card_for_cvv_4(environment_config) -> dict:
    return {
        "card_number": PAN_AMEX,
        "card_expiry": environment_config.card_expiry,
        "card_cvc": CVV_4,
    }
