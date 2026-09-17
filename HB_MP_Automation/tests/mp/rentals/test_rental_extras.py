"""TestRail smoke run 2967 - Legacy desktop rentals that tick every optional
extra at once (coverage, vehicle storing, autopay, active military, lien
holder) and pay by ACH, for a storage space and for a parking space, then
check the documents each extra generates.

Walked live 2026-09-16 stage/Hamilton (Garden Grove): Additional Information
Yes reveals idmilitary* / idlien_holder* / Vehicle Type radios; Sign
Agreements rejects until those required fields are filled.
"""
from __future__ import annotations

import uuid

import allure
import pytest

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_rental_cases import move_out_rental
from config.config_reader import load_property
from pages.common.hb_tenant_documents_page import HBTenantDocumentsPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


def _letter_suffix(raw: str) -> str:
    return "".join("abcdefghij"[int(ch)] if ch.isdigit() else ch for ch in raw)


def _extras_for(guest: dict, rental_data: dict, *, include_vehicle: bool) -> dict:
    """Fictional military / lien (/ optional vehicle) payload for C40628/29."""
    suffix = _letter_suffix(uuid.uuid4().hex[:6])
    extras: dict = {
        "coverage": True,
        "military": {
            "identification_number": "DOD-AUTO-001",
            "dob": "01/15/1990",
            # Reserved advertising / fictional SSN-shaped value for forms.
            "ssn": "900-11-2233",
            "ets": "12/31/2028",
            "branch": "Army",
            "unit_name": "Automation Unit",
            "unit_phone": "(714) 555-0188",
            "officer_first_name": "Officer",
            "officer_last_name": f"Lead{suffix}",
        },
        "lien_holder": {
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
        },
    }
    if include_vehicle:
        extras["vehicle_type"] = "Car"
    return extras


def _run_extras_rental(
    *,
    browser,
    environment,
    environment_config,
    app_config,
    mp_guest,
    property_landing_page_url,
    hb_login_page,
    test_data,
    move_out_after_rental: bool,
    unit_type: str | None,
    include_vehicle: bool,
    expected_documents: list[str],
) -> None:
    property_key = app_config.get(environment, "legacy_property", fallback="").strip()
    if not property_key:
        pytest.skip(f"No legacy_property configured for {environment}")
    prop = load_property(app_config, environment, property_key)
    if not (prop.mp_state and prop.mp_city and prop.hb_property_name):
        pytest.skip("No storefront / HB property configured for this environment")

    timeout = app_config.getint("browser", "timeout")
    property_url = property_landing_page_url(
        environment_config.mp_base_url, prop.mp_state, prop.mp_city
    )
    rental_data = test_data("mp_rental")
    extras = _extras_for(mp_guest, rental_data, include_vehicle=include_vehicle)
    guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
    space_number: str | None = None
    failure: BaseException | None = None
    store_ctx = browser.new_context(**desktop_context_options(app_config))
    try:
        page = store_ctx.new_page()
        prepare_desktop_page(page, app_config)
        setup = MPLegacyReservationSetup(
            page, environment_config, app_config, property_url=property_url
        )
        with allure.step(
            f"Reserve {'Parking' if unit_type else 'storage'} unit and rent with extras (ACH+autopay)"
        ):
            setup.reserve_unit(
                mp_guest, renting_as_business=False, unit_type=unit_type
            )
            rental = setup.convert_reservation_to_rental(
                mp_guest,
                rental_data,
                payment_method="ach",
                autopay=True,
                extras=extras,
            )
            space_number = rental["space_number"]

        with allure.step("HB: generated documents for the extras"):
            if hb_login_page.open_login_page():
                hb_login_page.submit_login_credentials()
            hb_login_page.assert_login_successful()
            tenants = HBTenantSpacesPage(hb_login_page.page, timeout)
            tenants.open_tenants(prop.hb_property_name)
            tenants.open_storefront_tenant(guest_name, space_number)
            docs = HBTenantDocumentsPage(hb_login_page.page, timeout)
            docs.open_documents_menu()
            docs.assert_documents_listed(expected_documents)
    except BaseException as error:
        failure = error
        raise
    finally:
        close_context_with_videos(store_ctx, app_config, name="storefront-video")
        if space_number and not move_out_after_rental:
            allure.attach(
                f"{mp_guest['email']}, space {space_number}, property {prop.hb_property_name}",
                name="move-out skipped (--no-move-out)",
                attachment_type=allure.attachment_type.TEXT,
            )
        elif space_number:
            try:
                move_out_rental(
                    hb_login_page,
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


@allure.feature("MP Rentals")
@allure.story("Legacy Flow - rental extras")
@pytest.mark.usefixtures("legacy_traditional_signing")
class TestRentalExtras:
    @allure.title(
        "Legacy Flow-Storage rental with coverage, vehicle, autopay, military, lien holder, ACH"
    )
    @pytest.mark.smoke
    @pytest.mark.testrail("C40628")
    def test_storage_rental_with_all_extras_by_ach(
        self,
        browser,
        environment,
        environment_config,
        app_config,
        mp_guest,
        property_landing_page_url,
        hb_login_page,
        test_data,
        move_out_after_rental,
    ) -> None:
        """Desktop Legacy flow, storage space: choose coverage, tick vehicle
        storing, enrol autopay, tick active military, add a lien holder, pay by
        ACH. Each of the lease, protection, vehicle and military documents is
        generated."""
        _run_extras_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_login_page,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            unit_type=None,
            include_vehicle=True,
            expected_documents=[
                "Lease Agreement",
                "Military Waiver",
                "Vehicle Addendum",
                "Autopay Enrollment Document",
            ],
        )

    @allure.title(
        "Legacy Flow-Parking rental with coverage, autopay, military, lien holder, ACH"
    )
    @pytest.mark.smoke
    @pytest.mark.testrail("C40629")
    def test_parking_rental_with_all_extras_by_ach(
        self,
        browser,
        environment,
        environment_config,
        app_config,
        mp_guest,
        property_landing_page_url,
        hb_login_page,
        test_data,
        move_out_after_rental,
    ) -> None:
        """C40628 for a parking space (no 'storing a vehicle' toggle - Vehicle
        Type* is required on the parking rental form instead)."""
        _run_extras_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_login_page,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            unit_type="Parking",
            include_vehicle=True,
            expected_documents=[
                "Lease Agreement",
                "Military Waiver",
                "Vehicle Addendum",
                "Autopay Enrollment Document",
            ],
        )
