"""The storefront rental scenarios (user's list, 2026-09-14): Legacy Flow with
Traditional, Clickwrap or Super Lease signing, and 2Step Flow with Super Lease
signing - each paid by Credit Card or ACH, with or without autopay, in the
desktop and the mobile view, as an individual and as a business (RAB, user:
"cover RAB for all cases"). One case is one real rental on the sandbox,
checked on the storefront, in the guest's Gmail inbox and in HB, and
then always moved out (user choice 2026-09-14)."""
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import allure
from playwright.sync_api import expect

from common_utils.browser_sessions import (
    capture_page_failure_artifacts,
    hb_admin_context,
    mark_storefront_failure_captured,
)
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_lease_costs import (
    assert_costs_match_three_ways,
    attach_move_in_cost_summary,
    lease_text_for_space,
    parse_move_in_total,
    security_deposit_amount,
)
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_move_out_page import HBMoveOutPage
from pages.common.hb_tenant_documents_page import HBTenantDocumentsPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage

_SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "screenshots"


@dataclass(frozen=True)
class RentalCase:
    payment: str  # "card" or "ach"
    autopay: bool
    view: str  # "desktop" or "mobile"
    rab: bool
    # False (default): skip reservation-hold + reservation email — go straight
    # to rental (Two-Step and Legacy both click Rent Now on the unit form).
    # True: full Reserve → email → rent.
    reserve: bool = False

    @property
    def title(self) -> str:
        """The scenario's name as in the user's list, e.g. "Credit Card with
        Autopay-DesktopView-RAB"."""
        payment = "ACH" if self.payment == "ach" else "Credit Card"
        autopay = " with Autopay" if self.autopay else ""
        view = "MobileView" if self.view == "mobile" else "DesktopView"
        renter = "RAB" if self.rab else "Individual"
        return f"{payment}{autopay}-{view}-{renter}"

    @property
    def markers(self) -> set[str]:
        """The pytest markers a test of this case carries (checked by
        tests/mp/rentals/conftest.py's rental_case_runner, so a test marked
        "ach" can't quietly run a card case)."""
        return {
            self.payment,
            "autopay" if self.autopay else "no_autopay",
            self.view,
            "rab" if self.rab else "individual",
        }


def _log_in(hb_login_page) -> None:
    """Reuse the module HB admin window on a clean dashboard shell.

    Signing / Clear Cache leave Settings open; Tenants needs the main
    shell (see HBLoginPage.ensure_on_dashboard).
    """
    hb_login_page.ensure_on_dashboard()


