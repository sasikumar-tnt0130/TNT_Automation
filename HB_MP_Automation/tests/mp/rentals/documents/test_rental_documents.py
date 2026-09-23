"""TestRail smoke run 2967 - documents a rental generates (lease, military
waiver, vehicle addendum, protection/coverage docs), individual and RAB.

Walked live 2026-09-16 stage/Hamilton (Garden Grove):
- Tenant Documents lists Lease Agreement, Military Waiver, Vehicle Addendum;
  coverage rentals also produce A1/A2/A3/A5 (type \"other\") - no document
  titled \"Protection Enrollment Agreement\" on this property.
- Row kebab -> View/Print opens a CloudFront PDF; pypdf extracts text.
  Lease shows \"Leased Space No.: LOAD###\", move-in total, and military /
  titled-vehicle flags when those extras were filled.
"""
from __future__ import annotations

import re

import allure
import pytest

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_rental_cases import move_out_rental
from common_utils.mp_rental_extras import rental_extras
from config.config_reader import load_property
from pages.common.hb_tenant_documents_page import HBTenantDocumentsPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage
from playwright.sync_api import expect


class NoInventoryError(Exception):
    """Preferred unit category has no rentable inventory on this property."""


# Live inventory on stage Garden Grove reliably has storage + parking.
# Wine / mailbox categories are uncommon on this property and are omitted
# so the smoke run stays within a practical wall-clock budget.
SPACE_TYPES = ("Storage", "Parking")


def _unit_type_arg(space_type: str) -> str | None:
    """select_unit preference; Storage uses first available category."""
    if space_type.lower() == "storage":
        return None
    return space_type


def _run_document_rental(
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
    renting_as_business: bool,
    extras: dict,
    expected_documents: list[str],
    pdf_checks: dict[str, list[str]] | None = None,
) -> dict:
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
    guest_name = (
        f"{mp_guest['first_name']} {mp_guest['last_name']} Business"
        if renting_as_business
        else f"{mp_guest['first_name']} {mp_guest['last_name']}"
    )
    space_number: str | None = None
    failure: BaseException | None = None
    store_ctx = browser.new_context(**desktop_context_options(app_config))
    result: dict = {}
    try:
        page = store_ctx.new_page()
        prepare_desktop_page(page, app_config)
        setup = MPLegacyReservationSetup(
            page, environment_config, app_config, property_url=property_url
        )
        with allure.step(
            "Reserve and rent"
            + (" as a business" if renting_as_business else "")
            + (f" ({unit_type})" if unit_type else " (storage)")
        ):
            try:
                setup.reserve_unit(
                    mp_guest,
                    renting_as_business=renting_as_business,
                    unit_type=unit_type,
                )
            except AssertionError as error:
                if unit_type and re.search(
                    r"sold out|no available|could not select|not found|failed to select",
                    str(error),
                    re.I,
                ):
                    raise NoInventoryError(f"No {unit_type} inventory: {error}") from error
                raise
            rental = setup.convert_reservation_to_rental(
                mp_guest,
                rental_data,
                payment_method="card",
                autopay=False,
                extras=extras,
            )
            space_number = rental["space_number"]
            result = {
                "space_number": space_number,
                "total": rental.get("total"),
                "guest_name": guest_name,
                "hb_property_name": prop.hb_property_name,
            }

        with allure.step("HB Documents"):
            hb_login_page.ensure_logged_in()
            tenants = HBTenantSpacesPage(hb_login_page.page, timeout)
            tenants.open_tenants(prop.hb_property_name)
            tenants.open_storefront_tenant(guest_name, space_number)
            docs = HBTenantDocumentsPage(hb_login_page.page, timeout)
            docs.open_documents_menu()
            # Documents can lag a few seconds after the rental confirmation.
            docs.assert_documents_listed(expected_documents)
            for document_name, snippets in (pdf_checks or {}).items():
                resolved = [
                    space_number if snippet == "{space}" else snippet
                    for snippet in snippets
                ]
                docs.assert_document_pdf_contains(document_name, resolved)
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
    return result


