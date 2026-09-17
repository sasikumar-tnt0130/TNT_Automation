import allure

from pages.common.hb_lead_management_page import HBLeadManagementPage


@allure.title('All reservations can be cancelled')
@allure.feature("HB Lead Management")
@allure.story("Cancel all reservations")
def test_all_reservations_can_be_cancelled(
    hb_login_page, app_config, test_data
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    cancel_reservation_data = test_data("cancel_reservation")
    lead_management = HBLeadManagementPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    lead_management.cancel_all_reservations(
        cancel_reservation_data["property_name"],
        cancel_reservation_data["notes"],
    )