def _compare_costs_mp_email_lease(
    *,
    hb_login_page,
    timeout: float,
    hb_property_name: str,
    guest_name: str,
    space_number: str,
    mp_charges: dict[str, float],
    mp_total: float | None,
    email_text: str,
    fallback_charges: dict[str, float] | None,
    tenant_already_open: bool = False,
    best_effort: bool = False,
    two_step: bool = False,
    lease_artifacts: dict | None = None,
) -> None:
    """Top-level Allure audit step: move-in totals across sources.

    Attaches email Superlease PDFs together (Pay Now + Updated for two-step),
    opens HB lease once, summary card, then detail matrices.

    ``best_effort``: on failure attach the error and return so an earlier
    storefront failure stays the primary test result.
    """
    from common_utils.mp_rental_emails import (
        _allure_doc_name,
        _attach_superlease_pdf_bytes,
        ensure_email_superlease_pdf,
    )

    artifacts = lease_artifacts or {}
    step_name = f"Compare costs: move-in totals (#{space_number})"
    if best_effort:
        step_name += " (best effort after earlier failure)"
    with allure.step(step_name):
        try:
            context = hb_login_page.page.context
            with allure.step(f"Superlease PDFs (#{space_number})"):
                pay_now_label = (
                    "Superlease (Pay Now)" if two_step else "Superlease (email)"
                )
                pay_now_pdf = ensure_email_superlease_pdf(
                    context,
                    artifacts,
                    space_number=space_number,
                    pdf_key="pay_now_pdf",
                    text_key="pay_now_pdf_text",
                    url_key="pay_now_pdf_url",
                    document_label=pay_now_label,
                )
                if pay_now_pdf:
                    _attach_superlease_pdf_bytes(
                        pay_now_pdf,
                        allure_name=_allure_doc_name(pay_now_label, space_number),
                        document_label=pay_now_label,
                        space_number=space_number,
                    )
                else:
                    allure.attach(
                        "Pay Now / rental confirmation Superlease PDF not available.",
                        name=f"{pay_now_label} missing",
                        attachment_type=allure.attachment_type.TEXT,
                    )

                updated_text = ""
                if two_step:
                    updated_pdf = ensure_email_superlease_pdf(
                        context,
                        artifacts,
                        space_number=space_number,
                        pdf_key="updated_superlease_pdf",
                        text_key="updated_superlease_pdf_text",
                        url_key="updated_superlease_url",
                        document_label="Updated Superlease (Get Access)",
                    )
                    updated_text = artifacts.get("updated_superlease_pdf_text") or ""
                    if updated_pdf:
                        _attach_superlease_pdf_bytes(
                            updated_pdf,
                            allure_name=_allure_doc_name(
                                "Updated Superlease (Get Access)", space_number
                            ),
                            document_label="Updated Superlease (Get Access)",
                            space_number=space_number,
                        )
                    else:
                        allure.attach(
                            "Updated Superlease PDF not available from Get Access email.",
                            name="Updated Superlease (Get Access) missing",
                            attachment_type=allure.attachment_type.TEXT,
                        )

            if not tenant_already_open:
                with allure.step(f"Open HB tenant for lease PDF (#{space_number})"):
                    _log_in(hb_login_page)
                    tenants = HBTenantSpacesPage(hb_login_page.page, timeout)
                    tenants.open_tenants(hb_property_name)
                    tenants.open_storefront_tenant(guest_name, space_number)
            with allure.step(f"HB lease PDF (#{space_number})"):
                docs = HBTenantDocumentsPage(hb_login_page.page, timeout)
                docs.open_documents_menu()
                lease_doc = docs.resolve_lease_document_name()
                docs.assert_documents_listed([lease_doc])
                lease_text = docs.open_document_pdf_text(
                    lease_doc, space_number=space_number
                )

            pay_now_total = parse_move_in_total(email_text or "")
            hb_slice = lease_text_for_space(lease_text or "", space_number)
            hb_total = parse_move_in_total(hb_slice) or parse_move_in_total(
                lease_text or ""
            )
            get_access_body = artifacts.get("get_access_email_body") or ""
            if not updated_text:
                updated_text = artifacts.get("updated_superlease_pdf_text") or ""
            get_access_total = (
                parse_move_in_total(get_access_body) if get_access_body else None
            )
            updated_total = (
                (
                    parse_move_in_total(
                        lease_text_for_space(updated_text, space_number)
                    )
                    or parse_move_in_total(updated_text)
                )
                if updated_text
                else None
            )

            summary_rows: list[tuple[str, float | None, str]] = [
                ("MP confirmation", mp_total, "from Rent it confirmation page"),
                (
                    "Pay Now email" if two_step else "Rental Confirmation email",
                    pay_now_total,
                    "Account Summary",
                ),
                (f"HB {lease_doc}", hb_total, "Documents panel"),
            ]
            if two_step:
                summary_rows.append(
                    (
                        "Get Access email",
                        get_access_total,
                        "second Rental Confirmation",
                    )
                )
                summary_rows.append(
                    (
                        "Updated Superlease",
                        updated_total,
                        "attached above under Superlease PDFs"
                        if artifacts.get("updated_superlease_pdf")
                        else "not captured from Get Access email",
                    )
                )
            attach_move_in_cost_summary(
                space_number=space_number,
                sources=summary_rows,
                reference_label="MP confirmation",
            )

            with allure.step(
                "Detail: MP confirmation | Pay Now email | HB lease"
                if two_step
                else "Detail: MP confirmation | email | HB lease"
            ):
                assert_costs_match_three_ways(
                    mp_charges=mp_charges or {},
                    mp_total=mp_total,
                    email_text=email_text or "",
                    lease_text=lease_text,
                    fallback_charges=fallback_charges,
                    wrap_step=False,
                    space_number=space_number,
                    email_column="Pay Now email" if two_step else "Email",
                    lease_column=f"HB {lease_doc}",
                    report_name="total-price-validation",
                )

            if two_step:
                if updated_text:
                    with allure.step(
                        "Detail (2-step): MP confirmation | Get Access email | "
                        "Updated Superlease"
                    ):
                        assert_costs_match_three_ways(
                            mp_charges=mp_charges or {},
                            mp_total=mp_total,
                            email_text=get_access_body or email_text or "",
                            lease_text=updated_text,
                            fallback_charges=fallback_charges,
                            wrap_step=False,
                            space_number=space_number,
                            email_column="Get Access email",
                            lease_column="Updated Superlease",
                            report_name="total-price-validation-updated-superlease",
                        )
                else:
                    with allure.step(
                        "Detail (2-step): Updated Superlease compare skipped"
                    ):
                        allure.attach(
                            "No Updated Superlease PDF text — second cost matrix "
                            "skipped. See Superlease PDFs substep above.",
                            name="updated-superlease-compare-skipped",
                            attachment_type=allure.attachment_type.TEXT,
                        )
        except BaseException as error:
            if not best_effort:
                raise
            allure.attach(
                f"{type(error).__name__}: {error!r}"[:2000],
                name="cost-compare-best-effort-failed",
                attachment_type=allure.attachment_type.TEXT,
            )



