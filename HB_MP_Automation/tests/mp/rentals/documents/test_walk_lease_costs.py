"""Live walk: after Super Lease rental confirmation, capture where cost
line items appear (email body, email lease download, HB Documents PDF,
HB communication). Writes reports/walk_lease_costs/*.txt — not a gate.

Run:
  py -3 -m pytest tests/mp/rentals/documents/test_walk_lease_costs.py -v --no-move-out
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import allure
import pytest

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from common_utils.email_utils import (
    find_email_link,
    get_email_plain_text,
    get_email_text,
    wait_for_email,
)
from common_utils.mp_lease_costs import assert_cost_line_items, parse_charges_from_summary_text
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_rental_cases import move_out_rental
from common_utils.mp_rental_extras import rental_extras
from config.config_reader import load_property
from pages.common.hb_tenant_documents_page import HBTenantDocumentsPage
from pages.common.hb_tenant_notes_page import HBTenantNotesPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage

WALK_DIR = Path(__file__).resolve().parents[4] / "reports" / "walk_lease_costs"


def _write(name: str, text: str) -> Path:
    WALK_DIR.mkdir(parents=True, exist_ok=True)
    path = WALK_DIR / name
    path.write_text(text, encoding="utf-8")
    allure.attach(text[:8000], name=name, attachment_type=allure.attachment_type.TEXT)
    return path


def _money_lines(text: str) -> str:
    return "\n".join(
        line.strip()
        for line in text.splitlines()
        if "$" in line or re.search(r"total|deposit|rent|fee|coverage|tax", line, re.I)
    )


@allure.feature("MP Rentals")
@allure.story("Walk: lease cost sources after confirmation")
@pytest.mark.usefixtures("legacy_superlease_signing")
@pytest.mark.mp_rental
class TestWalkLeaseCostSources:
    @allure.title("Walk Super Lease costs in email + lease document + HB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_walk_lease_cost_sources(
        self,
        browser,
        environment,
        environment_config,
        app_config,
        mp_guest,
        property_landing_page_url,
        hb_admin_session,
        test_data,
        move_out_after_rental,
    ) -> None:
        property_key = app_config.get(environment, "legacy_property", fallback="").strip()
        if not property_key:
            pytest.skip(f"No legacy_property for {environment}")
        prop = load_property(app_config, environment, property_key)
        timeout = app_config.getint("browser", "timeout")
        property_url = property_landing_page_url(
            environment_config.mp_base_url, prop.mp_state, prop.mp_city
        )
        rental_data = test_data("mp_rental")
        extras = rental_extras(rental_data, coverage=True)
        guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
        space_number: str | None = None
        store_ctx = browser.new_context(**desktop_context_options(app_config))
        notes: list[str] = []
        try:
            page = store_ctx.new_page()
            prepare_desktop_page(page, app_config)
            setup = MPLegacyReservationSetup(
                page, environment_config, app_config, property_url=property_url
            )
            with allure.step("Reserve + rent (Super Lease / Pay Now)"):
                setup.reserve_unit(mp_guest, renting_as_business=False)
                rental = setup.convert_reservation_to_rental(
                    mp_guest,
                    rental_data,
                    payment_method="card",
                    autopay=False,
                    extras=extras,
                    include_alternate=False,
                )
                space_number = rental["space_number"]
                charges = rental.get("charges") or {}
                amount_paid = rental["total"]
                move_in = rental.get("move_in_date") or date.today()
                notes.append(f"ending={rental.get('ending')!r} space={space_number}")
                notes.append(f"charges={charges!r}")
                notes.append(f"total={amount_paid}")
                _write("01_storefront_charges.txt", "\n".join(notes))

            with allure.step("Rental Confirmation email — body + lease links"):
                message = wait_for_email(
                    mp_guest["email"], subject_contains="Rental Confirmation"
                )
                html = get_email_text(message)
                plain = get_email_plain_text(message)
                _write("02_email_plain.txt", plain)
                _write("02_email_money_lines.txt", _money_lines(plain))
                _write("02_email_html_snip.txt", html[:12000])
                links = re.findall(
                    r"href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                    html,
                    re.I | re.S,
                )
                link_lines = []
                for href, inner in links:
                    label = re.sub(r"<[^>]+>|\s+", " ", inner).strip()
                    if re.search(
                        r"lease|super|download|pdf|document|agreement",
                        f"{label} {href}",
                        re.I,
                    ):
                        link_lines.append(f"{label!r} -> {href}")
                _write(
                    "03_email_lease_links.txt",
                    "\n".join(link_lines) or "(no lease/download links found)",
                )
                pdf_from_email = ""
                for label in (
                    "Download Superlease",
                    "Download Super Lease",
                    "Download Lease",
                    "View Lease",
                    "Superlease",
                ):
                    try:
                        url = find_email_link(message, label)
                    except AssertionError:
                        continue
                    notes.append(f"email link {label!r} = {url}")
                    try:
                        response = page.context.request.get(url)
                        notes.append(f"  GET status={response.status} bytes={len(response.body())}")
                        if response.status == 200 and response.body()[:4] == b"%PDF":
                            from io import BytesIO
                            from pypdf import PdfReader

                            pdf_from_email = "".join(
                                (p.extract_text() or "")
                                for p in PdfReader(BytesIO(response.body())).pages
                            )
                            _write("04_email_lease_pdf_text.txt", pdf_from_email[:8000])
                            _write(
                                "04_email_lease_pdf_money.txt",
                                _money_lines(pdf_from_email),
                            )
                            break
                    except Exception as err:
                        notes.append(f"  fetch failed: {type(err).__name__}: {err}")
                if charges:
                    try:
                        assert_cost_line_items(
                            plain, charges, total=amount_paid, source="email walk"
                        )
                        notes.append("email cost assert: PASS")
                    except AssertionError as err:
                        notes.append(f"email cost assert: FAIL {err}")
                if pdf_from_email and charges:
                    try:
                        assert_cost_line_items(
                            pdf_from_email,
                            charges,
                            total=amount_paid,
                            source="email PDF walk",
                        )
                        notes.append("email PDF cost assert: PASS")
                    except AssertionError as err:
                        notes.append(f"email PDF cost assert: FAIL {err}")

            with allure.step("HB tenant Documents Superlease PDF"):
                hb = hb_admin_session
                hb.ensure_on_dashboard()
                tenants = HBTenantSpacesPage(hb.page, timeout)
                tenants.open_tenants(prop.hb_property_name)
                tenants.open_storefront_tenant(guest_name, space_number)
                docs = HBTenantDocumentsPage(hb.page, timeout)
                docs.open_documents_menu()
                docs.assert_documents_listed(["Superlease"])
                pdf_hb = docs.open_document_pdf_text(
                    "Superlease", space_number=space_number
                )
                _write("05_hb_documents_pdf_text.txt", pdf_hb[:8000])
                _write("05_hb_documents_pdf_money.txt", _money_lines(pdf_hb))
                if charges:
                    try:
                        assert_cost_line_items(
                            pdf_hb, charges, total=amount_paid, source="HB Documents walk"
                        )
                        notes.append("HB Documents cost assert: PASS")
                    except AssertionError as err:
                        notes.append(f"HB Documents cost assert: FAIL {err}")

            with allure.step("HB tenant Communication email card (if present)"):
                try:
                    notes_page = HBTenantNotesPage(hb.page, timeout)
                    notes_page.open_in_communication_center(guest_name)
                    body_text = hb.page.locator("body").inner_text()
                    _write("06_hb_communication_body_snip.txt", body_text[:8000])
                    _write(
                        "06_hb_communication_money.txt",
                        _money_lines(body_text),
                    )
                    notes.append("HB communication panel opened")
                except Exception as err:
                    notes.append(
                        f"HB communication not walked: {type(err).__name__}: {err}"
                    )

            _write("00_walk_notes.txt", "\n".join(notes))
            # Walk always passes — evidence is in reports/walk_lease_costs/
            assert space_number, "rental did not produce a space"
            assert rental.get("ending") == "pay_now", rental.get("ending")
        finally:
            close_context_with_videos(store_ctx, app_config, name="walk-storefront-video")
            if space_number and move_out_after_rental:
                try:
                    move_out_rental(
                        hb_admin_session,
                        timeout,
                        prop.hb_property_name,
                        guest_name,
                        space_number,
                    )
                except Exception as cleanup_error:
                    _write("99_cleanup_error.txt", repr(cleanup_error))
