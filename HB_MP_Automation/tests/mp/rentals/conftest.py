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
      conftest.py ensures Autotest Document Templates (Lease / Military /
      Vehicle / Autopay). Signing mode stays on each test class.

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
from common_utils.document_templates_setup import DocumentTemplatesSetup
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
scoped_rental_property_keys = _helpers.scoped_rental_property_keys
disable_property_advanced_reservations_overrides = (
    _helpers.disable_property_advanced_reservations_overrides
)
ensure_property_advanced_reservations = _helpers.ensure_property_advanced_reservations
ensure_advance_reservation_days = _helpers.ensure_advance_reservation_days
ensure_scoped_rental_preconditions = _helpers.ensure_scoped_rental_preconditions
module_owns_signing_precondition = _helpers.module_owns_signing_precondition
ensure_legacy_clickwrap = _helpers.ensure_legacy_clickwrap
ensure_legacy_superlease = _helpers.ensure_legacy_superlease
ensure_legacy_traditional = _helpers.ensure_legacy_traditional
ensure_module_payment_gateways = _helpers.ensure_module_payment_gateways


# --- Module property / signing precondition ----------------------------------


@pytest.fixture(scope="module", autouse=True)
def disable_property_advanced_reservations(
    request,
    hb_admin_session,
    environment_config,
    app_config,
) -> None:
    """APW + Advance Days for modules that do **not** own a signing precondition.

    Modules with a local ``precondition`` fixture (or usefixtures signing)
    run APW + days + toggles + Clear Cache themselves — skip here.
    """
    if module_owns_signing_precondition(request):
        _log.info(
            "Skip standalone APW/days for %s — module owns signing precondition",
            getattr(request.node, "name", "?"),
        )
        return
    days_dirty = ensure_scoped_rental_preconditions(
        request,
        hb_admin_session,
        environment_config,
        app_config,
        close_settings=True,
    )
    if not days_dirty:
        return
    with legacy_signing_setup(
        hb_admin_session, environment_config, app_config
    ) as signing:
        signing.flush_website_cache()


# --- Document templates / Legacy signing (module scope) ----------------------


@pytest.fixture(scope="module")
def ensure_autotest_document_templates(
    hb_admin_session, environment_config, app_config
) -> list[dict]:
    """Ensure Autotest V2 Document Templates (professional bodies, all types).

    Idempotent corporate-library create (Merge Fields + Save Template) for
    Lease (AZ-style rental agreement), Military, Vehicle, Autopay, COA,
    coverage, authorized access, Other signed, and merge catalog.
    Compose with ``legacy_traditional_signing`` (or clickwrap) for document
    suites — does not flip signing mode and does not Clear Cache.
    """
    setup = DocumentTemplatesSetup(
        hb_admin_session, environment_config, app_config
    )
    return setup.ensure_project_templates()


@pytest.fixture(scope="module")
def legacy_traditional_signing(
    hb_admin_session, environment_config, app_config
) -> None:
    """Traditional signing once: APW + days + toggles + Clear Cache."""
    ensure_legacy_traditional(
        hb_admin_session, environment_config, app_config
    )


@pytest.fixture(scope="module")
def legacy_clickwrap_signing(
    hb_admin_session, environment_config, app_config
) -> None:
    """Clickwrap signing once: APW + days + toggles + Clear Cache."""
    ensure_legacy_clickwrap(hb_admin_session, environment_config, app_config)


@pytest.fixture(scope="module")
def legacy_superlease_signing(
    hb_admin_session, environment_config, app_config
) -> None:
    """Super Lease signing once: APW + days + toggles + Clear Cache."""
    ensure_legacy_superlease(hb_admin_session, environment_config, app_config)


# two_step_superlease_checked lives in tests/mp/conftest.py (reservations too).


# --- Payment gateway profile + ensure ----------------------------------------


@pytest.fixture(scope="module")
def gateway_profile() -> str | None:
    """Default: no gateway ensure. Gateway folders override this fixture."""
    return None


@pytest.fixture(scope="module")
def module_payment_gateways_ready() -> dict[str, bool]:
    """Set by module ``precondition`` after ``ensure_module_payment_gateways``."""
    return {"ready": False}


@pytest.fixture(scope="session")
def payment_gateways(browser, environment, environment_config, app_config):
    """ensure(property_key, profile, method, page=None) → gateway outcomes.

    Cached once per session per (property, method) while the profile stays
    the same. Module preconditions pass the shared HB page so gateway
    ensure does not open a second Chromium context + HB login. Falls back
    to one session-owned context when no page is provided.

    ``method=None`` ensures every method in the profile in **one** Payment
    Processing visit (module precondition: CC + ACH without open/close
    twice — live 2026-09-22).
    """
    timeout = app_config.getint("browser", "timeout")
    results: dict[tuple[str, str], tuple[str, dict[str, str] | Exception]] = {}
    context = None
    payments = None
    batch_page = None
    batch_payments = None
    batch_settings_property: str | None = None

    def ensure(
        property_key: str,
        profile: str,
        method: str | None = None,
        page=None,
    ) -> dict[str, str]:
        nonlocal context, payments, batch_page, batch_payments, batch_settings_property
        all_gateways = load_gateways(app_config, profile)
        methods = (
            [method]
            if method
            else list(dict.fromkeys(gateway.method for gateway in all_gateways))
        )
        if not methods:
            return {}

        # Session cache hit for every requested method at this profile.
        cached: dict[str, str] = {}
        missing: list[str] = []
        for meth in methods:
            key = (property_key, meth)
            if key in results and results[key][0] == profile:
                part = results[key][1]
                if isinstance(part, dict):
                    cached.update(part)
                else:
                    missing.append(meth)
            else:
                missing.append(meth)
        if not missing:
            return cached

        gateways = [
            gateway
            for gateway in all_gateways
            if gateway.method in missing
        ]
        outcomes: dict[str, str] = {}
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
                    batch_settings_property = None
                assert batch_payments is not None
                # Stage Hamilton vs Rutland: Payment Processing Select
                # Property only lists facilities for the dashboard
                # property (live 2026-09-19).
                select = page.get_by_role(
                    "textbox", name="Select Property", exact=True
                )
                try:
                    settings_ready = select.is_visible(timeout=500)
                except Exception:
                    settings_ready = False
                if not settings_ready:
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
                    batch_payments.open_payment_processing()
                    batch_settings_property = None
                if settings_name and batch_settings_property != settings_name:
                    batch_payments.select_property(settings_name)
                    batch_settings_property = settings_name
                outcomes = batch_payments.ensure_gateways(
                    gateways, close_settings=True
                )
                batch_settings_property = None
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
            for meth in missing:
                method_outcomes = {
                    key: value
                    for key, value in outcomes.items()
                    if any(
                        gateway.key == key and gateway.method == meth
                        for gateway in gateways
                    )
                }
                results[(property_key, meth)] = (profile, method_outcomes)
        return {**cached, **outcomes}

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
