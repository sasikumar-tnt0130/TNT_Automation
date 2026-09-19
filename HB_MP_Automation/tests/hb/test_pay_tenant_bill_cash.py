import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from common_utils.lease_configuration_setup import LeaseConfigurationSetup
from config.config_reader import load_property
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@allure.title('A tenant bill can be paid with cash')
@allure.feature("HB Smoke Test")
@allure.story("Pay a tenant bill with cash")
def test_pay_tenant_bill_with_cash(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    lease_data = test_data("quick_launch_lease")

    # This environment now tracks two named properties (see
    # environments.ini's [stage.hamilton_garden_grove] - the environment's
    # default, Legacy/Traditional Signing - and [stage.lightning_rutland]
    # - Two-Step) rather than one single stage property. Whichever
    # property lease_data["property_name"] (or HB_PROPERTY_OVERRIDE)
    # actually targets for the Quick Launch flow below, look up its own
    # named config explicitly here instead of assuming it matches
    # environment_config's default - sign_documents_on_this_device only
    # handles Traditional Signing, so Two-Step/Clickwrap/Super Lease get
    # force-disabled on whichever property this run uses. No rental_page:
    # that optional storefront cross-check has its own flakiness
    # (confirmed live - a stuck tier-selection dialog on a specific unit)
    # unrelated to what this test verifies; the admin-side assertions
    # inside disable_two_step_clickwrap_and_super_lease already confirm
    # the setting took effect.
    # Only environments that declare that property need this - confirmed
    # live (2026-09-11, uat_storoutlet/Bellflower) that lease signing works
    # there as configured (Superlease, "I Agree"), and that environment has
    # no [uat_storoutlet.lightning_rutland] section for load_property to
    # read (it raised ValueError there before this guard).
    if app_config.has_section(f"{environment_config.name}.lightning_rutland"):
        rutland = load_property(
            app_config, environment_config.name, "lightning_rutland"
        )
        LeaseConfigurationSetup(
            hb_login_page,
            environment_config,
            app_config,
            property_name=rutland.lease_configuration_property_name,
            fms_property_name=rutland.fms_property_name,
        ).disable_two_step_clickwrap_and_super_lease()
        # HB cash-pay path does not need storefront Clear Cache; settings
        # are only forced off so Quick Launch Traditional Signing works.

        # Confirmed live: the Settings/FMS panel used above doesn't close its
        # own dialog afterward - its leftover overlay intercepts clicks on
        # the Quick Launch dashboard's #search-box. open_login_page() forces
        # a fresh navigation (redirects straight to /dashboard since this
        # context is already authenticated), discarding that dialog state.
        hb_login_page.open_login_page()

    create_lease_through_quick_action(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
        environment_config,
        lease_data,
        hb_lead_guest,
    )

    quick_launch = HBQuickLaunchPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    quick_launch.open_take_payment_for_property(lease_data["property_name"])
    quick_launch.search_and_select_tenant_for_payment(hb_lead_guest["last_name"])
    quick_launch.ensure_payable_balance()
    quick_launch.pay_by_cash()
    quick_launch.assert_payment_receipt("Cash")
    quick_launch.finish_and_close()
