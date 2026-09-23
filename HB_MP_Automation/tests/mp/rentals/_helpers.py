"""Shared helpers for tests/mp/rentals/conftest.py (not pytest fixtures)."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from typing import Iterable

from common_utils.browser_sessions import browser_permissions
from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from config.config_reader import list_properties, load_gateways, load_property
from pages.common.hb_lead_scripts_page import HBLeadScriptsPage
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

_log = logging.getLogger("hb_mp.rentals")

_LEGACY_MARKERS = frozenset(
    {"legacy_clickwrap", "legacy_traditional", "legacy_superlease"}
)
_TWO_STEP_MARKERS = frozenset({"two_step_superlease"})
# Modules that usefixtures a signing mode own APW + days + flush themselves.
_SIGNING_MODULE_MARKERS = _LEGACY_MARKERS | _TWO_STEP_MARKERS
_SIGNING_FIXTURE_NAMES = frozenset(
    {
        "legacy_clickwrap_signing",
        "legacy_superlease_signing",
        "legacy_traditional_signing",
        "two_step_superlease_checked",
        "ensure_two_step_superlease",
        "legacy_traditional_checked",
        "legacy_reservation_checked",
    }
)


def permissions(app_config) -> list[str]:
    return browser_permissions(app_config)


def log_in(page, environment_config, timeout):
    """Login helper for callers that already own a page (e.g. payment_gateways)."""
    hb_login_page = HBLoginPage(page, environment_config, timeout)
    hb_login_page.ensure_logged_in()
    return hb_login_page


def rental_property_keys(app_config, environment) -> list[str]:
    """Legacy + Two-Step property keys from config/properties/<env>.ini."""
    keys = [
        app_config.get(environment, setting, fallback="").strip()
        for setting in ("legacy_property", "two_step_property")
    ]
    return list(dict.fromkeys(key for key in keys if key))


def all_property_keys(app_config, environment) -> list[str]:
    """Every property key listed under the environment's `properties`."""
    return list_properties(app_config, environment)


def _iter_pytestmarks(obj) -> list:
    marks = getattr(obj, "pytestmark", None)
    if marks is None:
        return []
    if not isinstance(marks, (list, tuple)):
        return [marks]
    return list(marks)


def _module_marker_names(request) -> set[str]:
    """Markers on this module plus its test classes (pytestmark)."""
    names = {mark.name for mark in request.node.iter_markers()}
    module = getattr(request.node, "obj", None)
    if module is None:
        return names
    for mark in _iter_pytestmarks(module):
        name = getattr(mark, "name", None)
        if name:
            names.add(name)
    for value in vars(module).values():
        if not isinstance(value, type):
            continue
        for mark in _iter_pytestmarks(value):
            name = getattr(mark, "name", None)
            if name:
                names.add(name)
    return names


def _usefixtures_names(request) -> set[str]:
    """Fixture names requested via usefixtures on the module or its classes."""
    names: set[str] = set()
    for mark in request.node.iter_markers("usefixtures"):
        names.update(str(arg) for arg in mark.args)
    module = getattr(request.node, "obj", None)
    if module is None:
        return names
    for mark in _iter_pytestmarks(module):
        if getattr(mark, "name", None) == "usefixtures":
            names.update(str(arg) for arg in getattr(mark, "args", ()))
    for value in vars(module).values():
        if not isinstance(value, type):
            continue
        for mark in _iter_pytestmarks(value):
            if getattr(mark, "name", None) == "usefixtures":
                names.update(str(arg) for arg in getattr(mark, "args", ()))
    return names


def module_owns_signing_precondition(request) -> bool:
    """True when this module owns APW + days + one Clear Cache.

    True if the test file defines ``precondition``, usefixtures a signing
    fixture, or still carries a legacy/two-step signing marker.
    """
    module = getattr(request.node, "obj", None)
    if module is not None and callable(getattr(module, "precondition", None)):
        return True
    marks = _module_marker_names(request)
    if marks & _SIGNING_MODULE_MARKERS:
        return True
    return bool(_usefixtures_names(request) & _SIGNING_FIXTURE_NAMES)