def move_out_rental(
    hb_login_page,
    timeout: float,
    hb_property_name: str,
    guest_name: str,
    space_number: str,
    tenant_url: str | None = None,
) -> None:
    """From the tenant's page when the case already reached it (no Tenants
    grid search), else found through the Tenants list."""
    with allure.step(f"Clean up: move out space {space_number}"):
        _log_in(hb_login_page)
        page = hb_login_page.page
        if tenant_url:
            page.goto(tenant_url, wait_until="domcontentloaded")
        else:
            tenants = HBTenantSpacesPage(page, timeout)
            tenants.open_tenants(hb_property_name)
            tenants.open_storefront_tenant(guest_name, space_number)
            tenant_url = page.url
        try:
            HBMoveOutPage(page, timeout).move_out_space(space_number, "No Longer Needed")
        except AssertionError as not_confirmed:
            # HB can finish a move-out after its drawer gives up (2026-09-14:
            # "did not complete" for 0088, yet the space was Available minutes
            # later), so the tenant page decides.
            allure.attach(
                repr(not_confirmed)[:600], name="move-out drawer did not confirm - checking the tenant page",
                attachment_type=allure.attachment_type.TEXT,
            )
        closed_leases = page.get_by_text(re.compile(r"CLOSED LEASES")).first
        for attempt in range(4):
            page.goto(tenant_url, wait_until="domcontentloaded")
            try:
                expect(closed_leases).to_be_visible(timeout=timeout / 2)
                return
            except AssertionError:
                if attempt == 3:
                    raise


def cancel_reservation(hb_login_page, timeout: float, hb_property_name: str, guest_email: str) -> None:
    with allure.step(f"Clean up: cancel the reservation of {guest_email}"):
        _log_in(hb_login_page)
        leads = HBLeadManagementPage(hb_login_page.page, timeout)
        leads.open_leads(hb_property_name)
        leads.cancel_reservation_for_lead(guest_email, "Automation - cancel a rental test's reservation")
        leads.assert_lead_not_active(guest_email)


def _clean_up(
    hb_login_page,
    timeout: float,
    hb_property_name: str,
    guest: dict,
    space_number: str | None,
    rented: bool,
    tenant_url: str | None,
    move_out: bool = True,
    cancel_reservation_hold: bool = True,
) -> None:
    """Moves a created rental out - a failure there is raised, as the space
    stays rented. When the case failed before the rental was confirmed, it
    tries the move-out too (the storefront may have created it anyway) and
    otherwise cancels the reservation - a failed case leaves nothing
    behind.

    Pass move_out=False (pytest --no-move-out / [cleanup] move_out_after_rental
    = false) to leave a completed rental in place. Pass
    cancel_reservation_hold=False (--no-cancel-reservation /
    [cleanup] cancel_reservation_after = false) to leave an unfinished
    reservation hold in place for inspection.
    """
    guest_name = f"{guest['first_name']} {guest['last_name']}"
    if rented and not move_out:
        allure.attach(
            f"{guest['email']}, space {space_number}, property {hb_property_name}",
            name="move-out skipped (--no-move-out)",
            attachment_type=allure.attachment_type.TEXT,
        )
        return
    if rented:
        move_out_rental(hb_login_page, timeout, hb_property_name, guest_name, space_number, tenant_url)
        return
    if space_number and move_out:
        try:
            move_out_rental(hb_login_page, timeout, hb_property_name, guest_name, space_number)
            return
        except Exception as move_out_error:
            allure.attach(
                repr(move_out_error)[:1000], name=f"space {space_number} not moved out - cancelling the reservation",
                attachment_type=allure.attachment_type.TEXT,
            )
    if not cancel_reservation_hold:
        allure.attach(
            f"{guest['email']}, space {space_number}, property {hb_property_name}",
            name="cancel-reservation skipped (--no-cancel-reservation)",
            attachment_type=allure.attachment_type.TEXT,
        )
        return
    cancel_reservation(hb_login_page, timeout, hb_property_name, guest["email"])


