"""The storefront rental scenarios (user's list, 2026-09-14): Legacy Flow with
Traditional, Clickwrap or Super Lease signing, and 2Step Flow with Super Lease
signing - each paid by Credit Card or ACH, with or without autopay, in the
desktop and the mobile view, as an individual and as a business (RAB, user:
"cover RAB for all cases"). One case is one real rental on the sandbox,
checked on the storefront, in the guest's Mailinator inbox and in HB, and
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
    format_money,
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
    """Reserve, rent, check the emails and the HB tenant, then move out -
    also when a step fails, once the rental form has named the space.
    Pass move_out=False to leave a completed rental in place.
    Pass cancel_reservation_hold=False to leave an unfinished reservation.

    skip_hb_on_confirmation_failure: gateway matrix suites set this so a
    failed storefront rental-confirmation email check does not continue into
    HB tenant validation (the failure is still raised after an Allure note).

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
    try:
        # Desktop rentals share one tab with HB (URL switch). Do not slice
        # videos here — one continuous Playwright recording is enough.
        setup_class = MPTwoStepReservationSetup if two_step else MPLegacyReservationSetup
        setup = setup_class(storefront_page, environment_config, app_config, property_url=property_url)
        with allure.step("Reserve a unit" + (" as a business" if case.rab else "")):
            reservation_code = setup.reserve_unit(guest, renting_as_business=case.rab)
        reserved = True

        # The reservation email itself: checked and screenshotted here so a
        # rental case keeps the email-<code>.png the reservation-only tests
        # save (user, 2026-09-16 - it was the one screenshot missing from a
        # rental's folder). The Two-Step flow takes its own property name,
        # since it rents on the two_step_property rather than the
        # environment's default.
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
                        else security_deposit_amount(confirmation_charges or charges)
                    )
                    # The move-in date the rental form showed (today on desktop,
                    # the reservation's date on mobile), else today.
                    move_in_date = rental.get("move_in_date") or move_in_date
                    ending = rental.get("ending")
            except BaseException as rent_error:
                if skip_hb_on_confirmation_failure:
                    with allure.step("HB validation skipped: rental confirmation failed"):
                        allure.attach(
                            f"{type(rent_error).__name__}: {rent_error!r}"[:1500],
                            name="hb-validation-skipped",
                            attachment_type=allure.attachment_type.TEXT,
                        )
                raise
        rented = True

        confirmation_error: BaseException | None = None
        cost_charges = confirmation_charges or charges
        with allure.step(
            "Verify rental confirmation" + (" and autopay" if case.autopay else "") + " emails"
        ):
            try:
                email_body = setup.assert_rental_emails(
                    guest,
                    space_number,
                    move_in_date,
                    amount_paid,
                    security_deposit,
                    autopay=case.autopay,
                    charges=cost_charges if (two_step or ending == "pay_now") else None,
                )
            except BaseException as error:
                confirmation_error = error
                if skip_hb_on_confirmation_failure:
                    allure.attach(
                        f"{type(error).__name__}: {error!r}"[:1500],
                        name="rental-confirmation-failed",
                        attachment_type=allure.attachment_type.TEXT,
                    )

        if confirmation_error is not None:
            if skip_hb_on_confirmation_failure:
                with allure.step("HB validation skipped: rental confirmation failed"):
                    allure.attach(
                        "Storefront rental confirmation email check failed; "
                        "HB current-tenant validation was not run.",
                        name="hb-validation-skipped",
                        attachment_type=allure.attachment_type.TEXT,
                    )
            raise confirmation_error

        if confirmation_total is not None:
            allure.attach(
                f"${format_money(confirmation_total)}",
                name="Total Cost to Move-in (MP confirmation)",
                attachment_type=allure.attachment_type.TEXT,
            )

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

        # Sibling of HB tenant checks — Superlease PDF on the same shared tab
        # after tenant validation (desktop: one window, URL-switched).
        if cost_charges and (two_step or ending == "pay_now"):
            with allure.step(
                "Compare costs: MP confirmation | email | lease agreement"
            ):
                docs = HBTenantDocumentsPage(hb_login_page.page, timeout)
                docs.open_documents_menu()
                lease_doc = "Superlease"
                docs.assert_documents_listed([lease_doc])
                lease_text = docs.open_document_pdf_text(
                    lease_doc, space_number=space_number
                )
                assert_costs_match_three_ways(
                    mp_charges=confirmation_charges or {},
                    mp_total=confirmation_total,
                    email_text=email_body or "",
                    lease_text=lease_text,
                    fallback_charges=charges,
                    wrap_step=False,
                    space_number=space_number,
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
