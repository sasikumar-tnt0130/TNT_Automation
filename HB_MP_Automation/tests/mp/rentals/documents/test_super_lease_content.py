"""TestRail smoke run 2967 - what the generated Superlease shows for the
optional blocks on the rental form (alternate contact, emergency contact,
authorized access, military, lien holder), for insurance, and for a quarterly
billing cycle.

Walked live 2026-09-16 stage/Hamilton (Garden Grove) under Legacy Super Lease
signing (Clickwrap on, Super Lease on, Pay Now):
- Tenant Documents lists File Name \"Superlease\" (type super-lease), not
  \"Lease Agreement\".
- Alternate contact only lands in the PDF after ticking secondary contact
  (id_secondary_contactyes); otherwise the Alternate Person block is N/A.
- Emergency / authorized-access Yes radios reveal idemergency* /
  idaccess_authorized* fields; those names appear under EMERGENCY CONTACT /
  AUTHORIZED ACCESS CONTACT.
"""
from __future__ import annotations

import re
from datetime import date

import allure
import pytest

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_lease_costs import assert_costs_match_three_ways
from common_utils.mp_rental_cases import move_out_rental
from common_utils.mp_rental_extras import rental_extras
from config.config_reader import load_property
from pages.common.hb_tenant_documents_page import HBTenantDocumentsPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


SUPERLEASE_DOC = "Superlease"