def scoped_rental_property_keys(request, app_config, environment) -> list[str]:
    """Property keys this module needs (Legacy and/or Two-Step only).

    Avoids configuring Hamilton + Rutland when the module is Legacy-only
    (or Two-Step-only). Mixed / unmarked modules still get both rental keys.
    """
    legacy_key = app_config.get(environment, "legacy_property", fallback="").strip()
    two_step_key = app_config.get(
        environment, "two_step_property", fallback=""
    ).strip()
    marks = _module_marker_names(request)
    fixtures = _usefixtures_names(request)
    want_legacy = bool(marks & _LEGACY_MARKERS) or bool(
        fixtures
        & {
            "legacy_clickwrap_signing",
            "legacy_superlease_signing",
            "legacy_traditional_signing",
        }
    )
    want_two_step = bool(marks & _TWO_STEP_MARKERS) or bool(
        fixtures & {"two_step_superlease_checked", "ensure_two_step_superlease"}
    )
    keys: list[str] = []
    if want_legacy and not want_two_step:
        if legacy_key:
            keys.append(legacy_key)
    elif want_two_step and not want_legacy:
        if two_step_key:
            keys.append(two_step_key)
    else:
        keys = rental_property_keys(app_config, environment)
    _log.info(
        "Scoped rental properties for %s: %s (markers=%s)",
        getattr(request.node, "name", environment),
        keys or "(none)",
        sorted(marks & (_LEGACY_MARKERS | _TWO_STEP_MARKERS))
        or sorted(fixtures & _SIGNING_FIXTURE_NAMES)
        or "unscoped",
    )
    return keys


@contextmanager
def legacy_signing_setup(hb_login_page, environment_config, app_config):
    """LeaseConfigurationSetup on an already-logged-in HB admin page.

    Targets ``legacy_property`` from config/properties/<env>.ini (not the
    two_step_property). Prefer the module ``hb_admin_session`` fixture so
    APW + signing share one window. Yields `LeaseConfigurationSetup`.
    """
    prop = environment_config.legacy_property
    yield LeaseConfigurationSetup(
        hb_login_page,
        environment_config,
        app_config,
        property_name=(
            prop.lease_configuration_property_name if prop else None
        ),
        fms_property_name=prop.fms_property_name if prop else None,
        hb_property_name=prop.hb_property_name if prop else None,
    )


def _flush_or_close_settings(signing, *, dirty: bool) -> None:
    if dirty:
        signing.flush_website_cache()
    else:
        signing.two_step_rental_page.nav.close_settings_panel()


def _legacy_property_keys(environment_config) -> list[str]:
    prop = environment_config.legacy_property
    return [prop.key] if prop and prop.key else []


def _ensure_legacy_signing(
    hb_login_page: HBLoginPage,
    environment_config,
    app_config,
    *,
    configure,
) -> None:
    """APW + Advance Days + signing toggles + one Clear Cache (legacy property)."""
    keys = _legacy_property_keys(environment_config)
    ensure_property_advanced_reservations(
        hb_login_page,
        environment_config,
        app_config,
        property_keys=keys,
    )
    days_dirty = ensure_advance_reservation_days(
        hb_login_page,
        environment_config,
        app_config,
        property_keys=keys,
        close_settings=False,
    )
    with legacy_signing_setup(
        hb_login_page, environment_config, app_config
    ) as signing:
        changed = configure(signing)
        _flush_or_close_settings(signing, dirty=changed or days_dirty)


def ensure_legacy_clickwrap(
    hb_login_page: HBLoginPage, environment_config, app_config
) -> None:
    """Once: APW + Advance Days + Clickwrap on + Clear Cache."""
    _ensure_legacy_signing(
        hb_login_page,
        environment_config,
        app_config,
        configure=lambda s: s.enable_clickwrap_with_super_lease_disabled(),
    )


def ensure_legacy_superlease(
    hb_login_page: HBLoginPage, environment_config, app_config
) -> None:
    """Once: APW + Advance Days + Super Lease on + Clear Cache."""
    _ensure_legacy_signing(
        hb_login_page,
        environment_config,
        app_config,
        configure=lambda s: s.enable_super_lease_and_clickwrap(),
    )


