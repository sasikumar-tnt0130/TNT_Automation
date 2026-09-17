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

import allure
from playwright.sync_api import expect

from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_two_step_reservation_setup import MPTwoStepReservationSetup
from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_move_out_page import HBMoveOutPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


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
    if hb_login_page.open_login_page():
        hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()


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
    with allure.step(f"Clean-up: move out space {space_number}"):
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
    with allure.step(f"Clean-up: cancel the reservation of {guest_email}"):
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
) -> None:
    """Moves a created rental out - a failure there is raised, as the space
    stays rented. When the case failed before the rental was confirmed, it
    tries the move-out too (the storefront may have created it anyway) and
    otherwise cancels the reservation - a failed case leaves nothing
    behind."""
    guest_name = f"{guest['first_name']} {guest['last_name']}"
    if rented:
        move_out_rental(hb_login_page, timeout, hb_property_name, guest_name, space_number, tenant_url)
        return
    if space_number:
        try:
            move_out_rental(hb_login_page, timeout, hb_property_name, guest_name, space_number)
            return
        except Exception as move_out_error:
            allure.attach(
                repr(move_out_error)[:1000], name=f"space {space_number} not moved out - cancelling the reservation",
                attachment_type=allure.attachment_type.TEXT,
            )
    cancel_reservation(hb_login_page, timeout, hb_property_name, guest["email"])


def _attach_storefront(page) -> None:
    """conftest's failure hook captures the HB `page` after clean-up, so a
    failed case attaches the storefront page (desktop or phone) as it was
    when the step failed."""
    try:
        allure.attach(page.url, name="storefront URL at failure", attachment_type=allure.attachment_type.URI_LIST)
        allure.attach(
            page.screenshot(full_page=True), name="storefront at failure",
            attachment_type=allure.attachment_type.PNG,
        )
        allure.attach(
            page.content(), name="storefront page source at failure",
            attachment_type=allure.attachment_type.HTML,
        )
    except Exception as capture_error:
        allure.attach(
            repr(capture_error)[:600], name="storefront not captured",
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
) -> None:
    """Reserve, rent, check the emails and the HB tenant, then move out -
    also when a step fails, once the rental form has named the space."""
    timeout = app_config.getint("browser", "timeout")
    guest_name = f"{guest['first_name']} {guest['last_name']}"
    setup = None
    space_number = None
    reserved = False
    rented = False
    tenant_url = None
    move_in_date = date.today()
    failure = None
    try:
        setup_class = MPTwoStepReservationSetup if two_step else MPLegacyReservationSetup
        setup = setup_class(storefront_page, environment_config, app_config, property_url=property_url)
        with allure.step("Reserve a unit" + (" as a business" if case.rab else "")):
            setup.reserve_unit(guest, renting_as_business=case.rab)
        reserved = True

        with allure.step(f"Rent it: {case.title}"):
            if two_step:
                bill = setup.rent_reserved_unit(
                    guest, {**rental_data, "enroll_autopay": case.autopay}, payment_method=case.payment
                )
                space_number, amount_paid = bill["space_number"], bill["pay_now"]
                security_deposit = next(
                    (amount for label, amount in bill["charges"].items() if "deposit" in label.lower()),
                    None,
                )
            else:
                rental = setup.convert_reservation_to_rental(
                    guest, rental_data, payment_method=case.payment, autopay=case.autopay
                )
                space_number, amount_paid = rental["space_number"], rental["total"]
                security_deposit = rental["security_deposit"]
                # The move-in date the rental form showed (today on desktop,
                # the reservation's date on mobile), else today.
                move_in_date = rental.get("move_in_date") or move_in_date
        rented = True

        with allure.step("Rental confirmation" + (" and autopay" if case.autopay else "") + " emails"):
            setup.assert_rental_emails(
                guest, space_number, move_in_date, amount_paid, security_deposit, autopay=case.autopay
            )

        with allure.step("HB: a current tenant, paid" + (", on autopay" if case.autopay else ", no autopay")):
            _log_in(hb_login_page)
            tenants = HBTenantSpacesPage(hb_login_page.page, timeout)
            tenants.open_tenants(property_config.hb_property_name)
            tenants.assert_web_rental_tenant(
                guest_name,
                space_number,
                move_in_date,
                amount_paid,
                card_last4=environment_config.card_number[-4:] if case.autopay and case.payment == "card" else None,
                ach_last4=(
                    environment_config.ach_account_number[-4:] if case.autopay and case.payment == "ach" else None
                ),
                no_autopay=not case.autopay,
            )
            tenant_url = hb_login_page.page.url
    except BaseException as error:
        failure = error
        if isinstance(error, Exception):
            _attach_storefront(storefront_page)
        raise
    finally:
        space_number = space_number or (setup.space_number if setup else None)
        if reserved:
            try:
                _clean_up(
                    hb_login_page, timeout, property_config.hb_property_name, guest, space_number,
                    rented, tenant_url,
                )
            except Exception as cleanup_error:
                allure.attach(
                    repr(cleanup_error)[:1000],
                    name=f"NOT cleaned up: {guest['email']}, space {space_number}",
                    attachment_type=allure.attachment_type.TEXT,
                )
                if failure is None:
                    raise
