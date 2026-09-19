"""TestRail smoke run 2967 - renting more than one space as the same business
at the same property.

Walked live 2026-09-16 stage/Hamilton (Garden Grove, Legacy Traditional):
two sequential RAB reserve→rent cycles with the same guest email complete;
HB Tenants lists one Current row per space under "Auto Tester Business";
opening either contact shows both `Space <n>` headings on one tenant page.
Email search does not find RAB tenants - space / business name does.
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
from common_utils.mp_legacy_reservation_setup import MPLegacyReservationSetup
from common_utils.mp_rental_cases import move_out_rental
from config.config_reader import load_property
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.feature("MP Rentals")
@allure.story("Rent as a Business - multiple spaces")
@pytest.mark.usefixtures("legacy_traditional_signing")
class TestMultipleSpacesRab:
    @allure.title(
        "Rent as a Business-Two or more spaces for the same business and property"
    )
    @pytest.mark.smoke
    @pytest.mark.testrail("C64723")
    @pytest.mark.testrail("C66593")
    def test_rent_two_spaces_as_same_business(
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
        """C64723: second rental completes; HB shows one contact with both
        spaces (own lease row each). C66593: both rows / contact keep the
        same business profile name (HB check from live walk; lease PDFs not
        opened)."""
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
        business_name = f"{mp_guest['first_name']} {mp_guest['last_name']} Business"
        guest_name = f"{mp_guest['first_name']} {mp_guest['last_name']}"
        spaces: list[str] = []
        store_ctx = browser.new_context(**desktop_context_options(app_config))
        failure: BaseException | None = None
        try:
            with allure.step("First RAB reservation + rental"):
                first_page = store_ctx.new_page()
                prepare_desktop_page(first_page, app_config)
                setup1 = MPLegacyReservationSetup(
                    first_page, environment_config, app_config, property_url=property_url
                )
                setup1.reserve_unit(mp_guest, renting_as_business=True)
                rental1 = setup1.convert_reservation_to_rental(
                    mp_guest, rental_data, payment_method="card", autopay=False
                )
                spaces.append(rental1["space_number"])

            with allure.step("Second RAB reservation + rental (same business email)"):
                second_page = store_ctx.new_page()
                prepare_desktop_page(second_page, app_config)
                setup2 = MPLegacyReservationSetup(
                    second_page, environment_config, app_config, property_url=property_url
                )
                setup2.reserve_unit(mp_guest, renting_as_business=True)
                rental2 = setup2.convert_reservation_to_rental(
                    mp_guest, rental_data, payment_method="card", autopay=False
                )
                spaces.append(rental2["space_number"])

            hb_admin_session.ensure_logged_in()
            tenants = HBTenantSpacesPage(hb_admin_session.page, timeout)
            tenants.open_tenants(prop.hb_property_name)

            with allure.step("C64723: one tenant contact holds both spaces"):
                tenants.assert_business_holds_spaces(business_name, spaces)

            with allure.step("C66593: second space keeps the business profile"):
                # Re-open from the second space: same business name on the
                # contact that also lists the first space (live 2026-09-16).
                tenants.open_tenants(prop.hb_property_name)
                tenants.open_storefront_tenant(business_name, spaces[-1])
                expect(hb_admin_session.page.locator("body")).to_contain_text(
                    business_name
                )
                for space_number in spaces:
                    expect(
                        hb_admin_session.page.get_by_text(
                            f"Space {space_number}", exact=True
                        ).first
                    ).to_be_visible(timeout=timeout)
        except BaseException as error:
            failure = error
            raise
        finally:
            close_context_with_videos(store_ctx, app_config, name="storefront-video")
            if not move_out_after_rental:
                allure.attach(
                    f"{mp_guest['email']}, spaces {spaces}, property {prop.hb_property_name}",
                    name="move-out skipped (--no-move-out)",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return
            for space_number in spaces:
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
