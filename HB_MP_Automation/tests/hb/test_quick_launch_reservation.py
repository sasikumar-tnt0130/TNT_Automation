import allure

from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@allure.title('A new lead can be created and a space reserved via Quick Launch')
@allure.feature("HB Smoke Test")
@allure.story("Create Reservation - Through Quick Action")
def test_create_reservation_through_quick_action(
    hb_login_page, app_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    quick_launch_data = test_data("quick_launch_reservation")
    quick_launch = HBQuickLaunchPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    quick_launch.open_quick_launch_for_property(
        quick_launch_data["property_name"]
    )
    quick_launch.start_new_contact(hb_lead_guest["email"])
    quick_launch.fill_lead_details(
        hb_lead_guest["first_name"],
        hb_lead_guest["last_name"],
        hb_lead_guest["email"],
        hb_lead_guest["phone_number"],
        quick_launch_data["lead_initiated"],
        quick_launch_data["lead_source"],
    )
    quick_launch.reserve_first_available_space()
    quick_launch.assert_reservation_active(
        hb_lead_guest["first_name"], hb_lead_guest["last_name"]
    )
