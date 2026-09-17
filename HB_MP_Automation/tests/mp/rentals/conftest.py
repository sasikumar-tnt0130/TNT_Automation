"""Rentals suite fixtures (signing, payment gateways, case runner).

Layout under tests/mp/rentals/:

  conftest.py (this file)
      Shared by every test under rentals/ (including documents/).
      Autouse: disable property-level Advanced Reservations override when
      configured. Signing modes, payment_gateways cache, rental_case_runner,
      and the default gateway_profile=None (no gateway ensure).

  tenant_payments_gateway/conftest.py
      Overrides gateway_profile → "tenant_payments". Required — do not
      delete; pytest directory override is how that folder selects TP.

  non_tenant_payments_gateway/conftest.py
      Overrides gateway_profile → "non_tenant_payments". Same as above.

  documents/
      No conftest — inherits this file only (signing fixtures; no runner).

Helpers live in _helpers.py so this file stays fixtures-only.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import allure
import pytest

from common_utils.browser_sessions import (
    close_context_with_videos,
    desktop_context_options,
    prepare_desktop_page,
)
from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from common_utils.mp_rental_cases import run_rental_case
from config.config_reader import load_gateways, load_property
from pages.common.hb_payment_processing_page import HBPaymentProcessingPage
from pages.common.hb_settings_navigation import HBSettingsNavigation

_log = logging.getLogger("hb_mp.rentals")

# Load same-folder helpers without making tests/ a package or touching sys.path.
_helpers_spec = importlib.util.spec_from_file_location(
    "mp_rentals_helpers", Path(__file__).with_name("_helpers.py")
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)
legacy_signing_setup = _helpers.legacy_signing_setup
log_in = _helpers.log_in
permissions = _helpers.permissions
rental_property_keys = _helpers.rental_property_keys
disable_property_advanced_reservations_overrides = (
    _helpers.disable_property_advanced_reservations_overrides
)
ensure_property_advanced_reservations = _helpers.ensure_property_advanced_reservations


# --- Lead Management Property Settings (module autouse) ----------------------


@pytest.fixture(scope="module", autouse=True)
def disable_property_advanced_reservations(
    browser, environment_config, app_config
) -> None:
    """Set APW Advanced Reservations from per-property config/properties/<env>.ini.

    Requires apw_advance_reservation_enable = true | false and
    lease_configuration_property_name (facility contains-match, same as
    Lease Configuration property selection).
    """
    ensure_property_advanced_reservations(
        browser, environment_config, app_config
    )


# --- Legacy / Two-Step signing (module scope) ---------------------------------


@pytest.fixture(scope="module")
def legacy_traditional_signing(browser, environment_config, app_config) -> None:
    """Traditional signing: Clickwrap off, Super Lease off."""
    with legacy_signing_setup(browser, environment_config, app_config) as signing:
        signing.disable_clickwrap_and_super_lease()


@pytest.fixture(scope="module")
def legacy_clickwrap_signing(browser, environment_config, app_config) -> None:
    """Clickwrap signing: Clickwrap on, Super Lease off."""
    with legacy_signing_setup(browser, environment_config, app_config) as signing:
        signing.enable_clickwrap_with_super_lease_disabled()


@pytest.fixture(scope="module")
def legacy_superlease_signing(browser, environment_config, app_config) -> None:
    """Super Lease signing: Clickwrap on, Super Lease on."""
    with legacy_signing_setup(browser, environment_config, app_config) as signing:
        signing.enable_super_lease_and_clickwrap()


@pytest.fixture(scope="module")
def two_step_superlease_checked(
    browser, environment_config, app_config, two_step_property
) -> None:
    """Read-only: Two-Step property must already have Clickwrap + Super Lease on.

    Settings are checked, never changed. Storefront flow is verified by
    MPTwoStepReservationSetup.reserve_unit instead.
    """
    from common_utils.browser_sessions import hb_admin_context

    with hb_admin_context(browser, environment_config, app_config) as hb_login_page:
        signing = LeaseConfigurationSetup(
            hb_login_page,
            environment_config,
            app_config,
            property_name=two_step_property.lease_configuration_property_name,
            fms_property_name=two_step_property.fms_property_name,
        )
        signing.open_state_compliance_tools()
        clickwrap = signing.lease_configuration.is_clickwrap_signature_enabled()
        super_lease = signing.lease_configuration.is_super_lease_enabled()
    if not (clickwrap and super_lease):
        pytest.fail(
            f"{two_step_property.lease_configuration_property_name} isn't on "
            f"Super Lease signing (Clickwrap {clickwrap}, Super Lease "
            f"{super_lease}) - its settings are only checked here, not changed"
        )


# --- Payment gateway profile + ensure ----------------------------------------


@pytest.fixture
def gateway_profile() -> str | None:
    """Default: no gateway ensure. Gateway folders override this fixture."""
    return None


@pytest.fixture(scope="session")
def payment_gateways(browser, environment, environment_config, app_config):
    """ensure(property_key, profile, method, page=None) → gateway outcomes.

    Cached once per session per (property, method) while the profile stays
    the same. Prefer an existing test page (rental_case_runner passes
    hb_login_page.page) so gateway ensure does not open a second Chromium
    context + HB login. Falls back to one session-owned context when no
    page is provided.
    """
    timeout = app_config.getint("browser", "timeout")
    results: dict[tuple[str, str], tuple[str, dict[str, str] | Exception]] = {}
    context = None
    payments = None
    batch_page = None
    batch_payments = None

    def ensure(
        property_key: str, profile: str, method: str, page=None
    ) -> dict[str, str]:
        nonlocal context, payments, batch_page, batch_payments
        key = (property_key, method)
        if key not in results or results[key][0] != profile:
            try:
                outcomes: dict[str, str] = {}
                gateways = [
                    gateway
                    for gateway in load_gateways(app_config, profile)
                    if gateway.method == method
                ]
                if gateways:
                    if page is not None:
                        if batch_page is not page:
                            log_in(page, environment_config, timeout)
                            batch_payments = HBPaymentProcessingPage(
                                page, timeout, HBSettingsNavigation(page, timeout)
                            )
                            batch_payments.open_payment_processing()
                            batch_page = page
                        assert batch_payments is not None
                        rental_property = load_property(
                            app_config, environment, property_key
                        )
                        batch_payments.select_property(
                            rental_property.lease_configuration_property_name
                            or rental_property.hb_property_name
                        )
                        outcomes = batch_payments.ensure_gateways(gateways)
                    else:
                        if payments is None:
                            context = browser.new_context(
                                **desktop_context_options(
                                    app_config, record_video=False
                                )
                            )
                            owned = context.new_page()
                            prepare_desktop_page(owned, app_config, record_artifacts=False)
                            log_in(owned, environment_config, timeout)
                            payments = HBPaymentProcessingPage(
                                owned, timeout, HBSettingsNavigation(owned, timeout)
                            )
                            payments.open_payment_processing()
                        rental_property = load_property(
                            app_config, environment, property_key
                        )
                        payments.select_property(
                            rental_property.lease_configuration_property_name
                            or rental_property.hb_property_name
                        )
                        outcomes = payments.ensure_gateways(gateways)
                results[key] = (profile, outcomes)
            except Exception as error:
                results[key] = (profile, error)
        outcome = results[key][1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    yield ensure
    if context is not None:
        close_context_with_videos(
            context, app_config, name="payment-gateways-video"
        )


# --- Case runner (gateway matrix folders) ------------------------------------


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
    payment_gateways,
    gateway_profile,
):
    """run(case, two_step=False) on Legacy or Two-Step property from config."""

    def run(case, two_step: bool = False) -> None:
        missing = sorted(
            marker
            for marker in case.markers
            if request.node.get_closest_marker(marker) is None
        )
        if missing:
            pytest.fail(
                f"{request.node.name}: its markers don't match its case - "
                f"missing {missing}"
            )
        setting = "two_step_property" if two_step else "legacy_property"
        property_key = app_config.get(environment, setting, fallback="").strip()
        if not property_key:
            pytest.skip(
                f"No {setting} configured for {environment} in config/properties/"
            )
        property_config = load_property(app_config, environment, property_key)
        if gateway_profile:
            _log.info(
                "Payment gateways on shared test page (no extra Chromium context)"
            )
            for key in rental_property_keys(app_config, environment):
                try:
                    payment_gateways(
                        key,
                        gateway_profile,
                        "ACH" if case.payment == "ach" else "Credit Cards",
                        page=hb_login_page.page,
                    )
                except Exception as error:
                    if key == property_key:
                        raise
                    allure.attach(
                        repr(error)[:1000],
                        name=f"payment gateways not ready on {key}",
                        attachment_type=allure.attachment_type.TEXT,
                    )
        _log.info(
            "Property landing discovery on shared test page for %s / %s",
            property_config.mp_state,
            property_config.mp_city,
        )
        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            property_config.mp_state,
            property_config.mp_city,
            page=page,
        )
        storefront_page = (
            request.getfixturevalue("mobile_page")
            if case.view == "mobile"
            else page
        )
        rental_data = test_data("mp_rental")
        if gateway_profile:
            method = "ACH" if case.payment == "ach" else "Credit Cards"
            rental_data = {
                **rental_data,
                "billing_address_required": any(
                    gateway.billing_address_required
                    for gateway in load_gateways(app_config, gateway_profile)
                    if gateway.method == method
                ),
            }
        run_rental_case(
            case=case,
            two_step=two_step,
            storefront_page=storefront_page,
            hb_login_page=hb_login_page,
            environment_config=environment_config,
            app_config=app_config,
            property_config=property_config,
            property_url=property_url,
            rental_data=rental_data,
            guest=mp_guest,
            move_out=request.getfixturevalue("move_out_after_rental"),
            cancel_reservation_hold=request.getfixturevalue("cancel_reservation_after"),
            # tenant_payments_gateway / non_tenant_payments_gateway: do not
            # burn time on HB tenant checks when MP confirmation already failed.
            skip_hb_on_confirmation_failure=bool(gateway_profile),
        )

    return run
