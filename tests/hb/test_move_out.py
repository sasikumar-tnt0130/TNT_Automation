import allure

from pages.common.hb_move_out_page import HBMoveOutPage


@allure.title('All filtered spaces can be moved out')
@allure.feature("HB Tenant Management")
@allure.story("Move out all filtered spaces")
def test_all_filtered_spaces_can_be_moved_out(
    hb_login_page, app_config, test_data
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    move_out_data = test_data("move_out")
    move_out = HBMoveOutPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    move_out.move_out_all_spaces(
        move_out_data["property_name"],
        move_out_data["active_tenant_filter"],
        move_out_data["reason"],
        move_out_data.get("custom_range_start_date"),
        move_out_data.get("custom_range_end_date"),
    )
