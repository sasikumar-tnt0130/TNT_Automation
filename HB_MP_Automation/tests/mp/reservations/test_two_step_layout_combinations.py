from pathlib import Path

import allure
import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.wrapper_methods import (
    confirmation_dir_for_current_test,
    save_confirmation_screenshot,
)
from config.config_reader import PropertyConfig
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage
from tests.mp.reservations._helpers import ensure_two_step_superlease

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"

# See test_legacy_layout_combinations.py's LAYOUT_COMBINATIONS for the
# full rationale - same 6 Landing Page Layout x Value Tier Layout
# combinations, hardcoded rather than read from environments.ini.
LAYOUT_COMBINATIONS = [
    ("Default", "Grid View"),
    ("Grid View", "Grid View"),
    ("List View", "Grid View"),
    ("Default", "List View"),
    ("Grid View", "List View"),
    ("List View", "List View"),
]


def _layout_shot_name(landing_layout: str, tier_layout: str, step: str) -> str:
    safe = (
        f"{landing_layout}-{tier_layout}-{step}"
        .replace(" ", "_")
        .replace("/", "-")
    )
    return f"layout-{safe}.png"


def _save_layout_screenshot(
    page,
    shot_dir: Path,
    landing_layout: str,
    tier_layout: str,
    step: str,
) -> Path:
    """Full-page PNG under reports/confirmations/<test>-<ts>/ plus Allure."""
    path = shot_dir / _layout_shot_name(landing_layout, tier_layout, step)
    save_confirmation_screenshot(
        page,
        path,
        allure_name=f"{landing_layout} / {tier_layout} - {step}",
    )
    return path


@pytest.fixture(scope="module", autouse=True)
def precondition(
    hb_admin_session, environment_config, app_config, two_step_property
) -> None:
    """Once: APW + Two-Step/CW/SL + days + Clear Cache (same as rentals)."""
    ensure_two_step_superlease(
        hb_admin_session, environment_config, app_config, two_step_property
    )


def _lease_setup(hb_login_page, environment_config, app_config, prop: PropertyConfig):
    """LeaseConfigurationSetup aimed at two_step_property, not Legacy."""
    return LeaseConfigurationSetup(
        hb_login_page,
        environment_config,
        app_config,
        property_name=prop.lease_configuration_property_name,
        fms_property_name=prop.fms_property_name,
    )


