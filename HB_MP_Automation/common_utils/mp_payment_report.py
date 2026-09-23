"""Allure space-card screenshot from the lease agreement PDF.

Crops one PNG of the rented unit's card: SPACE INFORMATION (costs) +
COVERAGE + PAYMENT — matching the Superlease layout for that space
number. Multi-space PDFs pick the block for ``space_number`` only.
"""

from __future__ import annotations

import re

import allure
import pymupdf

# PAYMENT card body (not TOC / body copy).
_STRONG_PAYMENT = re.compile(
    r"Payment\s+Method.{0,120}Autopay\s+Enabled.{0,400}"
    r"(Card\s+Issuer|Card\s+Number|Name\s+on\s+Card|Name\s+on\s+Account)",
    re.I | re.S,
)


def _norm_space(space_number: str | None) -> str:
    return re.sub(r"^#", "", (space_number or "").strip())


def _space_rects(page: pymupdf.Page, space: str) -> list[pymupdf.Rect]:
    """Find label hits for ``#0040E`` / ``0040E`` on the page."""
    if not space:
        return []
    hits: list[pymupdf.Rect] = []
    for needle in (f"#{space}", space):
        try:
            hits.extend(page.search_for(needle))
        except Exception:
            continue
    # Prefer short hits (the unit id cell, not a long paragraph).
    return [r for r in hits if r.height <= 28]


def _header_rects(page: pymupdf.Page, title: str) -> list[pymupdf.Rect]:
    try:
        rects = page.search_for(title)
    except Exception:
        return []
    return [r for r in rects if r.height <= 40]


def _clickwrap_header_clip(
    page: pymupdf.Page, space_number: str | None
) -> pymupdf.Rect | None:
    """Clickwrap / traditional Lease Agreement top card (UNIT # + total + card)."""
    page_rect = page.rect
    space = _norm_space(space_number)
    text = page.get_text("text") or ""
    if not re.search(r"TOTAL\s+MOVE-?\s*In\s+Cost", text, re.I):
        return None
    if space and not re.search(
        rf"UNIT\s*#\s*:?\s*{re.escape(space)}\b", text, re.I
    ):
        # Wrong page / wrong unit
        if re.search(r"UNIT\s*#\s*:", text, re.I):
            return None
    # Prefer anchoring on UNIT # when present.
    anchors: list[pymupdf.Rect] = []
    for needle in (
        (f"UNIT #: {space}" if space else None),
        (f"UNIT #:{space}" if space else None),
        "UNIT #:",
        "TOTAL MOVE-In Cost",
        "TOTAL MOVE-IN COST",
        "Card Details",
    ):
        if not needle:
            continue
        try:
            anchors.extend(page.search_for(needle))
        except Exception:
            continue
    if not anchors:
        return None
    top = min(a.y0 for a in anchors) - 12
    # Include card details block under the total.
    bottom = top + 220
    for needle in ("Card Details", "Exp Date", "Credit Card Type"):
        try:
            hits = page.search_for(needle)
        except Exception:
            hits = []
        for h in hits:
            if h.y0 >= top - 4:
                bottom = max(bottom, h.y1 + 48)
    return pymupdf.Rect(
        page_rect.x0 + 10,
        max(page_rect.y0, top),
        page_rect.x1 - 10,
        min(page_rect.y1, bottom),
    )


