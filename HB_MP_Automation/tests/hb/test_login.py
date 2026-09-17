import allure


@allure.title('Hb user can login')
@allure.feature("HB Authentication")
@allure.story("Successful HB login")
def test_hb_user_can_login(hb_login_page) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()