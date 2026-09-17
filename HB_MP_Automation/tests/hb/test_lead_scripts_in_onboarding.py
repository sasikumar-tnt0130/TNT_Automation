import uuid

import allure

from pages.common.hb_lead_scripts_page import HBLeadScriptsPage
from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.common.hb_spaces_page import HBSpacesPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


def _new_contact_email() -> str:
    return f"qa-script-{uuid.uuid4().hex[:10]}@mailinator.com"


@allure.title("A property script shows in Tenant Onboarding, shows its changes, and goes when cleared")
@allure.feature("HB Lead Management")
@allure.story("Ability to add scripts")
def test_property_script_shows_in_onboarding_and_clears(
    hb_login_page, app_config, environment_config, test_data
) -> None:
    # Old Robot Lead_Management/AbilityToAddScripts, the cases that save a
    # script: 15172 (the script shows in the lead flow), 15173 (a changed
    # script shows - user choice 2026-09-14), 16455 (from Spaces), 16454 (only
    # for its own property), 16451 and 15170/15175. This changes a shared
    # property setting, so the script is cleared again in finally.
    #
    # Changed from Robot, confirmed live 2026-09-14 (uat_storoutlet):
    # - 16451 expected Quick Launch's Create New Contact to show no script;
    #   it shows it now.
    # - 15170/15175 expected no script section once cleared; HB keeps an
    #   empty script record, so the heading stays with an empty box.
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    data = test_data("lead_scripts")
    page = hb_login_page.page
    dashboard_url = environment_config.hb_base_url.rstrip("/") + "/dashboard"
    script_lines = [
        f"QA automation lead script {uuid.uuid4().hex[:8]}.",
        "Please confirm the customer name and storage need.",
    ]
    changed_lines = [
        f"QA automation lead script {uuid.uuid4().hex[:8]} - changed.",
        "Please confirm the move-in date as well.",
    ]

    scripts = HBLeadScriptsPage(page, timeout, HBSettingsNavigation(page, timeout))
    quick_launch = HBQuickLaunchPage(page, timeout)

    def open_dashboard() -> None:
        page.goto(dashboard_url, wait_until="domcontentloaded")
        scripts.close_restored_onboarding()

    def open_property_script() -> None:
        # Settings only offers the dashboard's property, so select it first.
        open_dashboard()
        quick_launch.select_property(data["script_property"])
        scripts.open_property_script(data["script_property_settings_name"])

    open_property_script()
    # From the saved script itself, not the editor - which reads "" until
    # the script has loaded.
    assert not scripts.saved_script, (
        f"{data['script_property_settings_name']} already has a property script "
        f"({scripts.saved_script!r}) - not overwriting it"
    )

    try:
        scripts.write_script(script_lines)

        open_dashboard()
        quick_launch.open_quick_launch_for_property(data["script_property"])
        quick_launch.start_new_contact(_new_contact_email())
        scripts.assert_onboarding_script(script_lines)
        scripts.close_onboarding()

        spaces = HBSpacesPage(page, timeout)
        spaces.open_spaces()
        spaces.start_lead_from_available_space()
        scripts.assert_onboarding_script(script_lines)
        scripts.close_onboarding()

        open_dashboard()
        quick_launch.open_quick_launch_for_property(data["other_property"])
        quick_launch.start_new_contact(_new_contact_email())
        scripts.assert_no_onboarding_script()
        scripts.close_onboarding()

        with allure.step("15173: the changed script shows in the lead flow"):
            open_property_script()
            scripts.write_script(changed_lines)
            open_dashboard()
            quick_launch.open_quick_launch_for_property(data["script_property"])
            quick_launch.start_new_contact(_new_contact_email())
            scripts.assert_onboarding_script(changed_lines)
            scripts.close_onboarding()
    finally:
        with allure.step("Restore: clear the property script"):
            open_property_script()
            scripts.clear_script()

    with allure.step("The cleared script stays empty after a reload"):
        open_property_script()
        assert scripts.saved_script == "", (
            f"Saved script is {scripts.saved_script!r} after clearing"
        )
        assert scripts.read_script() == ""

    open_dashboard()
    quick_launch.open_quick_launch_for_property(data["script_property"])
    quick_launch.start_new_contact(_new_contact_email())
    scripts.assert_onboarding_script_empty()
    scripts.close_onboarding()
