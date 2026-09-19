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
from common_utils.mp_rental_cases import run_rental_case
from config.config_reader import load_gateways, load_property
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_payment_processing_page import HBPaymentProcessingPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

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
    hb_admin_session, environment_config, app_config
) -> None:
    """Set APW Advanced Reservations from per-property config/properties/<env>.ini.

    Requires apw_advance_reservation_enable = true | false and
    lease_configuration_property_name (facility contains-match, same as
    Lease Configuration property selection). Reuses module ``hb_admin_session``.
    """
    ensure_property_advanced_reservations(
        hb_admin_session, environment_config, app_config
    )


# --- Legacy / Two-Step signing (module scope) ---------------------------------


def _verify_legacy_storefront_flow(
    signing,
    *,
    browser,
    app_config,
    environment_config,
    property_landing_page_url,
) -> None:
    """Confirm Mariposa serves Legacy Reserve This Space after configure+flush.

    Admin Two-Step-off alone has been wrong while the storefront kept
    Reserve Now (stage/Garden Grove, 2026-09-19).

    Uses a tab on the existing HB admin context and discovers the landing
    URL on that same tab — never opens the session property-discovery
    Chromium window (that was the persistent third window).
    """
    del browser  # same Browser as hb_admin_session; keep call-site signature
    from pages.mariposa.mp_unit_search_page import MPUnitSearchPage

    prop = environment_config.legacy_property
    if not prop or not (prop.mp_state and prop.mp_city):
        return
    timeout = app_config.getint("browser", "timeout")
    store_page = signing.hb_login_page.page.context.new_page()
    try:
        store_page.set_default_timeout(timeout)
        # Resolve + verify on this tab only (page= avoids discovery_context).
        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            prop.mp_state,
            prop.mp_city,
            page=store_page,
        )
        rental_page = MPUnitSearchPage(store_page, environment_config, timeout)
        signing.two_step_rental_page.verify_two_step_on_storefront(
            signing.fms_property_name,
            False,
            rental_page,
            property_url=property_url,
        )
    finally:
        try:
            store_page.close()
        except Exception:
            pass


@pytest.fixture(scope="module")
def legacy_traditional_signing(
    hb_admin_session,
    environment_config,
    app_config,
    browser,
    property_landing_page_url,
) -> None:
    """Traditional signing: Clickwrap off, Super Lease off, Two-Step off."""
    with legacy_signing_setup(
        hb_admin_session, environment_config, app_config
    ) as signing:
        signing.disable_clickwrap_and_super_lease()
        signing.flush_website_cache()
        _verify_legacy_storefront_flow(
            signing,
            browser=browser,
            app_config=app_config,
            environment_config=environment_config,
            property_landing_page_url=property_landing_page_url,
        )


@pytest.fixture(scope="module")
def legacy_clickwrap_signing(
    hb_admin_session,
    environment_config,
    app_config,
    browser,
    property_landing_page_url,
) -> None:
    """Clickwrap signing: Clickwrap on, Super Lease off, Two-Step off."""
    with legacy_signing_setup(
        hb_admin_session, environment_config, app_config
    ) as signing:
        signing.enable_clickwrap_with_super_lease_disabled()
        signing.flush_website_cache()
        _verify_legacy_storefront_flow(
            signing,
            browser=browser,
            app_config=app_config,
            environment_config=environment_config,
            property_landing_page_url=property_landing_page_url,
        )


@pytest.fixture(scope="module")
def legacy_superlease_signing(
    hb_admin_session,
    environment_config,
    app_config,
    browser,
    property_landing_page_url,
) -> None:
    """Super Lease signing: Clickwrap on, Super Lease on, Two-Step off."""
    with legacy_signing_setup(
        hb_admin_session, environment_config, app_config
    ) as signing:
        signing.enable_super_lease_and_clickwrap()
        signing.flush_website_cache()
        _verify_legacy_storefront_flow(
            signing,
            browser=browser,
            app_config=app_config,
            environment_config=environment_config,
            property_landing_page_url=property_landing_page_url,
        )


