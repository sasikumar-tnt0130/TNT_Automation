import allure
import pytest

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage


@pytest.mark.skip(
    reason=(
        "Blocked by the sandbox, not the page object: uat_storoutlet/"
        "Bellflower's card form reports 'Tenant Payments form is missing an "
        "API key' (card gateway not configured there), so no card payment "
        "can be taken. Cash and ACH work on the same property (walked live "
        "2026-09-13). Unskip once Bellflower's card gateway is configured or "
        "on a property whose HB card gateway works - and confirm the "
        "receipt's card label then, it has never been seen live."
    )
)
@allure.title('A tenant bill can be paid with a credit/debit card')
@allure.feature("HB Smoke Test")
@allure.story("Pay a tenant bill with credit/debit card")
def test_pay_tenant_bill_with_card(
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

    quick_launch = HBQuickLaunchPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    quick_launch.open_take_payment_for_property(lease_data["property_name"])
    quick_launch.search_and_select_tenant_for_payment(hb_lead_guest["last_name"])
    quick_launch.ensure_payable_balance()
    card_expiry_month, card_expiry_year = environment_config.card_expiry.split("/")
    quick_launch.pay_by_credit_card(
        environment_config.card_number,
        environment_config.card_cvc,
        card_expiry_month,
        card_expiry_year,
        environment_config.card_zip_code,
    )
    # Receipt label text not yet live-verified (blocked, see skip reason
    # above) - "Credit/Debit" matches the known-verified payment-method
    # selection button; confirm the actual receipt wording before unskipping.
    quick_launch.assert_payment_receipt("Credit/Debit")
    quick_launch.finish_and_close()
