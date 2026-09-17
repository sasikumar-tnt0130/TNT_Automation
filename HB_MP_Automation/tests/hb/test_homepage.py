import allure

from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.mariposa.mp_website_homepage_page import MPWebsiteHomepagePage


@allure.title('Homepage descriptions are populated')
@allure.feature("HB Website Homepage")
@allure.story("Homepage descriptions are populated")
def test_homepage_descriptions_are_populated(hb_login_page, app_config) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    nav = HBSettingsNavigation(hb_login_page.page, timeout)
    homepage = MPWebsiteHomepagePage(hb_login_page.page, timeout, nav)
    homepage.open_homepage_settings()
    homepage.assert_descriptions_are_populated()
