import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action


@allure.title('A new lead can be moved in and finalized into a lease via Quick Launch')
@allure.feature("HB Smoke Test")
@allure.story("From Quick action Create a lease")
def test_create_lease_through_quick_action(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    lease_data = test_data("quick_launch_lease")
    create_lease_through_quick_action(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
        environment_config,
        lease_data,
        hb_lead_guest,
    )
