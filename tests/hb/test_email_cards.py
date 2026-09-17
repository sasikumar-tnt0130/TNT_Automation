import uuid
from pathlib import Path

import allure
import pytest

from common_utils.mailinator_utils import get_email_plain_text, wait_for_email
from pages.common.hb_email_cards_page import HBEmailCardsPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

# Old Robot Unified_Communications/Email_uiupdate. The tenant and its Alternate
# contact are created for the session (hb_comm_tenants, tests/hb/conftest.py);
# emails go only to their Mailinator inboxes (HBCommunicationComposePage
# refuses anything else). Robot's own contacts (Outlook addresses, a +91
# phone) are never used.
# Not migrated (user choices 2026-09-14):
# - 14164 for Emergency, Lien Holder and Authorized Access: the tenant has an
#   Alternate contact only; Alternate is checked below.
# - 14175 (Reply button), 14806 (reply to an incoming email), 14807
#   (threading): the only incoming emails on the property are other people's,
#   and Mailinator can't send one in.
# - 14180 (bounced): no bounced email found - a Communication Center search
#   for "Bounced" lists nothing (2026-09-14).
ATTACHMENT = Path(__file__).resolve().parents[2] / "config" / "test_data" / "test_upload.txt"


def _setup(hb_login_page, app_config, property_name: str) -> HBEmailCardsPage:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    cards = HBEmailCardsPage(hb_login_page.page, app_config.getint("browser", "timeout"))
    cards.close_restored_drawers(wait_seconds=5)
    # One property, checked on the dashboard header - see
    # test_communication_compose._select_property.
    HBQuickLaunchPage(cards.page, cards.timeout).select_property(property_name)
    return cards


def _expect_email(address: str, token: str) -> dict:
    with allure.step(f"The email {token} reached {address}"):
        message = wait_for_email(address, subject_contains=token, timeout=180)
        assert token in get_email_plain_text(message), message.get("subject")
        return message


@allure.title("Email cards: primary and alternate contact, time and status, space and subject, pin, left card")
@allure.feature("HB Unified Communications")
@allure.story("Email UI")
def test_email_cards_in_communication_center(hb_login_page, app_config, hb_comm_tenants) -> None:
    # 14164 (Alternate), 14167, 14168, 14169, 14178, 14172, 14177, 14179.
    tenant, alternate = hb_comm_tenants["single"], hb_comm_tenants["alternate"]
    cards = _setup(hb_login_page, app_config, hb_comm_tenants["property_name"])
    run = f"qa-{uuid.uuid4().hex[:8]}-u"
    subject = f"QA automation email {run}"

    cards.open_in_communication_center(tenant["name"])
    recipients = cards.send_email(
        subject, f"QA automation email body {run}", also_to=alternate["email"], space=tenant["space"]
    )
    assert any(
        alternate["email"] in recipient and f"({alternate['designation']})" in recipient
        for recipient in recipients
    ), recipients
    cards.assert_primary_email_card(run, subject, tenant["space"])
    cards.assert_alternate_email_card(run, subject, tenant["space"], alternate)

    pinned = False
    try:
        with allure.step("14172: a pinned email is listed on top"):
            cards.pin_card(run, "email", True)
            pinned = True
            cards.reopen_center(tenant["name"])
            cards.assert_card_pinned(run, "email", True)
        cards.assert_left_card(run, tenant["name"], tenant["status"])
        with allure.step("14172: the email can be unpinned"):
            cards.pin_card(run, "email", False)
            pinned = False
            cards.reopen_center(tenant["name"])
            cards.assert_card_pinned(run, "email", False)
    finally:
        if pinned:
            with allure.step("Unpin this run's email"):
                cards.reopen_center(tenant["name"])
                cards.pin_card(run, "email", False)

    _expect_email(tenant["email"], run)
    _expect_email(alternate["email"], run)


@allure.title("An email with an attachment shows the attachment icon")
@allure.feature("HB Unified Communications")
@allure.story("Email UI")
def test_email_attachment_icon(hb_login_page, app_config, hb_comm_tenants) -> None:
    # 14174: attached with paperclip -> Upload.
    tenant = hb_comm_tenants["single"]
    cards = _setup(hb_login_page, app_config, hb_comm_tenants["property_name"])
    run = f"qa-{uuid.uuid4().hex[:8]}-f"

    cards.open_in_communication_center(tenant["name"])
    cards.send_email(
        f"QA automation email {run}", f"QA automation email body {run}",
        attachment=str(ATTACHMENT), space=tenant["space"],
    )
    cards.assert_attachment_icon(run)
    message = _expect_email(tenant["email"], run)
    # Mailinator's public inbox strips attachments: the file's name isn't kept,
    # only a multipart/mixed email with an "attachment removed" part (seen
    # 2026-09-14).
    with allure.step("The email arrived with an attachment (stripped by Mailinator)"):
        content_type = message.get("headers", {}).get("content-type", "")
        assert content_type.startswith("multipart/mixed"), content_type
        bodies = [" ".join(part.get("body", "").split()) for part in message.get("parts", [])]
        assert "attachment removed" in bodies, f"No stripped attachment part: {[body[:40] for body in bodies]}"


@allure.title("Incoming and outgoing email icons in the Communication Center")
@allure.feature("HB Unified Communications")
@allure.story("Email UI")
def test_incoming_outgoing_email_icons(hb_login_page, app_config, test_data) -> None:
    # 14176. Read-only: the list is only filtered and read - the incoming
    # emails are other people's, so none is opened. Needs no tenant of its
    # own, only the property the session tenants live on.
    property_name = test_data("quick_launch_lease").get("property_name")
    if not property_name:
        pytest.skip("No Quick Launch lease property configured for this environment")
    cards = _setup(hb_login_page, app_config, property_name)

    cards.open_center()
    try:
        cards.filter_direction("Incoming")
        with allure.step("Incoming: only (In) items; incoming emails carry the receive icon"):
            emails = [item for item in cards.left_list_items("In", kind="Email") if item["kind"] == "Email"]
            assert emails, "No incoming email is listed"
            assert all("mdi-email-receive" in item["icons"] for item in emails), emails
        cards.clear_direction_filter()

        cards.filter_direction("Outgoing")
        with allure.step("Outgoing: only (Out) items; outgoing emails carry the send icon"):
            emails = [item for item in cards.left_list_items("Out", kind="Email") if item["kind"] == "Email"]
            assert emails, "No outgoing email is listed"
            assert all(
                "mdi-email-send-outline" in item["icons"] and "mdi-email-receive" not in item["icons"]
                for item in emails
            ), emails
    finally:
        cards.clear_direction_filter()
