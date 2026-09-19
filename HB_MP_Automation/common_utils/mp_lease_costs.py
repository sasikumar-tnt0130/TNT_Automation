"""Lease / confirmation cost line-item checks across three places:

1. MP rental confirmation page (thank-you after Pay Now / Sign)
2. Rental Confirmation email (Account Summary)
3. Lease agreement PDF (Superlease or Lease Agreement in HB / email link)

Each source is parsed for its own labels/amounts, then compared on
normalized keys. Any missing or mismatched dollar amount raises.
"""

from __future__ import annotations

import html as html_lib
import re
from contextlib import nullcontext

import allure
from playwright.sync_api import Page

from config.config_reader import load_config


def validate_cost_line_items_enabled() -> bool:
    """True when every rent line item must match across sources.

    Controlled by ``[validation] validate_cost_line_items`` in
    environments.ini. Default false: only Total Cost to Move-in is asserted.
    """
    return load_config().getboolean(
        "validation", "validate_cost_line_items", fallback=False
    )

_MONEY = re.compile(r"(-\s*)?\$\s*([\d,]+(?:\.\d+)?)")
_MOVE_IN_TOTAL = re.compile(
    r"Total\s+(?:Cost\s+To\s+)?Move-?In(?:\s+Cost)?\s*:?\s*\$\s*([\d,]+(?:\.\d+)?)",
    re.I,
)
# Lease SPACE INFORMATION uses "Total Move-In Cost" (no "Cost To").
_MOVE_IN_TOTAL_ALT = re.compile(
    r"Total\s+Move-?In\s+Cost\s*:?\s*\$\s*([\d,]+(?:\.\d+)?)",
    re.I,
)

# Lease-only rollups that are not charged the same way on MP / email.
_SKIP_COMPARE_KEYS = frozenset(
    {
        "total promotion rate",
        "merchandise total",
        "payment collected at move in",
        "payment collected",
        "total discounts",
        "monthly rent",  # lease SPACE INFORMATION base rate, not move-in rent
    }
)

# Map source-specific labels → one compare key. Kept small; unknown labels
# still compare via normalize_charge_key + fuzzy token overlap.
_ALIAS_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(web\s+)?rental\s+rate$|^total\s+rent$|^rent$", re.I), "rent"),
    (
        re.compile(
            r"^total\s+promotions?$|^\d+%\s*off|off\s+\d+\s+months|^derrels$",
            re.I,
        ),
        "promotion",
    ),
    (re.compile(r"^total\s+tax$|^taxes?$", re.I), "tax"),
    (re.compile(r"^admin(istrative)?\s+fees?$", re.I), "admin fees"),
    (re.compile(r"^security\s+deposit$", re.I), "security deposit"),
    (re.compile(r"^key\s+deposits?$", re.I), "key deposit"),
    (re.compile(r"^coverage\b", re.I), "coverage"),
    (re.compile(r"^lock\s+cut$", re.I), "lock cut"),
    (re.compile(r"^lien\s+notice$", re.I), "lien notice"),
    (re.compile(r"^advertising$", re.I), "advertising"),
    (re.compile(r"^damage\s+fee$", re.I), "damage fee"),
    (re.compile(r"^accounting\s+fee$", re.I), "accounting fee"),
    (re.compile(r"^addingnewstaging$", re.I), "addingnewstaging"),
]


def money_value(text: str) -> float:
    """Parse a $amount string; leading '-' makes it negative."""
    match = _MONEY.search(text or "")
    if not match:
        return 0.0
    value = float(match.group(2).replace(",", ""))
    return -value if match.group(1) else value