# two_step_superlease_checked / ensure_two_step_superlease live in
# tests/mp/conftest.py so reservations + account suites can use them too.


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
            outcomes: dict[str, str] = {}
            gateways = [
                gateway
                for gateway in load_gateways(app_config, profile)
                if gateway.method == method
            ]
            if gateways:
                rental_property = load_property(
                    app_config, environment, property_key
                )
                dashboard_name = (
                    rental_property.hb_property_name
                    or rental_property.lease_configuration_property_name
                )
                settings_name = (
                    rental_property.lease_configuration_property_name
                    or rental_property.hb_property_name
                )
                if page is not None:
                    if batch_page is not page:
                        log_in(page, environment_config, timeout)
                        batch_payments = HBPaymentProcessingPage(
                            page, timeout, HBSettingsNavigation(page, timeout)
                        )
                        batch_page = page
                    assert batch_payments is not None
                    # Stage Hamilton vs Rutland: Payment Processing Select
                    # Property only lists facilities for the dashboard
                    # property (live 2026-09-19).
                    if dashboard_name:
                        HBLoginPage(
                            page, environment_config, timeout
                        ).ensure_on_dashboard()
                        HBQuickLaunchPage(page, timeout).select_property(
                            dashboard_name
                        )
                    # Prior HB validation uses ensure_on_dashboard and leaves
                    # Settings closed; reuse must reopen Payment Processing
                    # before Select Property (live 2026-09-18 clickwrap ACH).
                    select = page.get_by_role(
                        "textbox", name="Select Property", exact=True
                    )
                    try:
                        settings_ready = select.is_visible(timeout=500)
                    except Exception:
                        settings_ready = False
                    if not settings_ready:
                        batch_payments.open_payment_processing()
                    batch_payments.select_property(settings_name)
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
                    if dashboard_name:
                        HBQuickLaunchPage(
                            payments.page, timeout
                        ).select_property(dashboard_name)
                    payments.open_payment_processing()
                    payments.select_property(settings_name)
                    outcomes = payments.ensure_gateways(gateways)
            # Cache successes only — a failed ensure must not poison the
            # rest of the session (pytest reruns / later methods).
            results[key] = (profile, outcomes)
        return results[key][1]

    yield ensure
    if context is not None:
        close_context_with_videos(
            context, app_config, name="payment-gateways-video"
        )


# --- Case runner (gateway matrix folders) ------------------------------------


@pytest.fixture
def rental_case_runner(
    request,
    hb_admin_session,
    environment,
    environment_config,
    app_config,
    mp_guest,
    property_landing_page_url,
    test_data,
    payment_gateways,
    gateway_profile,
):
    """run(case, two_step=False) on Legacy or Two-Step property from config.

    Desktop: one browser tab for HB setup → storefront → HB validation
    (URL switching on ``hb_admin_session.page``) so Allure gets a single
    execution-video with no ffmpeg merge. Mobile still uses ``mobile_page``.
    """

    def run(case, two_step: bool = False, card: dict | None = None) -> None:
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
        # One tab for desktop rentals (HB + Mariposa). Mobile keeps its own
        # phone viewport page.
        if case.view == "mobile":
            storefront_page = request.getfixturevalue("mobile_page")
        else:
            storefront_page = hb_admin_session.page
        if gateway_profile:
            _log.info(
                "Payment gateways on shared HB/storefront tab "
                "(single browser window)"
            )
            # Only the property this case rents — stage Payment Processing
            # for Hamilton does not list Lightning Storage (2026-09-19).
            try:
                payment_gateways(
                    property_key,
                    gateway_profile,
                    "ACH" if case.payment == "ach" else "Credit Cards",
                    page=hb_admin_session.page,
                )
            except Exception:
                raise
            # Soft-ensure sibling rental properties when they share a company.
            for key in rental_property_keys(app_config, environment):
                if key == property_key:
                    continue
                try:
                    payment_gateways(
                        key,
                        gateway_profile,
                        "ACH" if case.payment == "ach" else "Credit Cards",
                        page=hb_admin_session.page,
                    )
                except Exception as error:
                    allure.attach(
                        repr(error)[:1000],
                        name=f"payment gateways not ready on {key}",
                        attachment_type=allure.attachment_type.TEXT,
                    )
        _log.info(
            "Property landing discovery on shared tab for %s / %s",
            property_config.mp_state,
            property_config.mp_city,
        )
        property_url = property_landing_page_url(
            environment_config.mp_base_url,
            property_config.mp_state,
            property_config.mp_city,
            page=storefront_page,
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
            hb_login_page=hb_admin_session,
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
            card=card,
        )

    return run
