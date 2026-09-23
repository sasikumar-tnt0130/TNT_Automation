import allure
import pytest
from pathlib import Path

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.wrapper_methods import (
    confirmation_dir_for_current_test,
    save_confirmation_screenshot,
)
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage
from tests.mp.reservations._helpers import ensure_legacy_traditional

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"

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


@pytest.fixture(scope="module", autouse=True)
def precondition(hb_admin_session, environment_config, app_config) -> None:
    """Once: APW + Traditional (Two-Step/CW/SL off) + Clear Cache.

    Landing/tier layouts are set per test — do not force env landing layout.
    """
    ensure_legacy_traditional(hb_admin_session, environment_config, app_config)


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


def _select_unit(
    rental_page: MPUnitSearchPage,
    environment_config,
    landing_layout: str,
    tier_layout: str,
    shot_dir: Path,
) -> tuple[str, str]:
    """Navigates the storefront to a unit and reads back which Landing
    Page Layout/Value Tier Layout actually rendered - just far enough to
    reach the reservation window (MPUnitSearchPage.wait_for_reservation_flow),
    not through filling in or submitting the reservation form itself,
    since this suite is only validating that the configured layout is
    what the storefront actually used.

    Screenshots (under shot_dir): unit-listing, value-tier (when the
    protection-plan dialog appears - skipped for Default landing which
    bypasses it), then reservation."""
    if environment_config.mp_state and environment_config.mp_city:
        rental_page.search_storage_location(
            state=environment_config.mp_state, city=environment_config.mp_city
        )
    else:
        rental_page.select_first_available_location()
    _save_layout_screenshot(
        rental_page.page, shot_dir, landing_layout, tier_layout, step="unit-listing"
    )
    actual_landing_layout, actual_tier_layout = rental_page.select_unit(
        on_value_tier_dialog=lambda page: _save_layout_screenshot(
            page, shot_dir, landing_layout, tier_layout, step="value-tier"
        )
    )
    flow = rental_page.wait_for_reservation_flow()
    assert flow == "legacy", (
        f"Expected the Legacy reservation flow to render, got {flow!r}"
    )
    _save_layout_screenshot(
        rental_page.page, shot_dir, landing_layout, tier_layout, step="reservation"
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
    def _layout_shot_dir(self, request):
        """One confirmation folder named after the test case (not
        \"unknown\" from a missing PYTEST_CURRENT_TEST)."""
        request.node.layout_shot_dir = confirmation_dir_for_current_test(
            REPORTS_DIR, test_name=request.node.name
        )
        return request.node.layout_shot_dir

    @pytest.fixture(autouse=True)
    def _restore_layout(self, hb_admin_session, environment_config, app_config):
        yield
        pass
        # lease_configuration = LeaseConfigurationSetup(
        #     hb_admin_session, environment_config, app_config
        # )
        # # Use the combined helper so restore still works when a Default
        # # case left Value Tier Layout hidden on the FMS form.
        # lease_configuration.set_landing_and_value_tier_layouts(
        #     environment_config.landing_page_layout,
        #     environment_config.value_tier_layout,
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
        request,
    ) -> None:
        lease_configuration = LeaseConfigurationSetup(
            hb_admin_session, environment_config, app_config
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
        actual_landing_layout, actual_tier_layout = _select_unit(
            rental_page,
            environment_config,
            landing_layout,
            tier_layout,
            shot_dir=request.node.layout_shot_dir,
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
        mp_property_url,
        request,
    ) -> None:
        lease_configuration = LeaseConfigurationSetup(
            hb_admin_session, environment_config, app_config
        )
        lease_configuration.set_landing_and_value_tier_layouts(
            landing_layout, tier_layout
        )
        # lease_configuration.flush_website_cache()

        timeout = app_config.getint("browser", "timeout")
        rental_page = MPUnitSearchPage(
            mobile_page, environment_config.mp_base_url, timeout
        )
        rental_page.open_property_page(mp_property_url)
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
        assert flow == "legacy", (
            f"Expected the Legacy reservation flow to render, got {flow!r}"
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