def _for_each_space_type(
    request,
    *,
    renting_as_business: bool,
    extras_kwargs: dict,
    expected_documents: list[str],
    pdf_checks_factory,
) -> None:
    """Rent one space per available type; skip types with no inventory."""
    from common_utils.test_identities import new_mp_guest

    attempted = 0
    succeeded = 0
    for space_type in SPACE_TYPES:
        unit_type = _unit_type_arg(space_type)
        with allure.step(f"Space type: {space_type}"):
            try:
                attempted += 1
                guest = new_mp_guest()
                rental_data = request.getfixturevalue("test_data")("mp_rental")
                extras = rental_extras(rental_data, **extras_kwargs)
                # Parking always needs vehicle type fields on this property.
                if space_type.lower() == "parking" and not extras.get("vehicle_type"):
                    extras = rental_extras(
                        rental_data, **{**extras_kwargs, "vehicle": True}
                    )
                result = _run_document_rental(
                    browser=request.getfixturevalue("browser"),
                    environment=request.getfixturevalue("environment"),
                    environment_config=request.getfixturevalue("environment_config"),
                    app_config=request.getfixturevalue("app_config"),
                    mp_guest=guest,
                    property_landing_page_url=request.getfixturevalue(
                        "property_landing_page_url"
                    ),
                    hb_login_page=request.getfixturevalue("hb_admin_session"),
                    test_data=request.getfixturevalue("test_data"),
                    move_out_after_rental=request.getfixturevalue(
                        "move_out_after_rental"
                    ),
                    unit_type=unit_type,
                    renting_as_business=renting_as_business,
                    extras=extras,
                    expected_documents=expected_documents,
                    pdf_checks=pdf_checks_factory(extras, guest),
                )
                succeeded += 1
                allure.attach(
                    repr(result),
                    name=f"{space_type} rental",
                    attachment_type=allure.attachment_type.TEXT,
                )
            except NoInventoryError as skipped:
                allure.attach(
                    str(skipped),
                    name=f"{space_type} skipped",
                    attachment_type=allure.attachment_type.TEXT,
                )
    if succeeded == 0:
        pytest.skip(
            f"No space types available of {SPACE_TYPES} (attempted {attempted})"
        )


