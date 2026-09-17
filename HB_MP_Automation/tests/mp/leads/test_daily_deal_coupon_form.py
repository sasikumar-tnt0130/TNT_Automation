import allure

from pages.mariposa.mp_daily_deal_page import MPDailyDealPage


@allure.title("The home page coupon opens the 'Send me the Daily Deal' form")
@allure.feature("MP Lead Management")
@allure.story("Coupon click")
def test_home_coupon_opens_daily_deal_form(page, environment_config, app_config) -> None:
    # The part of old Robot Lead_Management/CouponClick 14428 that can run
    # unattended: the home page coupon banner opens the Daily Deal form with
    # its fields. Submitting it (and every case that needs the resulting
    # coupon-click lead: 14428, 14366, 14361-14365, 14404) is blocked - the
    # form has a real reCAPTCHA (confirmed live 2026-09-14); user choice: ask
    # for Google's reCAPTCHA test keys / a QA bypass on the uat storefront.
    timeout = app_config.getint("browser", "timeout")
    daily_deal = MPDailyDealPage(page, environment_config.mp_base_url, timeout)

    coupon_title = daily_deal.open_home_daily_deal()
    with allure.step(f"The coupon banner has a title: {coupon_title!r}"):
        assert coupon_title, "The home page coupon banner has no title"
    daily_deal.assert_daily_deal_form()
    daily_deal.close_daily_deal()