def _attach_storefront(page) -> None:
    """Capture Mariposa as it failed — before cleanup navigates the page to HB.

    Scrolls the error/Pay Now into view so long rental forms are readable in
    both the viewport shot and the execution video's last storefront frame.
    """
    try:
        capture_page_failure_artifacts(
            page, label="mariposa-storefront", reports_dir=_SCREENSHOTS_DIR
        )
        mark_storefront_failure_captured()
    except Exception as capture_error:
        allure.attach(
            repr(capture_error)[:600],
            name="mariposa-storefront not captured",
            attachment_type=allure.attachment_type.TEXT,
        )


def run_rental_case(
    *,
    case: RentalCase,
    two_step: bool,
    storefront_page,
    hb_login_page,
    environment_config,
    app_config,
    property_config,
    property_url: str,
    rental_data: dict,
    guest: dict,
    move_out: bool = True,
    cancel_reservation_hold: bool = True,
    skip_hb_on_confirmation_failure: bool = False,
    card: dict | None = None,
) -> None:
    """Reserve (optional), rent, check the emails and the HB tenant, then move out -
    also when a step fails, once the rental form has named the space.
    Pass move_out=False to leave a completed rental in place.
    Pass cancel_reservation_hold=False to leave an unfinished reservation.

    By default (case.reserve=False) skips the reservation hold and confirmation
    email: both flows click Rent Now on the unit form. Pass
    RentalCase(reserve=True) for the full Reserve → email → rent path.

    skip_hb_on_confirmation_failure: gateway matrix suites set this so a
    failed storefront rental-confirmation email check does not continue into
    HB tenant payment validation. Cost compare still runs best-effort (lease
    PDF + Allure attachments) before the email failure is re-raised.

    card: optional overrides for card_number / card_expiry / card_cvc
    (hosted-field format cases — MRECOM-323). Defaults to secrets.ini.
    """
    timeout = app_config.getint("browser", "timeout")
    guest_name = f"{guest['first_name']} {guest['last_name']}"
    setup = None
    space_number = None
    reserved = False
    rented = False
    tenant_url = None
    move_in_date = date.today()
    failure = None
    charges: dict[str, float] | None = None
    confirmation_charges: dict[str, float] | None = None
    confirmation_total: float | None = None
    ending: str | None = None
    email_body: str | None = None
    amount_paid: float | None = None
    security_deposit: float | None = None
    try:
        # Desktop rentals share one tab with HB (URL switch). Do not slice
        # videos here — one continuous Playwright recording is enough.
        setup_class = MPTwoStepReservationSetup if two_step else MPLegacyReservationSetup
        setup = setup_class(storefront_page, environment_config, app_config, property_url=property_url)

        if case.reserve:
            with allure.step(
                "Reserve a unit" + (" as a business" if case.rab else "")
            ):
                reservation_code = setup.reserve_unit(
                    guest, renting_as_business=case.rab
                )
            reserved = True

            # The reservation email itself: checked and screenshotted here so a
            # rental case keeps the email-<code>.png the reservation-only tests
            # save (user, 2026-09-16).
            with allure.step("Verify reservation confirmation email"):
                if two_step:
                    setup.assert_confirmation_email(
                        guest,
                        reservation_code,
                        property_name=property_config.lease_configuration_property_name
                        or property_config.hb_property_name,
                    )
                else:
                    setup.assert_confirmation_email(guest, reservation_code)

            with allure.step(f"Rent it: {case.title}"):
                try:
                    if two_step:
                        bill = setup.rent_reserved_unit(
                            guest,
                            {**rental_data, "enroll_autopay": case.autopay},
                            payment_method=case.payment,
                            card=card,
                        )
                        space_number, amount_paid = bill["space_number"], bill["pay_now"]
                        charges = bill.get("charges") or {}
                        confirmation_charges = bill.get("confirmation_charges") or {}
                        confirmation_total = bill.get("confirmation_total")
                        if confirmation_total is None and amount_paid is not None:
                            confirmation_total = amount_paid
                        security_deposit = security_deposit_amount(
                            confirmation_charges or charges
                        )
                        ending = "pay_now"
                    else:
                        rental = setup.convert_reservation_to_rental(
                            guest,
                            rental_data,
                            payment_method=case.payment,
                            autopay=case.autopay,
                            card=card,
                        )
                        space_number, amount_paid = rental["space_number"], rental["total"]
                        charges = rental.get("charges") or {}
                        confirmation_charges = rental.get("confirmation_charges") or {}
                        confirmation_total = rental.get("confirmation_total")
                        security_deposit = (
                            rental.get("security_deposit")
                            if rental.get("security_deposit") is not None
                            else security_deposit_amount(
                                confirmation_charges or charges
                            )
                        )
                        move_in_date = rental.get("move_in_date") or move_in_date
                        ending = rental.get("ending")
                except BaseException as rent_error:
                    if skip_hb_on_confirmation_failure:
                        with allure.step(
                            "HB validation skipped: rental confirmation failed"
                        ):
                            allure.attach(
                                f"{type(rent_error).__name__}: {rent_error!r}"[:1500],
                                name="hb-validation-skipped",
                                attachment_type=allure.attachment_type.TEXT,
                            )
                    raise
        else:
            # Direct rental: no reservation email / hold wait.
            with allure.step(
                f"Direct rent (skip reservation): {case.title}"
                + (" as a business" if case.rab else "")
            ):
                try:
                    if two_step:
                        bill = setup.rent_unit_directly(
                            guest,
                            {**rental_data, "enroll_autopay": case.autopay},
                            payment_method=case.payment,
                            card=card,
                            renting_as_business=case.rab,
                        )
                        space_number, amount_paid = bill["space_number"], bill["pay_now"]
                        charges = bill.get("charges") or {}
                        confirmation_charges = bill.get("confirmation_charges") or {}
                        confirmation_total = bill.get("confirmation_total")
                        if confirmation_total is None and amount_paid is not None:
                            confirmation_total = amount_paid
                        security_deposit = security_deposit_amount(
                            confirmation_charges or charges
                        )
                        ending = "pay_now"
                        move_in_date = setup.move_in_date or move_in_date
                    else:
                        rental = setup.rent_unit_directly(
                            guest,
                            rental_data,
                            payment_method=case.payment,
                            autopay=case.autopay,
                            card=card,
                            renting_as_business=case.rab,
                        )
                        space_number, amount_paid = rental["space_number"], rental["total"]
                        charges = rental.get("charges") or {}
                        confirmation_charges = rental.get("confirmation_charges") or {}
                        confirmation_total = rental.get("confirmation_total")
                        security_deposit = (
                            rental.get("security_deposit")
                            if rental.get("security_deposit") is not None
                            else security_deposit_amount(
                                confirmation_charges or charges
                            )
                        )
                        move_in_date = (
                            rental.get("move_in_date")
                            or setup.move_in_date
                            or move_in_date
                        )
                        ending = rental.get("ending")
                except BaseException as rent_error:
                    if skip_hb_on_confirmation_failure:
                        with allure.step(
                            "HB validation skipped: rental confirmation failed"
                        ):
                            allure.attach(
                                f"{type(rent_error).__name__}: {rent_error!r}"[:1500],
                                name="hb-validation-skipped",
                                attachment_type=allure.attachment_type.TEXT,
                            )
                    raise
        rented = True

        confirmation_error: BaseException | None = None
        # Prefer Lease Summary charges for email asserts (include coverage);
        # confirmation-page parse feeds three-way MP column when present.
        cost_charges = charges or confirmation_charges
        mp_cost_charges = confirmation_charges or charges
        email_body_parts: list[str] = []
        lease_artifacts: dict = {}
        email_step = (
            "Verify rental confirmation emails"
            + (" (Pay Now + Get Access)" if two_step else "")
            + (" + autopay" if case.autopay else "")
        )
        with allure.step(email_step):
            try:
                email_body = setup.assert_rental_emails(
                    guest,
                    space_number,
                    move_in_date,
                    amount_paid,
                    security_deposit,
                    autopay=case.autopay,
                    charges=cost_charges if (two_step or ending == "pay_now") else None,
                    body_out=email_body_parts,
                    lease_artifacts_out=lease_artifacts,
                )
            except BaseException as error:
                confirmation_error = error
                email_body = email_body_parts[0] if email_body_parts else ""
                if skip_hb_on_confirmation_failure:
                    allure.attach(
                        f"{type(error).__name__}: {error!r}"[:1500],
                        name="rental-confirmation-failed",
                        attachment_type=allure.attachment_type.TEXT,
                    )

        # Email failed: still attempt cost compare for the report (lease PDF
        # needs HB), then re-raise the email error as the primary failure.
        if confirmation_error is not None:
            if skip_hb_on_confirmation_failure:
                with allure.step("HB validation skipped: rental confirmation failed"):
                    allure.attach(
                        "Storefront rental confirmation email check failed; "
                        "HB current-tenant validation was not run. "
                        "Cost compare may still run best-effort below.",
                        name="hb-validation-skipped",
                        attachment_type=allure.attachment_type.TEXT,
                    )
            if cost_charges and (two_step or ending == "pay_now") and space_number:
                _compare_costs_mp_email_lease(
                    hb_login_page=hb_login_page,
                    timeout=timeout,
                    hb_property_name=property_config.hb_property_name,
                    guest_name=guest_name,
                    space_number=space_number,
                    mp_charges=mp_cost_charges or {},
                    mp_total=confirmation_total,
                    email_text=email_body or "",
                    fallback_charges=charges,
                    best_effort=True,
                    two_step=two_step,
                    lease_artifacts=lease_artifacts,
                )
            raise confirmation_error

        with allure.step(
            "Verify in HB: a current tenant, paid"
            + (", on autopay" if case.autopay else ", no autopay")
        ):
            # Reuse module hb_admin_session — do not open a second HB window.
            _log_in(hb_login_page)
            tenants = HBTenantSpacesPage(hb_login_page.page, timeout)
            tenants.open_tenants(property_config.hb_property_name)
            tenants.assert_web_rental_tenant(
                guest_name,
                space_number,
                move_in_date,
                amount_paid,
                card_last4=(
                    (
                        (card or {}).get("card_number")
                        or environment_config.card_number
                        or ""
                    )[-4:]
                    if case.autopay and case.payment == "card"
                    else None
                ),
                ach_last4=(
                    environment_config.ach_account_number[-4:]
                    if case.autopay and case.payment == "ach"
                    else None
                ),
                no_autopay=not case.autopay,
            )
            tenant_url = hb_login_page.page.url

        # Sibling of HB tenant checks — lease PDF on the same shared tab
        # after tenant validation (desktop: one window, URL-switched).
        # Superlease when configured; clickwrap/traditional use Lease Agreement.
        if cost_charges and (two_step or ending == "pay_now"):
            _compare_costs_mp_email_lease(
                hb_login_page=hb_login_page,
                timeout=timeout,
                hb_property_name=property_config.hb_property_name,
                guest_name=guest_name,
                space_number=space_number,
                mp_charges=mp_cost_charges or {},
                mp_total=confirmation_total,
                email_text=email_body or "",
                fallback_charges=charges,
                tenant_already_open=True,
                two_step=two_step,
                lease_artifacts=lease_artifacts,
            )
    except BaseException as error:
        failure = error
        if isinstance(error, Exception):
            _attach_storefront(storefront_page)
        raise
    finally:
        space_number = space_number or (setup.space_number if setup else None)
        if reserved:
            try:
                # Prefer the dedicated HB admin page (module hb_admin_session).
                # Only when storefront and HB share one page (legacy callers)
                # and the case failed on Mariposa, clean up in a fresh HB
                # context so the recorded storefront video stays on the error.
                same_page = storefront_page is hb_login_page.page
                if failure is not None and same_page:
                    browser = hb_login_page.page.context.browser
                    if browser is None:
                        _clean_up(
                            hb_login_page,
                            timeout,
                            property_config.hb_property_name,
                            guest,
                            space_number,
                            rented,
                            tenant_url,
                            move_out=move_out,
                            cancel_reservation_hold=cancel_reservation_hold,
                        )
                    else:
                        with hb_admin_context(
                            browser, environment_config, app_config
                        ) as cleanup_login:
                            _clean_up(
                                cleanup_login,
                                timeout,
                                property_config.hb_property_name,
                                guest,
                                space_number,
                                rented,
                                tenant_url,
                                move_out=move_out,
                                cancel_reservation_hold=cancel_reservation_hold,
                            )
                else:
                    _clean_up(
                        hb_login_page,
                        timeout,
                        property_config.hb_property_name,
                        guest,
                        space_number,
                        rented,
                        tenant_url,
                        move_out=move_out,
                        cancel_reservation_hold=cancel_reservation_hold,
                    )
            except Exception as cleanup_error:
                allure.attach(
                    repr(cleanup_error)[:1000],
                    name=f"NOT cleaned up: {guest['email']}, space {space_number}",
                    attachment_type=allure.attachment_type.TEXT,
                )
                if failure is None:
                    raise