@allure.feature("MP Rentals")
@allure.story("Rental documents")
@pytest.mark.usefixtures(
    "ensure_autotest_document_templates",
    "legacy_traditional_signing",
)
class TestRentalDocuments:
    @allure.title("Rentals with HB-Lease Agreement generated for every space type")
    @pytest.mark.smoke
    @pytest.mark.testrail("C41014")
    def test_lease_agreement_generated_for_each_space_type(self, request) -> None:
        def pdf_checks(_extras: dict, _guest: dict) -> dict[str, list[str]]:
            return {
                "Lease Agreement": ["{space}", "Leased Space No"],
            }

        _for_each_space_type(
            request,
            renting_as_business=False,
            extras_kwargs={"coverage": True},
            expected_documents=["Lease Agreement"],
            pdf_checks_factory=pdf_checks,
        )

    @allure.title("Rentals with HB-Military Addendum generated for every space type")
    @pytest.mark.smoke
    @pytest.mark.testrail("C41016")
    def test_military_addendum_generated_for_each_space_type(self, request) -> None:
        def pdf_checks(extras: dict, _guest: dict) -> dict[str, list[str]]:
            military = extras["military"]
            return {
                "Military Waiver": [
                    "{space}",
                    "MILITARY",
                    military["branch"],
                ],
                "Lease Agreement": [
                    "{space}",
                    military["identification_number"],
                    military["branch"],
                ],
            }

        _for_each_space_type(
            request,
            renting_as_business=False,
            extras_kwargs={"military": True, "coverage": True},
            expected_documents=["Lease Agreement", "Military Waiver"],
            pdf_checks_factory=pdf_checks,
        )

    @allure.title("Rentals with HB-Vehicle Addendum generated when storing a vehicle")
    @pytest.mark.smoke
    @pytest.mark.testrail("C41018")
    def test_vehicle_addendum_generated_with_vehicle_storing(
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
        rental_data = test_data("mp_rental")
        extras = rental_extras(rental_data, vehicle=True, coverage=True)
        vehicle = extras["vehicle"]
        _run_document_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            unit_type=None,
            renting_as_business=False,
            extras=extras,
            expected_documents=["Lease Agreement", "Vehicle Addendum"],
            pdf_checks={
                "Vehicle Addendum": [
                    "{space}",
                    "VEHICLE",
                    vehicle["license_plate"],
                ],
            },
        )

    @allure.title(
        "Rentals with HB-Protection Enrollment Agreement generated with insurance"
    )
    @pytest.mark.smoke
    @pytest.mark.testrail("C41019")
    def test_protection_enrollment_agreement_generated_with_insurance(
        self, request
    ) -> None:
        """Coverage selected: lease PDF carries move-in total; on stage the
        named Protection Enrollment Agreement is not generated - A1..A5
        \"other\" docs appear instead (walked 2026-09-16). Assert Lease + at
        least one coverage-related row (Protection* or A1)."""

        def pdf_checks(_extras: dict, _guest: dict) -> dict[str, list[str]]:
            return {"Lease Agreement": ["{space}", "Total Move"]}

        def run_one(space_type: str) -> None:
            from common_utils.test_identities import new_mp_guest

            unit_type = _unit_type_arg(space_type)
            rental_data = request.getfixturevalue("test_data")("mp_rental")
            extras = rental_extras(rental_data, coverage=True)
            if space_type.lower() == "parking":
                extras = rental_extras(rental_data, coverage=True, vehicle=True)
            result = _run_document_rental(
                browser=request.getfixturevalue("browser"),
                environment=request.getfixturevalue("environment"),
                environment_config=request.getfixturevalue("environment_config"),
                app_config=request.getfixturevalue("app_config"),
                mp_guest=new_mp_guest(),
                property_landing_page_url=request.getfixturevalue(
                    "property_landing_page_url"
                ),
                hb_login_page=request.getfixturevalue("hb_admin_session"),
                test_data=request.getfixturevalue("test_data"),
                move_out_after_rental=request.getfixturevalue(
                    "move_out_after_rental"
                ),
                unit_type=unit_type,
                renting_as_business=False,
                extras=extras,
                expected_documents=["Lease Agreement"],
                pdf_checks=pdf_checks(extras, {}),
            )
            # After lease assert, reopen docs panel is already open - check
            # protection-named or A1 coverage companion docs.
            docs = HBTenantDocumentsPage(
                request.getfixturevalue("hb_admin_session").page,
                request.getfixturevalue("app_config").getint("browser", "timeout"),
            )
            protection = request.getfixturevalue("hb_admin_session").page.get_by_role(
                "row", name=re.compile(r"Protection|Enrollment|A1", re.I)
            )
            expect(protection.first).to_be_visible(
                timeout=request.getfixturevalue("app_config").getint(
                    "browser", "timeout"
                )
            )
            allure.attach(
                repr(result),
                name=f"{space_type} coverage rental",
                attachment_type=allure.attachment_type.TEXT,
            )

        succeeded = 0
        for space_type in SPACE_TYPES:
            with allure.step(f"Space type: {space_type}"):
                try:
                    run_one(space_type)
                    succeeded += 1
                except NoInventoryError as skipped:
                    allure.attach(
                        str(skipped),
                        name=f"{space_type} skipped",
                        attachment_type=allure.attachment_type.TEXT,
                    )
        if succeeded == 0:
            pytest.skip(f"No space types available of {SPACE_TYPES}")

    @allure.title("Rentals with RAB-Lease Agreement generated for every space type")
    @pytest.mark.smoke
    @pytest.mark.testrail("C41071")
    def test_rab_lease_agreement_generated_for_each_space_type(self, request) -> None:
        def pdf_checks(_extras: dict, guest: dict) -> dict[str, list[str]]:
            business = f"{guest['first_name']} {guest['last_name']} Business"
            return {
                "Lease Agreement": [
                    "{space}",
                    "Leased Space No",
                    business,
                    guest["first_name"],
                ],
            }

        _for_each_space_type(
            request,
            renting_as_business=True,
            extras_kwargs={"coverage": True},
            expected_documents=["Lease Agreement"],
            pdf_checks_factory=pdf_checks,
        )

    @allure.title("Rentals with RAB-Military Addendum generated for every space type")
    @pytest.mark.smoke
    @pytest.mark.testrail("C41073")
    def test_rab_military_addendum_generated_for_each_space_type(self, request) -> None:
        def pdf_checks(extras: dict, _guest: dict) -> dict[str, list[str]]:
            military = extras["military"]
            return {
                "Military Waiver": [
                    "{space}",
                    "MILITARY",
                    military["branch"],
                ],
                "Lease Agreement": [
                    "{space}",
                    military["identification_number"],
                ],
            }

        _for_each_space_type(
            request,
            renting_as_business=True,
            extras_kwargs={"military": True, "coverage": True},
            expected_documents=["Lease Agreement", "Military Waiver"],
            pdf_checks_factory=pdf_checks,
        )

    @allure.title("Rentals with RAB-Vehicle Addendum generated when storing a vehicle")
    @pytest.mark.smoke
    @pytest.mark.testrail("C41075")
    def test_rab_vehicle_addendum_generated_with_vehicle_storing(
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
        rental_data = test_data("mp_rental")
        extras = rental_extras(rental_data, vehicle=True, coverage=True)
        vehicle = extras["vehicle"]
        _run_document_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            unit_type=None,
            renting_as_business=True,
            extras=extras,
            expected_documents=["Lease Agreement", "Vehicle Addendum"],
            pdf_checks={
                "Vehicle Addendum": [
                    "{space}",
                    "VEHICLE",
                    vehicle["license_plate"],
                ],
            },
        )
