from contextlib import contextmanager

import pytest

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_rental_cases import run_rental_case
from config.config_reader import load_property
from pages.common.hb_login_page import HBLoginPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


def _permissions(app_config) -> list[str]:
    return [p.strip() for p in app_config.get("browser", "permissions", fallback="").split(",") if p.strip()]


def _log_in(page, environment_config, timeout) -> HBLoginPage:
    hb_login_page = HBLoginPage(page, environment_config, timeout)
    if hb_login_page.open_login_page():
        hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    return hb_login_page


@contextmanager
def _legacy_signing_setup(browser, environment_config, app_config):
    """Gives a fixture what it needs to switch the Legacy property's signing:
    `signing` (HB lease configuration, logged in on its own browser context)
    and `rental_page` (the storefront, on a separate context, which the
    switch uses to check the storefront serves the Legacy flow). Both
    contexts are closed afterwards. Signing is a shared, server-side HB
    setting - the user allowed switching it on the Legacy property only
    (2026-09-14) - so each fixture below runs once per test file."""
    timeout = app_config.getint("browser", "timeout")
    hb_context = browser.new_context(permissions=_permissions(app_config), no_viewport=True)
    storefront_context = browser.new_context(permissions=_permissions(app_config), no_viewport=True)
    try:
        hb_page = hb_context.new_page()
        hb_page.set_default_timeout(timeout)
        signing = LeaseConfigurationSetup(_log_in(hb_page, environment_config, timeout), environment_config, app_config)
        storefront_page = storefront_context.new_page()
        storefront_page.set_default_timeout(timeout)
        rental_page = MPUnitSearchPage(storefront_page, environment_config.mp_base_url, timeout)
        yield signing, rental_page
    finally:
        storefront_context.close()
        hb_context.close()


@pytest.fixture(scope="module")
def legacy_traditional_signing(browser, environment_config, app_config) -> None:
    """Traditional signing: Clickwrap off, Super Lease off (user, 2026-09-14)."""
    with _legacy_signing_setup(browser, environment_config, app_config) as (signing, rental_page):
        signing.disable_clickwrap_and_super_lease(rental_page=rental_page)

 
@pytest.fixture(scope="module")
def legacy_clickwrap_signing(browser, environment_config, app_config) -> None:
    """Clickwrap signing: Clickwrap on, Super Lease off (user, 2026-09-14)."""
    with _legacy_signing_setup(browser, environment_config, app_config) as (signing, rental_page):
        signing.enable_clickwrap_with_super_lease_disabled(rental_page=rental_page)


@pytest.fixture(scope="module")
def legacy_superlease_signing(browser, environment_config, app_config) -> None:
    """Super Lease signing: Clickwrap on, Super Lease on (user, 2026-09-14)."""
    with _legacy_signing_setup(browser, environment_config, app_config) as (signing, rental_page):
        signing.enable_super_lease_and_clickwrap(rental_page=rental_page)


@pytest.fixture(scope="module")
def two_step_superlease_checked(browser, environment, environment_config, app_config) -> None:
    """Read-only: the Two-Step property is only checked, never changed (user,
    2026-09-14) - it must already have Clickwrap and Super Lease on. Its
    Two-Step switch isn't read here (a probe read it off while the storefront
    served Two-Step, 2026-09-14); MPTwoStepReservationSetup.reserve_unit
    checks the flow the storefront actually serves instead."""
    property_key = app_config.get(environment, "two_step_property", fallback="").strip()
    if not property_key:
        pytest.skip(f"No two_step_property configured for {environment} in environments.ini")
    two_step_property = load_property(app_config, environment, property_key)
    timeout = app_config.getint("browser", "timeout")
    context = browser.new_context(permissions=_permissions(app_config), no_viewport=True)
    try:
        page = context.new_page()
        page.set_default_timeout(timeout)
        signing = LeaseConfigurationSetup(
            _log_in(page, environment_config, timeout),
            environment_config,
            app_config,
            property_name=two_step_property.lease_configuration_property_name,
            fms_property_name=two_step_property.fms_property_name,
        )
        signing.open_state_compliance_tools()
        clickwrap = signing.lease_configuration.is_clickwrap_signature_enabled()
        super_lease = signing.lease_configuration.is_super_lease_enabled()
    finally:
        context.close()
    if not (clickwrap and super_lease):
        pytest.fail(
            f"{two_step_property.lease_configuration_property_name} isn't on Super Lease signing "
            f"(Clickwrap {clickwrap}, Super Lease {super_lease}) - its settings are only "
            "checked here, not changed"
        )


@pytest.fixture
def rental_case_runner(
    request,
    page,
    hb_login_page,
    environment,
    environment_config,
    app_config,
    mp_guest,
    property_landing_page_url,
    test_data,
):
    """run(case, two_step=False) - one rental case on the environment's
    Legacy property (default_property) or Two-Step property
    (two_step_property). The storefront runs on the desktop `page` or the
    iPhone 13 `mobile_page`; HB always on the desktop page. Each test states
    its case and its markers explicitly (user, 2026-09-15), so the two are
    checked against each other first."""

    def run(case, two_step: bool = False) -> None:
        missing = sorted(marker for marker in case.markers if request.node.get_closest_marker(marker) is None)
        if missing:
            pytest.fail(f"{request.node.name}: its markers don't match its case - missing {missing}")
        setting = "two_step_property" if two_step else "default_property"
        property_key = app_config.get(environment, setting, fallback="").strip()
        if not property_key:
            pytest.skip(f"No {setting} configured for {environment} in environments.ini")
        property_config = load_property(app_config, environment, property_key)
        property_url = property_landing_page_url(
            environment_config.mp_base_url, property_config.mp_state, property_config.mp_city
        )
        storefront_page = request.getfixturevalue("mobile_page") if case.view == "mobile" else page
        run_rental_case(
            case=case,
            two_step=two_step,
            storefront_page=storefront_page,
            hb_login_page=hb_login_page,
            environment_config=environment_config,
            app_config=app_config,
            property_config=property_config,
            property_url=property_url,
            rental_data=test_data("mp_rental"),
            guest=mp_guest,
        )

    return run