def _run_super_lease_rental(
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
    extras: dict,
    include_alternate: bool,
    pdf_must_contain: list[str],
    pdf_must_not_contain: list[str] | None = None,
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
    guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
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
        with allure.step("Reserve and rent under Super Lease"):
            setup.reserve_unit(mp_guest, renting_as_business=False, unit_type=None)
            rental = setup.convert_reservation_to_rental(
                mp_guest,
                rental_data,
                payment_method="card",
                autopay=False,
                extras=extras,
                include_alternate=include_alternate,
            )
            space_number = rental["space_number"]
            charges = rental.get("charges") or {}
            amount_paid = rental["total"]
            move_in_date = rental.get("move_in_date") or date.today()
            result = {
                "space_number": space_number,
                "ending": rental.get("ending"),
                "charges": charges,
                "total": amount_paid,
                "alternate": rental.get("alternate"),
                "extras": {
                    key: extras[key]
                    for key in (
                        "emergency",
                        "authorized_access",
                        "military",
                        "lien_holder",
                        "coverage",
                    )
                    if key in extras
                },
                "hb_property_name": prop.hb_property_name,
                "guest_name": guest_name,
            }
            assert rental.get("ending") == "pay_now", (
                f"Expected Super Lease Pay Now ending, got {rental.get('ending')!r}"
            )

        with allure.step("Rental confirmation email + lease agreement costs"):
            email_body = setup.assert_rental_emails(
                mp_guest,
                space_number,
                move_in_date,
                amount_paid,
                rental.get("security_deposit"),
                autopay=False,
                charges=rental.get("confirmation_charges") or charges or None,
            )

        with allure.step("HB Superlease PDF — three-way cost compare"):
            hb_login_page.ensure_logged_in()
            tenants = HBTenantSpacesPage(hb_login_page.page, timeout)
            tenants.open_tenants(prop.hb_property_name)
            tenants.open_storefront_tenant(guest_name, space_number)
            docs = HBTenantDocumentsPage(hb_login_page.page, timeout)
            docs.open_documents_menu()
            docs.assert_documents_listed([SUPERLEASE_DOC])
            resolved = [
                space_number if snippet == "{space}" else snippet
                for snippet in pdf_must_contain
            ]
            text = docs.assert_document_pdf_contains(
                SUPERLEASE_DOC, resolved, space_number=space_number
            )
            assert_costs_match_three_ways(
                mp_charges=rental.get("confirmation_charges") or {},
                mp_total=rental.get("confirmation_total"),
                email_text=email_body,
                lease_text=text,
                fallback_charges=charges,
                space_number=space_number,
            )
            missing_absent = [
                snippet
                for snippet in (pdf_must_not_contain or [])
                if snippet and snippet.lower() in text.lower()
            ]
            if missing_absent:
                raise AssertionError(
                    f"{SUPERLEASE_DOC!r} unexpectedly contains {missing_absent!r}"
                )
            result["pdf_text"] = text
            result["pdf_sample"] = text[:1500]
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


@allure.feature("MP Rentals")
@allure.story("Super lease content")
@pytest.mark.usefixtures("legacy_superlease_signing")
class TestSuperLeaseContent:
    @allure.title("Super lease-Alternate contact details are shown")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64685")
    def test_super_lease_shows_alternate_contact(
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
        extras = rental_extras(test_data("mp_rental"), coverage=False)
        result = _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=True,
            pdf_must_contain=["{space}"],
        )
        alternate = result["alternate"]
        assert alternate, "Expected an alternate contact on the rental"
        text = result["pdf_text"].lower()
        for snippet in (
            alternate["last_name"],
            alternate["email"],
            alternate["first_name"],
        ):
            assert snippet.lower() in text, (
                f"Superlease missing alternate field {snippet!r}"
            )

    @allure.title("Super lease-Alternate contact left blank when not given")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64686")
    def test_super_lease_alternate_contact_blank_when_not_given(
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
        extras = rental_extras(test_data("mp_rental"), coverage=False)
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=["{space}", "Alternate", "N/A"],
        )

    @allure.title("Super lease-Emergency contact details are shown")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64687")
    def test_super_lease_shows_emergency_contact(
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
        extras = rental_extras(
            test_data("mp_rental"), emergency=True, coverage=False
        )
        emergency = extras["emergency"]
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=[
                "{space}",
                "EMERGENCY CONTACT",
                emergency["last_name"],
                emergency["email"],
            ],
        )

    @allure.title("Super lease-Emergency contact left blank when not given")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64688")
    def test_super_lease_emergency_contact_blank_when_not_given(
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
        extras = rental_extras(test_data("mp_rental"), coverage=False)
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=["{space}"],
            pdf_must_not_contain=["Emerg Contact"],
        )

    @allure.title("Super lease-Authorized access contact details are shown")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64689")
    def test_super_lease_shows_authorized_access_contact(
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
        extras = rental_extras(
            test_data("mp_rental"), authorized_access=True, coverage=False
        )
        authorized = extras["authorized_access"]
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=[
                "{space}",
                "AUTHORIZED ACCESS CONTACT",
                authorized["last_name"],
                authorized["email"],
            ],
        )

    @allure.title("Super lease-Authorized access contact left blank when not given")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64690")
    def test_super_lease_authorized_access_blank_when_not_given(
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
        extras = rental_extras(test_data("mp_rental"), coverage=False)
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=["{space}"],
            pdf_must_not_contain=["Auth Contact"],
        )

    @allure.title("Super lease-Military information is shown")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64693")
    def test_super_lease_shows_military_information(
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
        extras = rental_extras(
            test_data("mp_rental"), military=True, coverage=False
        )
        military = extras["military"]
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=[
                "{space}",
                "MILITARY INFORMATION",
                military["branch"],
                military["identification_number"],
            ],
        )

    @allure.title("Super lease-Military information left blank when not given")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64694")
    def test_super_lease_military_information_blank_when_not_given(
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
        extras = rental_extras(test_data("mp_rental"), coverage=False)
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=["{space}"],
            pdf_must_not_contain=["DOD-AUTO-001", "Dod-auto-001"],
        )

    @allure.title("Super lease-Lien holder information is shown")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64695")
    def test_super_lease_shows_lien_holder_information(
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
        extras = rental_extras(
            test_data("mp_rental"), lien_holder=True, coverage=False
        )
        lien = extras["lien_holder"]
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=[
                "{space}",
                "LIEN HOLDER",
                lien["last_name"],
                lien["email"],
            ],
        )

    @allure.title("Super lease-Lien holder information left blank when not given")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64696")
    def test_super_lease_lien_holder_blank_when_not_given(
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
        extras = rental_extras(test_data("mp_rental"), coverage=False)
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=["{space}"],
            pdf_must_not_contain=["Lien Bank"],
        )

    @allure.title("Super lease-Payment with insurance")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64995")
    def test_payment_with_insurance_and_super_lease(
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
        extras = rental_extras(test_data("mp_rental"), coverage=True)
        result = _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=["{space}", "COVERAGE", "Premium"],
        )
        text = result["pdf_text"]
        assert not (
            re.search(r"Coverage:\s*\$0\.00", text)
            and re.search(r"Premium:\s*\$0\.00", text)
        ), "Expected a non-zero protection plan on the Superlease"

    @allure.title("Super lease-Payment without insurance")
    @pytest.mark.smoke
    @pytest.mark.testrail("C64996")
    def test_payment_without_insurance_and_super_lease(
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
        extras = rental_extras(test_data("mp_rental"), coverage=False)
        _run_super_lease_rental(
            browser=browser,
            environment=environment,
            environment_config=environment_config,
            app_config=app_config,
            mp_guest=mp_guest,
            property_landing_page_url=property_landing_page_url,
            hb_login_page=hb_admin_session,
            test_data=test_data,
            move_out_after_rental=move_out_after_rental,
            extras=extras,
            include_alternate=False,
            pdf_must_contain=["{space}", "Coverage:", "$0.00", "N/A"],
        )

    @allure.title("Super lease-Quarterly billing cycle")
    @pytest.mark.smoke
    @pytest.mark.testrail("C66598")
    def test_quarterly_billing_cycle_payment_and_super_lease(self) -> None:
        pytest.skip(
            "No quarterly-billed unit path walked on stage Garden Grove yet "
            "(Superlease shows Payment Cycle: Monthly for standard storage)"
        )