def _space_card_clip(
    page: pymupdf.Page, space_number: str | None
) -> pymupdf.Rect | None:
    """Clip SPACE INFORMATION → COVERAGE → PAYMENT for ``space_number``.

    Falls back to clickwrap Lease Agreement header, then the first strong
    PAYMENT card when the space is unknown or not found on this page.
    """
    page_rect = page.rect
    space = _norm_space(space_number)
    space_hits = _space_rects(page, space) if space else []

    info_headers = _header_rects(page, "SPACE INFORMATION")
    coverage_headers = _header_rects(page, "COVERAGE")
    payment_headers = _header_rects(page, "PAYMENT")

    # Anchor: SPACE INFORMATION whose block contains this space id.
    info_anchor: pymupdf.Rect | None = None
    if space_hits and info_headers:
        space_y = min(r.y0 for r in space_hits)
        above = [h for h in info_headers if h.y0 <= space_y + 8]
        if above:
            info_anchor = max(above, key=lambda h: h.y0)
        else:
            # Space id might sit slightly above the blue bar in rare layouts.
            below = [h for h in info_headers if h.y0 >= space_y - 40]
            if below:
                info_anchor = min(below, key=lambda h: h.y0)

    # PAYMENT card that belongs to this space (space id in/near the band).
    payment_anchor: pymupdf.Rect | None = None
    for header in payment_headers:
        clip = pymupdf.Rect(
            page_rect.x0 + 12,
            max(page_rect.y0, header.y0 - 4),
            page_rect.x1 - 12,
            min(page_rect.y1, header.y1 + 340),
        )
        band = page.get_text("text", clip=clip) or ""
        if not _STRONG_PAYMENT.search(band):
            continue
        if space and space_hits:
            # Prefer PAYMENT whose band mentions this space, or that sits
            # below the space's SPACE INFORMATION and before the next one.
            if re.search(rf"#\s*{re.escape(space)}\b", band, re.I):
                payment_anchor = header
                break
            if info_anchor is not None and header.y0 >= info_anchor.y0 - 2:
                next_info = [
                    h for h in info_headers if h.y0 > info_anchor.y0 + 20
                ]
                if not next_info or header.y0 < next_info[0].y0:
                    payment_anchor = header
                    break
        else:
            payment_anchor = header
            break

    if info_anchor is not None and payment_anchor is not None:
        # End before the next SPACE INFORMATION (another unit) if present.
        end_y = min(page_rect.y1, payment_anchor.y1 + 300)
        for h in info_headers:
            if h.y0 > info_anchor.y0 + 40:
                end_y = min(end_y, h.y0 - 4)
                break
        # Include COVERAGE if it sits between info and payment.
        for h in coverage_headers:
            if info_anchor.y0 - 2 <= h.y0 <= end_y + 20:
                end_y = max(end_y, min(page_rect.y1, h.y1 + 160))
        end_y = max(end_y, min(page_rect.y1, payment_anchor.y1 + 280))
        return pymupdf.Rect(
            page_rect.x0 + 10,
            max(page_rect.y0, info_anchor.y0 - 8),
            page_rect.x1 - 10,
            end_y,
        )

    # Fallback: PAYMENT-only card (legacy behaviour).
    if payment_anchor is not None:
        return pymupdf.Rect(
            page_rect.x0 + 16,
            max(page_rect.y0, payment_anchor.y0 - 6),
            page_rect.x1 - 16,
            min(page_rect.y1, payment_anchor.y1 + 320),
        )
    for header in payment_headers:
        if header.height > 40:
            continue
        clip = pymupdf.Rect(
            page_rect.x0 + 16,
            max(page_rect.y0, header.y0 - 6),
            page_rect.x1 - 16,
            min(page_rect.y1, header.y1 + 320),
        )
        band = page.get_text("text", clip=clip) or ""
        if _STRONG_PAYMENT.search(band):
            return clip

    # Clickwrap / traditional Lease Agreement (no Superlease cards).
    return _clickwrap_header_clip(page, space_number)

def attach_payment_screenshots_from_pdf(
    pdf_bytes: bytes,
    *,
    document_name: str = "Superlease",
    space_number: str | None = None,
) -> int:
    """Attach one space-card PNG (costs + coverage + payment). Returns 1 or 0."""
    if not pdf_bytes:
        return 0
    space = _norm_space(space_number)
    step_label = "Space card (lease document screenshot)"
    if space:
        step_label = f"Space card #{space} (lease document screenshot)"
    with allure.step(step_label):
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            allure.attach(
                f"Could not open PDF for space-card screenshot: "
                f"{type(exc).__name__}: {exc}"[:800],
                name="payment-details",
                attachment_type=allure.attachment_type.TEXT,
            )
            return 0
        try:
            matrix = pymupdf.Matrix(2, 2)
            for page in doc:
                clip = _space_card_clip(page, space_number)
                if clip is None:
                    continue
                png = page.get_pixmap(
                    matrix=matrix, clip=clip, alpha=False
                ).tobytes("png")
                name = f"{document_name} space card"
                if space:
                    name = f"{document_name} space card #{space}"
                allure.attach(
                    png,
                    name=name,
                    attachment_type=allure.attachment_type.PNG,
                )
                return 1
        finally:
            doc.close()
        hint = f" for space #{space}" if space else ""
        allure.attach(
            f"No SPACE INFORMATION / PAYMENT block found in "
            f"{document_name} PDF{hint}.",
            name="payment-details",
            attachment_type=allure.attachment_type.TEXT,
        )
        return 0
