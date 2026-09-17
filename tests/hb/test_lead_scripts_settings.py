import uuid

import allure

from pages.common.hb_lead_scripts_page import HBLeadScriptsPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

# Confirmed live 2026-09-14 (uat_storoutlet). The Property Settings tab's
# panels vary by property (Bellflower adds its own "Advanced Reservations and
# Rentals"), so only The Script is checked there.
CORPORATE_PANELS = [
    "Lead Questionnaire",
    "The Script",
    "Reservation Settings",
    "Advanced Reservations and Rentals",
    "Lead Expiration",
    "Offline Spaces",
]


def _login(hb_login_page) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()


@allure.title("Lead Management settings show The Script for the selected property")
@allure.feature("HB Lead Management")
@allure.story("Ability to add scripts")
def test_lead_management_script_settings(
    hb_login_page, app_config, environment_config, test_data
) -> None:
    # Old Robot Lead_Management/AbilityToAddScripts 15167 (Lead Management is
    # in Settings), 15168 (its landing page), 16449 (the property tab only
    # works once a property is selected) and 15169 (The Script can be
    # added/modified). Read-only: nothing is saved.
    _login(hb_login_page)
    timeout = app_config.getint("browser", "timeout")
    data = test_data("lead_scripts")
    page = hb_login_page.page

    scripts = HBLeadScriptsPage(page, timeout, HBSettingsNavigation(page, timeout))
    scripts.open_lead_management()
    scripts.assert_landing_page()
    with allure.step("Corporate Settings panels"):
        scripts.wait_for_panel_titles(CORPORATE_PANELS)

    # Straight after login no dashboard property is picked yet.
    scripts.open_tab("Property Settings")
    scripts.assert_property_prompt()

    page.goto(
        environment_config.hb_base_url.rstrip("/") + "/dashboard", wait_until="domcontentloaded"
    )
    HBQuickLaunchPage(page, timeout).select_property(data["script_property"])
    scripts.open_property_script(data["script_property_settings_name"])
    scripts.assert_script_controls_enabled()


@allure.title("A property with no script shows no script in Tenant Onboarding")
@allure.feature("HB Lead Management")
@allure.story("Ability to add scripts")
def test_no_script_section_without_a_property_script(hb_login_page, app_config, test_data) -> None:
    # Old Robot 16454 ("displayed only for the selected property"), the
    # read-only half: a property that has never had a script shows no
    # script section at all. The write test checks the same property while
    # another one has a script.
    _login(hb_login_page)
    timeout = app_config.getint("browser", "timeout")
    data = test_data("lead_scripts")
    page = hb_login_page.page

    quick_launch = HBQuickLaunchPage(page, timeout)
    quick_launch.open_quick_launch_for_property(data["other_property"])
    quick_launch.start_new_contact(f"qa-script-{uuid.uuid4().hex[:10]}@mailinator.com")
    scripts = HBLeadScriptsPage(page, timeout, HBSettingsNavigation(page, timeout))
    scripts.assert_no_onboarding_script()
    scripts.close_onboarding()
