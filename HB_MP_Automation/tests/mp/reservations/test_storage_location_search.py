import re

import allure
import pytest
from playwright.sync_api import expect

from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


@pytest.fixture
def storefront(page, environment_config, app_config) -> MPUnitSearchPage:
    if not (environment_config.mp_city and environment_config.mp_state):
        pytest.skip(
            f"No storefront property (mp_city/mp_state) configured for "
            f"{environment_config.name} in properties.ini"
        )
    storefront_page = MPUnitSearchPage(
        page, environment_config.mp_base_url, app_config.getint("browser", "timeout")
    )
    storefront_page.open_storefront()
    storefront_page.search_from_locations_page(
        f"{environment_config.mp_city}, {environment_config.mp_state}"
    )
    return storefront_page


@allure.title("A city search lists the configured storage location with its best price")
@allure.feature("MP Storage Facility Smoke")
@allure.story("Validate Number of available units")
def test_validate_number_of_available_units(storefront, environment_config) -> None:
    assert storefront.locations_found_count() >= 1
    card = storefront.location_card(environment_config.mp_city)
    expect(card).to_be_visible()
    # Confirmed live (2026-09-12, uat_storoutlet): each result card shows
    # a "BEST PRICE* $4.50 WEB RATE" line for the location.
    expect(card).to_contain_text(re.compile(r"BEST PRICE\*?\s*\$\d"))


@allure.title("A location's unit sizes are listed and a unit can be taken to its reservation form")
@allure.feature("MP Storage Facility Smoke")
@allure.story("Validate Unit Details section")
def test_validate_unit_details_section(storefront, environment_config) -> None:
    storefront.open_location_from_results(environment_config.mp_city)
    storefront.assert_facility_landing_page_content()
    storefront.assert_unit_size_sections_listed()
    # The old Robot suite's Grid View branch of "Verify UI Is Default or
    # Grid View": select a unit, pick its protection-plan tier, and reach
    # the reservation form - stopped there, nothing is submitted. Which
    # form renders depends on the property's Two-Step Rental setting
    # (confirmed live 2026-09-12, uat_storoutlet: Bellflower serves
    # Legacy "Reserve This Space", Chula Vista serves Two-Step "Reserve
    # Now"); wait_for_reservation_flow accepts either.
    storefront.select_unit()
    flow = storefront.wait_for_reservation_flow()
    allure.attach(flow, name="reservation-flow", attachment_type=allure.attachment_type.TEXT)
