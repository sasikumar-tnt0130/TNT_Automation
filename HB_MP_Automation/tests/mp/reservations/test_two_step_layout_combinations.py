import allure
import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from pages.common.hb_login_page import HBLoginPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage

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


@pytest.fixture(scope="class")
def _two_step_flow_configured(browser, environment_config, app_config) -> None:
    """One-time admin-side setup for every test in this class - see
    test_two_step_reservation.py's fixture of the same shape for the
    full rationale (server-side HB setting, own class-scoped login/
    context instead of every test repeating it)."""
    timeout = app_config.getint("browser", "timeout")
    permissions = [
        p.strip()
        for p in app_config.get("browser", "permissions", fallback="").split(",")
        if p.strip()
    ]
    context = browser.new_context(permissions=permissions, no_viewport=True)
    setup_page = context.new_page()
    setup_page.set_default_timeout(timeout)
    # Own context for the storefront self-heal check (enable_two_step_
    # clickwrap_and_super_lease's rental_page arg) - kept separate from
    # the admin context above, which stays on HB admin throughout.
    storefront_context = browser.new_context(permissions=permissions, no_viewport=True)
    try:
        hb_login_page = HBLoginPage(setup_page, environment_config, timeout)
        if hb_login_page.open_login_page():
            hb_login_page.submit_login_credentials()
        hb_login_page.assert_login_successful()

        storefront_page = storefront_context.new_page()
        storefront_page.set_default_timeout(timeout)
        rental_page = MPUnitSearchPage(
            storefront_page, environment_config.mp_base_url, timeout
        )

        LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        ).enable_two_step_clickwrap_and_super_lease(rental_page=rental_page)
    finally:
        storefront_context.close()
        context.close()


@allure.feature("MP Reservation")
@allure.story("Two-Step Flow: Landing Page Layout x Value Tier Layout combinations")
@pytest.mark.usefixtures("_two_step_flow_configured")
class TestTwoStepLayoutCombinations:
    # See TestLayoutCombinations (test_legacy_layout_combinations.py) for
    # why every combination is exercised, and why this only drives up to
    # the reservation window rather than a full reservation - same
    # rationale, Two-Step flow.

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
        if environment_config.mp_state and environment_config.mp_city:
            rental_page.search_storage_location(
                state=environment_config.mp_state, city=environment_config.mp_city
            )
        else:
            rental_page.select_first_available_location()
        actual_landing_layout, actual_tier_layout = rental_page.select_unit()
        flow = rental_page.wait_for_reservation_flow()
        assert flow == "two_step", (
            f"Expected the Two-Step reservation flow to render, got {flow!r}"
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
        property_landing_page_url,
    ) -> None:
        lease_configuration = LeaseConfigurationSetup(
            hb_login_page, environment_config, app_config
        )
        lease_configuration.set_landing_page_layout(landing_layout)
        lease_configuration.set_value_tier_layout(tier_layout)

        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            environment_config.mp_state,
            environment_config.mp_city,
        )
        timeout = app_config.getint("browser", "timeout")
        rental_page = MPUnitSearchPage(
            mobile_page, environment_config.mp_base_url, timeout
        )
        rental_page.open_property_page(property_url)
        actual_landing_layout, actual_tier_layout = rental_page.select_unit()
        flow = rental_page.wait_for_reservation_flow()
        assert flow == "two_step", (
            f"Expected the Two-Step reservation flow to render, got {flow!r}"
        )
        assert actual_landing_layout == landing_layout, (
            f"Landing Page Layout mismatch: configured {landing_layout!r}, "
            f"storefront rendered {actual_landing_layout!r}"
        )
        assert actual_tier_layout == tier_layout, (
            f"Value Tier Layout mismatch: configured {tier_layout!r}, "
            f"storefront rendered {actual_tier_layout!r}"
        )
