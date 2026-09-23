import allure

from common_utils.email_providers import is_test_inbox_email
from pages.common.hb_tenant_bulk_actions_page import HBTenantBulkActionsPage


@allure.title('Several tenants can be sent one bulk email; a bulk SMS reaches its review step')
@allure.feature("HB Smoke Test")
@allure.story("Email/Text multiple tenants")
def test_email_text_multiple_tenants(
    hb_login_page, app_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    lease_data = test_data("quick_launch_lease")
    bulk_actions = HBTenantBulkActionsPage(hb_login_page.page, timeout)
    bulk_actions.open_tenants(lease_data["property_name"])

    # Like the old Robot suite (which searched on ${lead_firstname} alone and
    # depended on its lease scenarios), this relies on tenants the HB lease
    # tests leave behind - they all share hb_lead_guest's first name.
    bulk_actions.search_tenants(hb_lead_guest["first_name"])
    selected = bulk_actions.select_all_tenants()
    assert selected >= 2, (
        f"Need at least 2 '{hb_lead_guest['first_name']}' tenants to bulk-message, "
        f"found {selected} - run one of the HB lease tests first"
    )

    # SMS is walked up to its review step and never sent: tenants created
    # before hb_lead_guest switched to fictional 555-01xx numbers still have
    # random 707-719-xxxx ones, which could reach real people.
    bulk_actions.start_communication("Send SMS")
    bulk_actions.compose_sms("Automation smoke test - this SMS is never sent.")
    sms_recipients, _ = bulk_actions.review_recipients()
    assert sms_recipients == selected
    bulk_actions.close_bulk_actions()

    # Email really is sent - but only once every recipient is confirmed to be
    # the Gmail test inbox.
    selected = bulk_actions.select_all_tenants()
    bulk_actions.start_communication("Send Email")
    bulk_actions.compose_email(
        "Automation smoke test - bulk email",
        "Automated bulk email from the HB smoke test suite.",
    )
    email_recipients, emails = bulk_actions.review_recipients()
    assert email_recipients == selected
    assert emails and all(is_test_inbox_email(email) for email in emails), (
        f"Refusing to send: not every recipient is a test inbox: {emails}"
    )
    bulk_actions.confirm_and_send()