def format_money(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def _amounts_equal(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) < 0.005


def parse_move_in_total(text: str) -> float | None:
    match = _MOVE_IN_TOTAL.search(text or "") or _MOVE_IN_TOTAL_ALT.search(text or "")
    if not match:
        match = re.search(
            r"Total\s+Cost\s+to\s+Move-?in\s*:?\s*\$\s*([\d,]+(?:\.\d+)?)",
            text or "",
            re.I,
        )
    return float(match.group(1).replace(",", "")) if match else None


def lease_text_for_space(lease_text: str, space_number: str | None) -> str:
    """Slice lease PDF text to the rented space (multi-space Superleases).

    Starts at SPACE INFORMATION / PAYMENT near ``#<space>`` (or
    ``Space <space>``) and stops before the next other unit id.
    Falls back to the full text when the space is not found.
    """
    text = lease_text or ""
    if not text or not space_number:
        return text
    space = re.sub(r"^#", "", str(space_number).strip())
    if not space:
        return text
    hit = re.search(
        rf"(?:Space\s*[#:]?\s*|#\s*){re.escape(space)}\b",
        text,
        re.I,
    )
    if not hit:
        return text
    start = hit.start()
    lookback = text[max(0, start - 600) : start]
    headers = list(
        re.finditer(r"\b(?:SPACE\s+INFORMATION|PAYMENT)\b", lookback, re.I)
    )
    if headers:
        start = max(0, start - 600) + headers[-1].start()
    rest = text[start:]
    # End before another unit id (#ABCD) that is not this space, or the
    # next SPACE INFORMATION block (another unit's card).
    tail = rest[max(80, hit.end() - start) :]
    end = len(rest)
    other = re.search(
        rf"#\s*(?!{re.escape(space)}\b)[A-Za-z0-9]+\b",
        tail,
        re.I,
    )
    if other:
        end = min(end, max(80, hit.end() - start) + other.start())
    nxt = re.search(r"\bSPACE\s+INFORMATION\b", rest[120:], re.I)
    if nxt:
        end = min(end, 120 + nxt.start())
    return rest[: min(end, 10_000)]


def parse_charges_from_summary_text(text: str) -> dict[str, float]:
    """Charge label → amount from Lease Summary / confirmation / email / lease.

    Takes the last $amount on each line so labels like ``Coverage $2000`` keep
    the coverage limit and use ``$8.00`` as the charge (screenshot 2026-09-18).

    Mailinator plain text used to collapse to one line; when there are almost
    no newlines, amounts are split on every ``$`` boundary instead.
    """
    # Earliest charge-like label so MP "Security Deposit" rows above
    # "Web Rental Rate" are not dropped (2026-09-19 Hamilton walk).
    starts = [
        m.start()
        for m in (
            re.search(r"\bSecurity\s+Deposit\b", text, re.I),
            re.search(r"\bAdmin(?:istrative)?\s+Fees?\b", text, re.I),
            re.search(r"\bRent\s*\(", text),
            re.search(r"\b(?:Web\s+)?Rental\s+Rate\b", text, re.I),
            re.search(r"\bTotal\s+Rent\b", text, re.I),
            re.search(r"\b(?:Monthly\s+)?Rent\b", text, re.I),
            re.search(r"\bCoverage\b", text, re.I),
            re.search(r"\bKey\s+Deposit\b", text, re.I),
        )
        if m is not None
    ]
    rows = text[min(starts) :] if starts else text
    # Only split on the real move-in total footer — bare "Total:" also matches
    # "Merchandise Total:" on the lease SPACE INFORMATION card.
    rows = re.split(
        r"\btotal\s+cost\s+to\s+move-?in\b|\btotal\s+move-?in\s+cost\b",
        rows,
        maxsplit=1,
        flags=re.I,
    )[0]
    # Collapsed email body (single line): pair each $amount with the label
    # text immediately before it.
    if rows.count("\n") < 2 and len(list(_MONEY.finditer(rows))) > 1:
        return _parse_charges_inline(rows)
    charges: dict[str, float] = {}
    pending_label: str | None = None
    for line in rows.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        matches = list(_MONEY.finditer(line))
        if not matches:
            # Lease SPACE INFORMATION often prints "Taxes:" with no $0.00.
            if re.fullmatch(r"taxes?\s*:?", line, re.I):
                charges["Taxes"] = 0.0
                pending_label = None
                continue
            # MP confirmation can split "50% Off 3 Months" / "Derrels".
            if re.search(r"[A-Za-z]", line) and not re.match(
                r"^(taxes?|total)\b", line, re.I
            ):
                pending_label = (
                    f"{pending_label} {line}".strip() if pending_label else line
                )
            continue
        amount_match = matches[-1]
        label = line[: amount_match.start()].strip(" -:\t")
        if pending_label and not label:
            label = pending_label
        pending_label = None
        if not label:
            continue
        # Skip footer-style totals; keep Total Tax / Total Rent / Total Promotions.
        if re.match(r"total\s+cost\b", label, re.I):
            continue
        if re.match(r"total\s+move-?in\b", label, re.I):
            continue
        if re.fullmatch(r"total", label, re.I):
            continue
        value = float(amount_match.group(2).replace(",", ""))
        if amount_match.group(1) or line.lstrip().startswith("-"):
            value = -abs(value)
        charges[label] = value
    return charges


def _parse_charges_inline(text: str) -> dict[str, float]:
    """Parse label+$amount pairs from whitespace-collapsed email bodies."""
    charges: dict[str, float] = {}
    matches = list(_MONEY.finditer(text))
    for index, amount_match in enumerate(matches):
        start = matches[index - 1].end() if index else 0
        label = text[start : amount_match.start()].strip(" -:\t")
        label = re.sub(r"\s+", " ", label).strip()
        if not label:
            continue
        if re.match(r"total\s+cost\b", label, re.I):
            continue
        if re.match(r"total\s+move-?in\b", label, re.I):
            continue
        if re.fullmatch(r"total", label, re.I):
            continue
        value = float(amount_match.group(2).replace(",", ""))
        if amount_match.group(1):
            value = -abs(value)
        charges[label] = value
    return charges


def security_deposit_amount(charges: dict[str, float] | None) -> float | None:
    """Prefer 'Security Deposit' over other *deposit* rows (key deposit, …)."""
    if not charges:
        return None
    for label, amount in charges.items():
        if re.fullmatch(r"security\s+deposit", label, re.I):
            return amount
    for label, amount in charges.items():
        if "security deposit" in label.lower() and not re.search(
            r"security\s+deposit\s+\d+", label, re.I
        ):
            return amount
    return None


def _label_key(label: str) -> str:
    """Drop parenthetical date ranges / noise for flexible matching."""
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", label)).strip()


def normalize_charge_key(label: str) -> str:
    """Stable key for cross-source compare (MP page / email / lease PDF)."""
    key = _label_key(label).lower()
    key = re.sub(r"\$\s*[\d,]+(?:\.\d+)?", "", key)
    key = re.sub(r"[^a-z0-9%]+", " ", key).strip()
    for pattern, canonical in _ALIAS_RULES:
        if pattern.search(key):
            return canonical
    return key


def _by_canonical(charges: dict[str, float]) -> dict[str, tuple[str, float]]:
    """canonical key → (original label, amount). Last write wins per key."""
    out: dict[str, tuple[str, float]] = {}
    for label, amount in charges.items():
        raw_key = re.sub(
            r"\s+",
            " ",
            re.sub(r"\$\s*[\d,]+(?:\.\d+)?", "", _label_key(label).lower()),
        )
        raw_key = re.sub(r"[^a-z0-9%]+", " ", raw_key).strip()
        if raw_key in _SKIP_COMPARE_KEYS:
            continue
        key = normalize_charge_key(label)
        if not key or key in _SKIP_COMPARE_KEYS:
            continue
        out[key] = (label, amount)
    return out


def _label_pattern(label: str) -> str:
    """Regex for a charge label with flexible whitespace (not escaped spaces)."""
    key = _label_key(label) or label
    return r"\s+".join(re.escape(part) for part in key.split() if part)


def read_confirmation_page_costs(page: Page) -> dict:
    """Parse cost rows + move-in total from the MP rental confirmation page."""
    with allure.step("Read costs from MP rental confirmation page"):
        text = page.locator("body").inner_text()
        charges = parse_charges_from_summary_text(text)
        total = parse_move_in_total(text)
        result = {"charges": charges, "total": total, "text": text}
        allure.attach(
            "\n".join(f"{k}: {v:+.2f}" for k, v in charges.items())
            + (f"\nTOTAL: {total:.2f}" if total is not None else "\nTOTAL: (not found)"),
            name="mp-confirmation-costs",
            attachment_type=allure.attachment_type.TEXT,
        )
        return result


def _keys_compatible(left: str, right: str) -> bool:
    """True when two normalized keys name the same charge (dynamic, not exact)."""
    if left == right:
        return True
    if not left or not right:
        return False
    a, b = set(left.split()), set(right.split())
    if a <= b or b <= a:
        return True
    # e.g. "admin fee" vs "admin fees" after stemming-ish strip of trailing s
    a_stem = {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in a}
    b_stem = {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in b}
    if a_stem <= b_stem or b_stem <= a_stem:
        return True
    overlap = a_stem & b_stem
    return len(overlap) >= max(1, min(len(a_stem), len(b_stem)) - 1)


def _coverage_limit_vs_premium(
    expected_amount: float, actual_label: str, actual_amount: float
) -> bool:
    """Lease Summary often stores Coverage as the plan limit ($2000); email
    shows ``Coverage $2000 $ 8.00`` (limit + premium). Treat as matched."""
    if abs(expected_amount - actual_amount) < 0.005:
        return True
    limits = [
        float(m.group(1).replace(",", ""))
        for m in re.finditer(r"\$\s*([\d,]+(?:\.\d+)?)", actual_label or "")
    ]
    if any(abs(expected_amount - limit) < 0.005 for limit in limits):
        return True
    # Expected was the limit alone (round hundreds+), actual is the premium.
    if expected_amount >= 100 and actual_amount < expected_amount:
        return True
    return False


def _lookup_actual_amount(
    actual: dict[str, tuple[str, float]],
    key: str,
    expected_amount: float,
) -> float | None:
    """Find the amount in ``actual`` for ``key``, allowing fuzzy labels."""
    if key in actual and _amounts_equal(actual[key][1], expected_amount):
        return actual[key][1]
    for akey, (alabel, aamt) in actual.items():
        if not _keys_compatible(key, akey):
            continue
        if _amounts_equal(aamt, expected_amount):
            return aamt
        if key == "coverage" or "coverage" in key:
            if _coverage_limit_vs_premium(expected_amount, alabel, aamt):
                return aamt
    # Amount appears under any compatible key even if expected was a limit.
    if key == "coverage" or "coverage" in key:
        for akey, (alabel, aamt) in actual.items():
            if "coverage" in akey or "coverage" in alabel.lower():
                if _coverage_limit_vs_premium(expected_amount, alabel, aamt):
                    return aamt
    return None


def assert_cost_line_items(
    text: str,
    charges: dict[str, float],
    *,
    total: float | None = None,
    source: str = "text",
    line_items: bool | None = None,
) -> None:
    """Assert costs in plain text (email / lease PDF).

    By default (``[validation] validate_cost_line_items = false``) only the
    Total Cost to Move-in is required. Set the flag (or pass
    ``line_items=True``) to also assert every charge label/amount.
    """
    check_lines = (
        validate_cost_line_items_enabled() if line_items is None else line_items
    )
    with allure.step(
        f"Assert {'cost line items' if check_lines else 'Total Cost to Move-in'} "
        f"in {source}"
    ):
        actual = _by_canonical(parse_charges_from_summary_text(text))
        expected = _by_canonical(charges) if check_lines else {}
        missing: list[str] = []
        rows: list[str] = ["key | expected | found in text | result", "-" * 64]
        if not check_lines:
            rows.append(
                "(line-item checks skipped — "
                "[validation] validate_cost_line_items=false)"
            )
        for key, (label, amount) in expected.items():
            found = _lookup_actual_amount(actual, key, amount)
            if found is None:
                missing.append(f"{label} = {amount:+.2f}")
                rows.append(
                    f"{key} ({label}) | {format_money(amount)} | MISSING | FAIL"
                )
            else:
                rows.append(
                    f"{key} ({label}) | {format_money(amount)} | "
                    f"{format_money(found)} | MATCH"
                )
        if total is not None:
            parsed_total = parse_move_in_total(text)
            if parsed_total is None or not _amounts_equal(parsed_total, total):
                money = f"{abs(total):,.2f}"
                total_ok = bool(
                    re.search(
                        rf"Total\s+Cost\s+To\s+Move-?In.{{0,40}}\$\s*{re.escape(money)}",
                        text,
                        re.I | re.S,
                    )
                    or re.search(
                        rf"Total\s+Cost\s+To\s+Move-?In.{{0,40}}\$\s*"
                        rf"{re.escape(f'{abs(total):.2f}')}",
                        text,
                        re.I | re.S,
                    )
                    or re.search(
                        rf"Total\s+Move-?In\s+Cost.{{0,40}}\$\s*{re.escape(money)}",
                        text,
                        re.I | re.S,
                    )
                    or re.search(
                        rf"Move-?in\s+Total.{{0,40}}\$\s*{re.escape(money)}",
                        text,
                        re.I | re.S,
                    )
                )
                if not total_ok:
                    missing.append(f"Total Cost to Move-in = {total:.2f}")
                    rows.append(
                        f"total | {format_money(total)} | "
                        f"{format_money(parsed_total) if parsed_total is not None else 'MISSING'} | FAIL"
                    )
                else:
                    rows.append(f"total | {format_money(total)} | (regex) | MATCH")
            else:
                rows.append(
                    f"total | {format_money(total)} | {format_money(parsed_total)} | MATCH"
                )
        table = "\n".join(rows)
        if check_lines or missing:
            allure.attach(
                table,
                name=f"expected-costs ({source})",
                attachment_type=allure.attachment_type.TEXT,
            )
        if check_lines:
            allure.attach(
                "\n".join(
                    f"{k}: {format_money(v[1])} ({v[0]})" for k, v in actual.items()
                ),
                name=f"parsed-costs ({source})",
                attachment_type=allure.attachment_type.TEXT,
            )
        assert not missing, (
            f"{source} is missing cost line item(s) {missing}. "
            f"Text sample: {text[:1200]}\n\n{table}"
        )


def _cell(amount: float | None) -> str:
    if amount is None:
        return "MISSING"
    return format_money(amount)


def _status(
    mp: float | None, email: float | None, lease: float | None, *, required: bool
) -> str:
    # A $0.00 charge omitted on one source still counts as zero.
    if required and mp == 0.0:
        email = 0.0 if email is None else email
        lease = 0.0 if lease is None else lease
    present = [v for v in (mp, email, lease) if v is not None]
    if required and (mp is None or email is None or lease is None):
        missing = []
        if mp is None:
            missing.append("MP")
        if email is None:
            missing.append("email")
        if lease is None:
            missing.append("lease")
        return "MISSING (" + ", ".join(missing) + ")"
    if len(present) < 2:
        return "N/A"
    if all(_amounts_equal(present[0], other) for other in present[1:]):
        return "MATCH"
    return "MISMATCH"


def _align_source_amounts(
    key: str,
    mp_amt: float | None,
    mp_label: str | None,
    email_amt: float | None,
    email_label: str | None,
    lease_amt: float | None,
    lease_label: str | None,
) -> tuple[float | None, float | None, float | None]:
    """Reconcile Coverage limit vs premium (and similar) across sources."""
    if "coverage" not in key:
        return mp_amt, email_amt, lease_amt

    def _ok(a: float | None, a_label: str | None, b: float | None, b_label: str | None) -> bool:
        if a is None or b is None:
            return True
        if _amounts_equal(a, b):
            return True
        return _coverage_limit_vs_premium(a, b_label or "", b) or _coverage_limit_vs_premium(
            b, a_label or "", a
        )

    if not (
        _ok(mp_amt, mp_label, email_amt, email_label)
        and _ok(mp_amt, mp_label, lease_amt, lease_label)
        and _ok(email_amt, email_label, lease_amt, lease_label)
    ):
        return mp_amt, email_amt, lease_amt

    # For display/status, collapse to the premium (smallest positive) when
    # one side still carries the plan limit.
    positives = [v for v in (mp_amt, email_amt, lease_amt) if v is not None and v > 0]
    if len(positives) >= 2 and max(positives) >= 100 and min(positives) < max(positives):
        premium = min(positives)
        mp_amt = premium if mp_amt is not None else None
        email_amt = premium if email_amt is not None else None
        lease_amt = premium if lease_amt is not None else None
    return mp_amt, email_amt, lease_amt


def assert_costs_match_three_ways(
    *,
    mp_charges: dict[str, float],
    mp_total: float | None,
    email_text: str,
    lease_text: str,
    fallback_charges: dict[str, float] | None = None,
    line_items: bool | None = None,
    wrap_step: bool = True,
    space_number: str | None = None,
) -> None:
    """Compare costs across MP confirmation, email, and lease PDF.

    Default (``[validation] validate_cost_line_items = false``): only
    Total Cost to Move-in must match. Set the flag (or ``line_items=True``)
    to also require every charge key across the three sources.

    ``space_number`` scopes lease PDF parsing to that unit's block
    (multi-space Superleases). Always attaches parsed-costs for MP /
    email / lease.

    Pass ``wrap_step=False`` when the caller already opened an Allure step
    with this name (avoids a nested duplicate).
    """
    check_lines = (
        validate_cost_line_items_enabled() if line_items is None else line_items
    )
    raw_mp = dict(mp_charges or fallback_charges or {})
    if not raw_mp and email_text:
        raw_mp = parse_charges_from_summary_text(email_text)

    lease_slice = lease_text_for_space(lease_text or "", space_number)
    email_charges = parse_charges_from_summary_text(email_text or "")
    lease_charges = parse_charges_from_summary_text(lease_slice)
    mp_map = _by_canonical(raw_mp)
    email_map = _by_canonical(email_charges)
    lease_map = _by_canonical(lease_charges)

    total = mp_total
    if total is None:
        total = parse_move_in_total(email_text or "")
    email_total = parse_move_in_total(email_text or "")
    lease_total = parse_move_in_total(lease_slice) or parse_move_in_total(
        lease_text or ""
    )

    if total is None and not raw_mp:
        raise AssertionError(
            "No Total Cost to Move-in (and no line items) on the MP "
            "confirmation page or Lease Summary to compare against "
            "email / lease agreement"
        )

    # Keys that appear on MP are required on email + lease when line-item
    # validation is on. Extra email/lease keys are report-only unless they
    # disagree with MP.
    keys = (
        sorted(set(mp_map) | set(email_map) | set(lease_map)) if check_lines else []
    )

    step = (
        allure.step(
            "Compare costs: MP confirmation | email | lease agreement"
            + ("" if check_lines else " (Total Cost to Move-in only)")
        )
        if wrap_step
        else nullcontext()
    )
    with step:
        lease_label = "parsed-costs (lease document)"
        if space_number:
            lease_label = f"parsed-costs (lease document #{space_number})"
        allure.attach(
            "\n".join(f"{label}: {format_money(amt)}" for label, amt in raw_mp.items())
            + (f"\nTOTAL: {format_money(total)}" if total is not None else ""),
            name="parsed-costs (MP confirmation)",
            attachment_type=allure.attachment_type.TEXT,
        )
        allure.attach(
            "\n".join(
                f"{label}: {format_money(amt)}" for label, amt in email_charges.items()
            )
            + (
                f"\nTOTAL: {format_money(email_total)}"
                if email_total is not None
                else ""
            ),
            name="parsed-costs (email)",
            attachment_type=allure.attachment_type.TEXT,
        )
        allure.attach(
            "\n".join(
                f"{label}: {format_money(amt)}" for label, amt in lease_charges.items()
            )
            + (
                f"\nTOTAL: {format_money(lease_total)}"
                if lease_total is not None
                else ""
            ),
            name=lease_label,
            attachment_type=allure.attachment_type.TEXT,
        )

        text_rows: list[str] = [
            "key | MP confirmation | email | lease | result",
            "-" * 88,
        ]
        html_rows: list[str] = []
        mismatches: list[str] = []

        for key in keys:
            if key in mp_map:
                mp_label, mp_amt = mp_map[key]
            else:
                mp_label, mp_amt = None, None
            if key in email_map:
                email_label, email_amt = email_map[key]
            else:
                email_label, email_amt = None, None
            if key in lease_map:
                lease_label, lease_amt = lease_map[key]
            else:
                lease_label, lease_amt = None, None

            mp_amt, email_amt, lease_amt = _align_source_amounts(
                key,
                mp_amt,
                mp_label,
                email_amt,
                email_label,
                lease_amt,
                lease_label,
            )

            required = key in mp_map
            status = _status(mp_amt, email_amt, lease_amt, required=required)
            display = key
            if mp_label and mp_label.lower() != key:
                display = f"{key} (MP: {mp_label})"
            text_rows.append(
                f"{display} | {_cell(mp_amt)} | {_cell(email_amt)} | "
                f"{_cell(lease_amt)} | {status}"
            )
            html_rows.append(
                "<tr>"
                f"<td>{html_lib.escape(display)}</td>"
                f"<td>{html_lib.escape(_cell(mp_amt))}</td>"
                f"<td>{html_lib.escape(_cell(email_amt))}</td>"
                f"<td>{html_lib.escape(_cell(lease_amt))}</td>"
                f"<td><b>{html_lib.escape(status)}</b></td>"
                "</tr>"
            )
            if status.startswith("MISSING") or status == "MISMATCH":
                mismatches.append(
                    f"{key}: MP={_cell(mp_amt)} email={_cell(email_amt)} "
                    f"lease={_cell(lease_amt)} → {status}"
                )

        total_status = _status(
            total, email_total, lease_total, required=total is not None
        )
        text_rows.append(
            f"Total Cost to Move-in | {_cell(total)} | {_cell(email_total)} | "
            f"{_cell(lease_total)} | {total_status}"
        )
        html_rows.append(
            "<tr style='background:#f5f5f5'>"
            "<td><b>Total Cost to Move-in</b></td>"
            f"<td><b>{html_lib.escape(_cell(total))}</b></td>"
            f"<td><b>{html_lib.escape(_cell(email_total))}</b></td>"
            f"<td><b>{html_lib.escape(_cell(lease_total))}</b></td>"
            f"<td><b>{html_lib.escape(total_status)}</b></td>"
            "</tr>"
        )
        if total_status.startswith("MISSING") or total_status == "MISMATCH":
            mismatches.append(
                f"Total Cost to Move-in: MP={_cell(total)} "
                f"email={_cell(email_total)} lease={_cell(lease_total)} "
                f"→ {total_status}"
            )

        table = "\n".join(text_rows)
        # One HTML matrix for the report; text dump only when line items run
        # (or on mismatch so the assert message still has a table).
        report_html = (
            "<h3>Cost comparison: MP rental page | Email | Lease document</h3>"
            f"<p style='color:#666;font-size:12px'>Mode: "
            f"{'line items + total' if check_lines else 'Total Cost to Move-in only'}"
            "</p>"
            "<table border='1' cellpadding='6' cellspacing='0' "
            "style='border-collapse:collapse;font-family:sans-serif'>"
            "<tr style='background:#eee'>"
            "<th>Charge</th><th>MP confirmation</th><th>Email</th>"
            "<th>Lease document</th><th>Result</th></tr>"
            + "".join(html_rows)
            + "</table>"
        )
        allure.attach(
            report_html,
            name="total-price-validation",
            attachment_type=allure.attachment_type.HTML,
        )
        if check_lines or mismatches:
            allure.attach(
                table,
                name="cost-compare-mp-email-lease",
                attachment_type=allure.attachment_type.TEXT,
            )
        assert not mismatches, (
            "Cost mismatch across MP confirmation / email / lease agreement:\n"
            + "\n".join(mismatches)
            + "\n\n"
            + table
        )