@allure.feature("MP Reservation")
@allure.story("Two-Step Flow: Landing Page Layout x Value Tier Layout combinations")
class TestTwoStepLayoutCombinations:
    # See TestLayoutCombinations (test_legacy_layout_combinations.py) for
    # why every combination is exercised, and why this only drives up to
    # the reservation window rather than a full reservation - same
    # rationale, Two-Step flow. Always uses properties.ini
    # two_step_property (not flat environment_config Legacy fields).

    @pytest.fixture(autouse=True)
    def _layout_shot_dir(self, request):
        """One confirmation folder named after the test case (not
        \"unknown\" from a missing PYTEST_CURRENT_TEST)."""
        request.node.layout_shot_dir = confirmation_dir_for_current_test(
            REPORTS_DIR, test_name=request.node.name
        )
        return request.node.layout_shot_dir

    @pytest.fixture(autouse=True)
    def _restore_layout(
        self, hb_admin_session, environment_config, app_config, two_step_property
    ):
        yield
        pass
        # lease_configuration = _lease_setup(
        #     hb_admin_session, environment_config, app_config, two_step_property
        # )
        # lease_configuration.set_landing_and_value_tier_layouts(
        #     two_step_property.landing_page_layout,
        #     two_step_property.value_tier_layout,
        # )
        # lease_configuration.flush_website_cache()

    @pytest.mark.parametrize("landing_layout,tier_layout", LAYOUT_COMBINATIONS)
    @allure.title(
        "Landing Page Layout = {landing_layout}, Value Tier Layout = "
        "{tier_layout} renders as configured - Desktop"
    )
    def test_layout_renders_as_configured_desktop(
        self,
        landing_layout,
        tier_layout,
        hb_admin_session,
        page,
        environment_config,
        app_config,
        two_step_property,
        request,
    ) -> None:
        lease_configuration = _lease_setup(
            hb_admin_session, environment_config, app_config, two_step_property
        )
        lease_configuration.set_landing_and_value_tier_layouts(
            landing_layout, tier_layout
        )
        # lease_configuration.flush_website_cache()

        timeout = app_config.getint("browser", "timeout")
        rental_page = MPUnitSearchPage(
            page, environment_config.mp_base_url, timeout
        )
        rental_page.open_storefront()
        if two_step_property.mp_state and two_step_property.mp_city:
            rental_page.search_storage_location(
                state=two_step_property.mp_state, city=two_step_property.mp_city
            )
        else:
            rental_page.select_first_available_location()
        shot_dir = request.node.layout_shot_dir
        _save_layout_screenshot(
            rental_page.page,
            shot_dir,
            landing_layout,
            tier_layout,
            step="unit-listing",
        )
        actual_landing_layout, actual_tier_layout = rental_page.select_unit(
            on_value_tier_dialog=lambda page: _save_layout_screenshot(
                page, shot_dir, landing_layout, tier_layout, step="value-tier"
            )
        )
        flow = rental_page.wait_for_reservation_flow()
        assert flow == "two_step", (
            f"Expected the Two-Step reservation flow to render, got {flow!r}"
        )
        _save_layout_screenshot(
            rental_page.page,
            shot_dir,
            landing_layout,
            tier_layout,
            step="reservation",
        )
        assert actual_landing_layout == landing_layout, (
            f"Landing Page Layout mismatch: configured {landing_layout!r}, "
            f"storefront rendered {actual_landing_layout!r}"
        )
        # Default landing skips the Value Tier dialog (walked 2026-09-16
        # stage/Garden Grove) - select_unit reports "n/a" in that case.
        if actual_tier_layout != "n/a":
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
        hb_admin_session,
        mobile_page,
        environment_config,
        app_config,
        two_step_property,
        mp_property_landing_urls,
        request,
    ) -> None:
        lease_configuration = _lease_setup(
            hb_admin_session, environment_config, app_config, two_step_property
        )
        lease_configuration.set_landing_and_value_tier_layouts(
            landing_layout, tier_layout
        )
        # lease_configuration.flush_website_cache()

        property_url = mp_property_landing_urls["two_step"]
        timeout = app_config.getint("browser", "timeout")
        rental_page = MPUnitSearchPage(
            mobile_page, environment_config.mp_base_url, timeout
        )
        rental_page.open_property_page(property_url)
        shot_dir = request.node.layout_shot_dir
        _save_layout_screenshot(
            rental_page.page,
            shot_dir,
            landing_layout,
            tier_layout,
            step="unit-listing-mobile",
        )
        actual_landing_layout, actual_tier_layout = rental_page.select_unit(
            on_value_tier_dialog=lambda page: _save_layout_screenshot(
                page,
                shot_dir,
                landing_layout,
                tier_layout,
                step="value-tier-mobile",
            )
        )
        flow = rental_page.wait_for_reservation_flow()
        assert flow == "two_step", (
            f"Expected the Two-Step reservation flow to render, got {flow!r}"
        )
        _save_layout_screenshot(
            rental_page.page,
            shot_dir,
            landing_layout,
            tier_layout,
            step="reservation-mobile",
        )
        assert actual_landing_layout == landing_layout, (
            f"Landing Page Layout mismatch: configured {landing_layout!r}, "
            f"storefront rendered {actual_landing_layout!r}"
        )
        # Default landing skips the Value Tier dialog (walked 2026-09-16
        # stage/Garden Grove) - select_unit reports "n/a" in that case.
        if actual_tier_layout != "n/a":
            assert actual_tier_layout == tier_layout, (
                f"Value Tier Layout mismatch: configured {tier_layout!r}, "
                f"storefront rendered {actual_tier_layout!r}"
            )