def ensure_legacy_traditional(
    hb_login_page: HBLoginPage, environment_config, app_config
) -> None:
    """Once: APW + Advance Days + Traditional signing + Clear Cache."""
    _ensure_legacy_signing(
        hb_login_page,
        environment_config,
        app_config,
        configure=lambda s: s.disable_clickwrap_and_super_lease(),
    )


def ensure_two_step_superlease(
    hb_login_page: HBLoginPage,
    environment_config,
    app_config,
    two_step_property=None,
) -> None:
    """Once: APW + Two-Step/Clickwrap/Super Lease + Advance Days + Clear Cache."""
    prop = two_step_property or environment_config.two_step_property
    if prop is None:
        raise ValueError(
            f"No two_step_property configured for {environment_config.name!r}"
        )
    ensure_property_advanced_reservations(
        hb_login_page,
        environment_config,
        app_config,
        property_keys=[prop.key],
    )
    signing = LeaseConfigurationSetup(
        hb_login_page,
        environment_config,
        app_config,
        property_name=prop.lease_configuration_property_name,
        fms_property_name=prop.fms_property_name,
        hb_property_name=prop.hb_property_name,
    )
    signing.enable_two_step_clickwrap_and_super_lease()
    days = prop.advance_reservation_days
    if days and days > 0:
        signing.set_advance_reservation_days(days)
    signing.flush_website_cache()


def ensure_property_advanced_reservations(
    hb_login_page: HBLoginPage,
    environment_config,
    app_config,
    *,
    property_keys: Iterable[str] | None = None,
) -> bool:
    """APW Advanced Reservations for the given property keys (or all).

    Returns True if at least one property was acted on.
    """
    if property_keys is not None:
        keys = list(dict.fromkeys(key for key in property_keys if key))
    else:
        keys = all_property_keys(app_config, environment_config.name)
        if not keys:
            keys = rental_property_keys(app_config, environment_config.name)
    if not keys:
        _log.info(
            "Skip APW Advanced Reservations ensure: no properties for %s",
            environment_config.name,
        )
        return False

    timeout = app_config.getint("browser", "timeout")
    # Dashboard shell required for #search-box (APW / property picker).
    # ensure_logged_in alone can leave /login?redirect=… if session dropped
    # (live 2026-09-22 clickwrap module precondition).
    hb_login_page.ensure_on_dashboard()
    page = hb_login_page.page
    quick_launch = HBQuickLaunchPage(page, timeout)
    scripts = HBLeadScriptsPage(
        page, timeout, HBSettingsNavigation(page, timeout)
    )
    acted = False
    for key in keys:
        prop = load_property(app_config, environment_config.name, key)
        lease_name = prop.lease_configuration_property_name
        settings_name = (
            prop.lead_management_property_settings_name or lease_name
        )
        hb_name = prop.hb_property_name or lease_name
        enabled = prop.apw_advance_reservation_enable
        if enabled is None or not settings_name or not hb_name:
            _log.info(
                "Skip APW Advanced Reservations for %s: "
                "apw_advance_reservation_enable / "
                "lease_configuration_property_name not fully configured",
                key,
            )
            continue
        desired = "ON" if enabled else "OFF"
        quick_launch.select_property(hb_name)
        ok = scripts.ensure_advanced_reservations_property_override(
            settings_name, enabled=enabled
        )
        _log.info(
            "APW Advanced Reservations for %s (%s): %s",
            key,
            settings_name,
            f"ensured {desired}" if ok else "panel/toggle not available",
        )
        acted = True
        scripts.nav._dismiss_blocking_dialog()
        page.goto(
            environment_config.hb_base_url.rstrip("/") + "/dashboard",
            wait_until="domcontentloaded",
        )
    if not acted:
        _log.info(
            "Skip APW Advanced Reservations ensure: no property configured "
            "with apw_advance_reservation_enable for %s",
            environment_config.name,
        )
    return acted


# Back-compat alias for older imports.
disable_property_advanced_reservations_overrides = (
    ensure_property_advanced_reservations
)


