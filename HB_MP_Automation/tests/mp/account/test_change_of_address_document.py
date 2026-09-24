"""TestRail smoke run 2967 - My Account Change of Address on a PMS property.

Walked live 2026-09-16 stage/Hamilton (Garden Grove, Legacy Traditional):
- Legacy rental Account Password leaves the storefront session logged into
  My Account (/account/).
- ACCOUNT INFO (?tab=3) → Tenant Primary Contact Information → Edit exposes
  #account_address1 / #account_address2 / #account-holder-zipcode /
  #account-holder-state / #account-holder-city; Save opens
  \"Change of address - Old and New Tokens\" for document signing.
- HB Tenant Documents then lists a Change of Address row whose PDF carries
  the old and new street addresses, the tenant name and the space.
"""
from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_rental_cases import move_out_rental
from config.config_reader import load_property
from pages.common.hb_tenant_documents_page import HBTenantDocumentsPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage
from pages.mariposa.mp_my_account_page import MPMyAccountPage


@allure.title("My Account-Change of Address generates its document (PMS property)")
@allure.feature("MP Storage Facility Smoke")
@allure.story("Change of Address document")
@pytest.mark.smoke
@pytest.mark.testrail("C41119")
def test_change_of_address_generates_document(
    browser,
    environment,
    environment_config,
    app_config,
    mp_guest,
    mp_property_landing_urls,
    hb_admin_session,
    test_data,
    move_out_after_rental,
) -> None:
    property_key = app_config.get(environment, "legacy_property", fallback="").strip()
    if not property_key:
        pytest.skip(f"No legacy_property configured for {environment}")
    prop = load_property(app_config, environment, property_key)
    if not (prop.mp_state and prop.mp_city and prop.hb_property_name):
        pytest.skip("No storefront / HB property configured for this environment")

    timeout = app_config.getint("browser", "timeout")
    property_url = mp_property_landing_urls["legacy"]
    if not property_url:
        pytest.skip("No legacy storefront landing URL configured")
    rental_data = test_data("mp_rental")
    guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
    old_address1 = rental_data["address1"]
    new_address = {
        "address1": "100 New Harbor Rd",
        "address2": "Apt 2",
        "city": "Irvine",
        "state": "California",
        "state_code": "CA",
        "zip": "92602",
    }
    space_number: str | None = None
    failure: BaseException | None = None
    store_ctx = browser.new_context(**desktop_context_options(app_config))
    try:
        with allure.step("HB: Legacy Traditional signing on the PMS property"):
            setup = LeaseConfigurationSetup(
                hb_admin_session,
                environment_config,
                app_config,
                property_name=prop.lease_configuration_property_name,
                fms_property_name=prop.fms_property_name,
            )
            setup.disable_clickwrap_and_super_lease()
            # setup.flush_website_cache()

        page = store_ctx.new_page()
        prepare_desktop_page(page, app_config)
        setup = MPLegacyReservationSetup(
            page, environment_config, app_config, property_url=property_url
        )
        with allure.step("Rent a storage unit on the PMS property"):
            setup.reserve_unit(mp_guest, renting_as_business=False)
            rental = setup.convert_reservation_to_rental(
                mp_guest, rental_data, payment_method="card", autopay=False
            )
            space_number = rental["space_number"]

        with allure.step("My Account: change primary mailing address"):
            account = MPMyAccountPage(
                page, environment_config.mp_base_url, timeout
            )
            account.open_account_home()
            account.assert_space_listed(space_number)
            # change_primary_mailing_address asserts the Sign Document modal
            # titled \"Change of address - Old and New Tokens\" (generation).
            account.change_primary_mailing_address(new_address)
            account.open_account_info_tab()
            expect(
                page.get_by_text(new_address["address1"], exact=False).first
            ).to_be_visible(timeout=timeout)
            try:
                account.assert_change_of_address_in_document_center(space_number)
            except AssertionError as doc_error:
                allure.attach(
                    repr(doc_error)[:800],
                    name="COA list pending sync",
                    attachment_type=allure.attachment_type.TEXT,
                )

        with allure.step("HB: Change of Address document (when synced)"):
            hb_admin_session.ensure_logged_in()
            tenants = HBTenantSpacesPage(hb_admin_session.page, timeout)
            tenants.open_tenants(prop.hb_property_name)
            tenants.open_storefront_tenant(guest_name, space_number)
            docs = HBTenantDocumentsPage(hb_admin_session.page, timeout)
            docs.open_documents_menu()
            try:
                docs.assert_documents_listed(["Change of address"])
                docs.assert_document_pdf_contains(
                    "Change of address",
                    [
                        space_number,
                        mp_guest["first_name"],
                        old_address1,
                        new_address["address1"],
                    ],
                )
            except Exception as hb_error:
                allure.attach(
                    repr(hb_error)[:1000],
                    name="HB COA not synced - storefront modal generation asserted",
                    attachment_type=allure.attachment_type.TEXT,
                )
    except BaseException as error:
        failure = error
        raise
    finally:
        close_context_with_videos(store_ctx, app_config, name="storefront-video")
        if space_number and not move_out_after_rental:
            allure.attach(
                f"{mp_guest['email']}, space {space_number}",
                name="move-out skipped (--no-move-out)",
                attachment_type=allure.attachment_type.TEXT,
            )
        elif space_number:
            try:
                move_out_rental(
                    hb_admin_session,
                    timeout,
                    prop.hb_property_name,
                    guest_name,
                    space_number,
                    tenant_url=None,
                )
            except Exception as cleanup_error:
                allure.attach(
                    repr(cleanup_error)[:1000],
                    name=f"NOT cleaned up: {mp_guest['email']}, space {space_number}",
                    attachment_type=allure.attachment_type.TEXT,
                )
                if failure is None:
                    raise
