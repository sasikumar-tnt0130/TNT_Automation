import allure
import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage

# Every combination of Landing Page Layout (Default/Grid View/List View)
# x Value Tier Layout (Grid View/List View, no "Default") - hardcoded
# here rather than read from environments.ini, so every environment
# always exercises all 6 regardless of its own config.
LAYOUT_COMBINATIONS = [
    ("Default", "Grid View"),
    ("Grid View", "Grid View"),
    ("List View", "Grid View"),
    ("Default", "List View"),
    ("Grid View", "List View"),
    ("List View", "List View"),
]


def _select_unit(rental_page: MPUnitSearchPage, environment_config) -> tuple[str, str]:
    """Navigates the storefront to a unit and reads back which Landing
    Page Layout/Value Tier Layout actually rendered - just far enough to
    reach the reservation window (MPUnitSearchPage.wait_for_reservation_flow),
    not through filling in or submitting the reservation form itself,
    since this suite is only validating that the configured layout is
    what the storefront actually used."""
    if environment_config.mp_state and environment_config.mp_city:
        rental_page.search_storage_location(
            state=environment_config.mp_state, city=environment_config.mp_city
        )
    else:
        rental_page.select_first_available_location()
    actual_landing_layout, actual_tier_layout = rental_page.select_unit()
    flow = rental_page.wait_for_reservation_flow()
    assert flow == "legacy", (
        f"Expected the Legacy reservation flow to render, got {flow!r}"
    )
    return actual_landing_layout, actual_tier_layout


@allure.feature("MP Reservation")
@allure.story("Legacy Flow: Landing Page Layout x Value Tier Layout combinations")
class TestLayoutCombinations:
    # FMS Initial Setup's Landing Page Layout (controls the storefront's
    # unit-listing page rendering) and Value Tier Layout (controls the
    # protection-plan tier-selection dialog's rendering) are independent
    # settings that can be combined freely - MPUnitSearchPage.select_unit
    # already detects and handles every combination at runtime, and
    # reports back which one it used. These tests configure each
    # combination and assert the storefront actually rendered it, up to
    # the reservation window - not a full reservation, since that's
    # already covered by test_legacy_reservation.py and isn't needed to
    # validate layout rendering.

    @pytest.fixture(autouse=True)
    def _restore_layout(self, hb_login_page, environment_config, app_config):
        yield
        lease_configuration = LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        )
        lease_configuration.set_landing_page_layout(environment_config.landing_page_layout)
        lease_configuration.set_value_tier_layout(environment_config.value_tier_layout)

    @pytest.mark.parametrize("landing_layout,tier_layout", LAYOUT_COMBINATIONS)
    @allure.title(
        "Landing Page Layout = {landing_layout}, Value Tier Layout = "
        "{tier_layout} renders as configured - Desktop"
    )
    def test_layout_renders_as_configured_desktop(
        self, landing_layout, tier_layout, hb_login_page, environment_config, app_config
    ) -> None:
        lease_configuration = LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        )
        lease_configuration.set_landing_page_layout(landing_layout)
        lease_configuration.set_value_tier_layout(tier_layout)

        timeout = app_config.getint("browser", "timeout")
        rental_page = MPUnitSearchPage(
            hb_login_page.page, environment_config.mp_base_url, timeout
        )
        rental_page.open_storefront()
        actual_landing_layout, actual_tier_layout = _select_unit(
            rental_page, environment_config
        )
        assert actual_landing_layout == landing_layout, (
            f"Landing Page Layout mismatch: configured {landing_layout!r}, "
            f"storefront rendered {actual_landing_layout!r}"
        )
        assert actual_tier_layout == tier_layout, (
            f"Value Tier Layout mismatch: configured {tier_layout!r}, "
            f"storefront rendered {actual_tier_layout!r}"
        )

    @pytest.mark.parametrize("landing_layout,tier_layout", LAYOUT_COMBINATIONS)
    @allure.title(
        "Landing Page Layout = {landing_layout}, Value Tier Layout = "
        "{tier_layout} renders as configured - Mobile"
    )
    def test_layout_renders_as_configured_mobile(
        self,
        landing_layout,
        tier_layout,
        hb_login_page,
        mobile_page,
        environment_config,
        app_config,
        mp_property_url,
    ) -> None:
        lease_configuration = LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        )
        lease_configuration.set_landing_page_layout(landing_layout)
        lease_configuration.set_value_tier_layout(tier_layout)

        timeout = app_config.getint("browser", "timeout")
        rental_page = MPUnitSearchPage(
            mobile_page, environment_config.mp_base_url, timeout
        )
        rental_page.open_property_page(mp_property_url)
        actual_landing_layout, actual_tier_layout = rental_page.select_unit()
        flow = rental_page.wait_for_reservation_flow()
        assert flow == "legacy", (
            f"Expected the Legacy reservation flow to render, got {flow!r}"
        )
        assert actual_landing_layout == landing_layout, (
            f"Landing Page Layout mismatch: configured {landing_layout!r}, "
            f"storefront rendered {actual_landing_layout!r}"
        )
        assert actual_tier_layout == tier_layout, (
            f"Value Tier Layout mismatch: configured {tier_layout!r}, "
            f"storefront rendered {actual_tier_layout!r}"
        )
