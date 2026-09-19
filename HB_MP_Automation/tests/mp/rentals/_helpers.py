"""Shared helpers for tests/mp/rentals/conftest.py (not pytest fixtures)."""

from contextlib import contextmanager
import logging

from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from config.config_reader import list_properties, load_property
from pages.common.hb_lead_scripts_page import HBLeadScriptsPage
from pages.common.hb_login_page import HBLoginPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage
from common_utils.browser_sessions import browser_permissions

_log = logging.getLogger("hb_mp.rentals")


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


def ensure_property_advanced_reservations(
    hb_login_page: HBLoginPage, environment_config, app_config
) -> None:
    """APW Advanced Reservations for every property in config/properties/<env>.ini.

    Uses the caller's logged-in HB page (module ``hb_admin_session``).
    For each property with apw_advance_reservation_enable set (true/false),
    select via lease_configuration_property_name (contains-match) and force
    the Property Settings toggle. Missing UI panel → log and continue.
    """
    keys = all_property_keys(app_config, environment_config.name)
    if not keys:
        # Fall back to legacy/two_step when `properties=` is empty.
        keys = rental_property_keys(app_config, environment_config.name)
    if not keys:
        _log.info(
            "Skip APW Advanced Reservations ensure: no properties for %s",
            environment_config.name,
        )
        return

    timeout = app_config.getint("browser", "timeout")
    hb_login_page.ensure_logged_in()
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


# Back-compat alias for older imports.
disable_property_advanced_reservations_overrides = (
    ensure_property_advanced_reservations
)
