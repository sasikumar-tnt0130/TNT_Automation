from playwright.sync_api import Page

from config.config_reader import EnvironmentConfig
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


def create_lease_through_quick_action(
    page: Page,
    timeout: float,
    environment_config: EnvironmentConfig,
    lease_data: dict,
    guest: dict,
    payment_method: str | None = None,
) -> HBQuickLaunchPage:
    """Runs the full "From Quick action Create a lease" flow (property
    selection through signed/finalized lease) for a fresh contact.
    Extracted so tests that need an already-existing tenant as a
    precondition (e.g. document upload) don't have to duplicate every
    step of setting one up. payment_method: see
    complete_lease_from_move_in. The returned page's space_number is the
    space moved into (e.g. "0031")."""
    quick_launch = HBQuickLaunchPage(page, timeout)
    quick_launch.open_quick_launch_for_property(lease_data["property_name"])
    quick_launch.start_new_contact(guest["email"])
    quick_launch.fill_lead_details(
        guest["first_name"],
        guest["last_name"],
        guest["email"],
        guest["phone_number"],
        lease_data["lead_initiated"],
        lease_data["lead_source"],
    )
    space_number = quick_launch.move_in_first_available_space()
    complete_lease_from_move_in(
        quick_launch, environment_config, lease_data, guest, payment_method
    )
    # The grid cell also holds the size on a second line ("0040\n8' x 8'",
    # 2026-09-14) - the space is its first word.
    quick_launch.space_number = space_number.lstrip("#").split()[0]
    return quick_launch


def complete_lease_from_move_in(
    quick_launch: HBQuickLaunchPage,
    environment_config: EnvironmentConfig,
    lease_data: dict,
    guest: dict,
    payment_method: str | None = None,
) -> None:
    """Everything after "Move In" lands on the Lease step, through the
    signed/finalized lease. Shared by the Quick Action flow above and
    "From Leads create a Rental", which reach that same Lease step from
    different entry points (see HBLeadManagementPage.
    open_lead_and_start_move_in).

    payment_method: "card" or "cash". None (the default) uses the test
    data's own "payment_method" for this environment, falling back to
    card - see quick_launch_lease.json, where uat_storoutlet says cash
    (its card form is missing its payment gateway API key)."""
    payment_method = payment_method or lease_data.get("payment_method", "card")
    address = lease_data["address"]
    driver_license = lease_data["driver_license"]
    quick_launch.fill_lease_address_and_identity(
        address["street"],
        address["zip_code"],
        address["state"],
        address["city"],
        lease_data["date_of_birth"],
        driver_license["number"],
        driver_license["expiry"],
        driver_license["state"],
    )
    quick_launch.decline_coverage_with_expiration()
    quick_launch.confirm_notice_delivery_method()
    quick_launch.confirm_vehicle_information(has_vehicle=False)
    quick_launch.proceed_to_payments()

    if payment_method == "cash":
        quick_launch.pay_by_cash()
    else:
        card_expiry_month, card_expiry_year = environment_config.card_expiry.split("/")
        quick_launch.pay_by_credit_card(
            environment_config.card_number,
            environment_config.card_cvc,
            card_expiry_month,
            card_expiry_year,
            environment_config.card_zip_code,
        )
    initials = f"{guest['first_name'][0]}{guest['last_name'][0]}".upper()
    quick_launch.sign_documents_on_this_device(initials)
    quick_launch.complete_move_in_checklist_and_finalize()
    quick_launch.assert_lease_completed()
    quick_launch.finish_and_close()


def add_space_and_lease_for_tenant(
    page: Page,
    timeout: float,
    lease_data: dict,
    guest: dict,
    payment_method: str | None = None,
) -> HBQuickLaunchPage:
    """Old Robot suite's "Open Tenant And Add Multiple Space And Lease": a
    second space and lease for a tenant who already has one, leaving its
    move-in charges unpaid (Skip Payment) so a later payment can cover
    every space at once - or paid in cash with payment_method="cash" (the
    session test tenants, which would otherwise keep a balance once moved
    out). Confirmed live (2026-09-11, Bellflower): the Lease step comes
    pre-filled from the tenant's first lease (address, date of birth,
    driver's license), so those aren't re-entered here. The returned
    page's space_number is the added space."""
    tenant_spaces = HBTenantSpacesPage(page, timeout)
    tenant_spaces.open_tenants(lease_data["property_name"])
    tenant_spaces.open_tenant_details(guest["first_name"], guest["last_name"])
    tenant_spaces.start_add_space()

    quick_launch = HBQuickLaunchPage(page, timeout)
    quick_launch.select_lead_source(
        lease_data["lead_initiated"], lease_data["lead_source"]
    )
    space_number = quick_launch.move_in_first_available_space()
    quick_launch.decline_coverage_with_expiration()
    quick_launch.confirm_notice_delivery_method()
    quick_launch.confirm_vehicle_information(has_vehicle=False)
    quick_launch.proceed_to_payments()
    if payment_method == "cash":
        quick_launch.pay_by_cash()
    else:
        quick_launch.skip_payment()

    initials = f"{guest['first_name'][0]}{guest['last_name'][0]}".upper()
    quick_launch.sign_documents_on_this_device(initials)
    quick_launch.complete_move_in_checklist_and_finalize()
    quick_launch.assert_lease_completed()
    quick_launch.finish_and_close()
    # The grid cell also holds the size on a second line ("0040\n8' x 8'",
    # 2026-09-14) - the space is its first word.
    quick_launch.space_number = space_number.lstrip("#").split()[0]
    return quick_launch