def ensure_advance_reservation_days(
    hb_login_page: HBLoginPage,
    environment_config,
    app_config,
    *,
    property_keys: Iterable[str] | None = None,
    close_settings: bool = True,
) -> bool:
    """FMS Advance Reservation Days for the given property keys (or all).

    Returns True if at least one property Save ran (value changed).
    When ``close_settings`` is True (default), closes Settings once when
    done. Signing fixtures pass False so they can keep configuring and
    Clear Cache once at the end of the module precondition.
    """
    if property_keys is not None:
        keys = list(dict.fromkeys(key for key in property_keys if key))
    else:
        keys = all_property_keys(app_config, environment_config.name)
        if not keys:
            keys = rental_property_keys(app_config, environment_config.name)
    if not keys:
        _log.info(
            "Skip Advance Reservation Days ensure: no properties for %s",
            environment_config.name,
        )
        return False

    saved = False
    last_nav = None
    for key in keys:
        prop = load_property(app_config, environment_config.name, key)
        days = prop.advance_reservation_days
        fms_name = prop.fms_property_name
        if days is None or days < 1 or not fms_name:
            _log.info(
                "Skip Advance Reservation Days for %s: "
                "advance_reservation_days / fms_property_name not set",
                key,
            )
            continue
        setup = LeaseConfigurationSetup(
            hb_login_page,
            environment_config,
            app_config,
            property_name=prop.lease_configuration_property_name,
            fms_property_name=fms_name,
            hb_property_name=prop.hb_property_name,
        )
        if setup.set_advance_reservation_days(days):
            saved = True
        last_nav = setup.two_step_rental_page.nav
        _log.info(
            "Advance Reservation Days for %s (%s): ensured %s",
            key,
            fms_name,
            days,
        )
    if close_settings and last_nav is not None:
        last_nav.close_settings_panel()
    if last_nav is None:
        _log.info(
            "Skip Advance Reservation Days ensure: no property configured "
            "with advance_reservation_days for %s",
            environment_config.name,
        )
    return saved


def ensure_scoped_rental_preconditions(
    request,
    hb_login_page: HBLoginPage,
    environment_config,
    app_config,
    *,
    close_settings: bool = True,
) -> bool:
    """APW Advanced Reservations + Advance Reservation Days for this module.

    Returns True if a days Save ran (caller should Clear Cache). Used by
    signing fixtures so one module test file gets one precondition package.
    """
    keys = scoped_rental_property_keys(
        request, app_config, environment_config.name
    )
    ensure_property_advanced_reservations(
        hb_login_page,
        environment_config,
        app_config,
        property_keys=keys,
    )
    return ensure_advance_reservation_days(
        hb_login_page,
        environment_config,
        app_config,
        property_keys=keys,
        close_settings=close_settings,
    )


def ensure_module_payment_gateways(
    hb_login_page: HBLoginPage,
    environment: str,
    environment_config,
    app_config,
    payment_gateways_ensure,
    gateway_profile: str | None,
    *,
    two_step: bool = False,
    ready: dict | None = None,
) -> None:
    """Ensure this file's payment gateways once (all methods in the profile).

    Tenant Payments → Credit Cards + ACH; non-tenant → Credit Cards only
    (whatever ``load_gateways`` lists for the profile). One Payment
    Processing visit for every method (not open/close per method).
    This is the only gateway ensure. Commenting it out in a module
    ``precondition`` skips Payment Processing for that file.
    """
    if not gateway_profile:
        return
    setting = "two_step_property" if two_step else "legacy_property"
    property_key = app_config.get(environment, setting, fallback="").strip()
    if not property_key:
        _log.info("Skip module payment gateways: no %s for %s", setting, environment)
        return
    methods = list(
        dict.fromkeys(
            gateway.method for gateway in load_gateways(app_config, gateway_profile)
        )
    )
    if not methods:
        _log.info(
            "Skip module payment gateways: no gateways in profile %s",
            gateway_profile,
        )
        return
    _log.info(
        "Module payment gateways once for %s / %s: %s",
        property_key,
        gateway_profile,
        methods,
    )
    # method=None → one Settings → Payment Processing pass for all methods.
    payment_gateways_ensure(
        property_key,
        gateway_profile,
        None,
        page=hb_login_page.page,
    )
    # Leave Settings so the shared tab can open Mariposa cleanly, then
    # return to HB dashboard for tenant validation without a stuck panel.
    timeout = app_config.getint("browser", "timeout")
    HBSettingsNavigation(hb_login_page.page, timeout).close_settings_panel()
    if ready is not None:
        ready["ready"] = True
