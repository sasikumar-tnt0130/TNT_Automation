import re
import uuid

import allure
import pytest

from pages.common.hb_email_cards_page import HBEmailCardsPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

# Old Robot Unified_Communications/Sms_uiupdate. The tenant is created for the
# session (hb_comm_tenants, tests/hb/conftest.py); texts go only to its
# fictional (707) 555-01xx number (HBCommunicationComposePage refuses anything
# else).
# Not migrated: 14808 (reply to an incoming text) and 14188 (Reply button) -
# the only incoming texts on the property are other people's, and replying
# would text a real person.


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


@allure.title("Text cards: time, space and message, pin, expanded long text, left card and status")
@allure.feature("HB Unified Communications")
@allure.story("Text UI")
def test_text_cards_in_communication_center(hb_login_page, app_config, hb_comm_tenants) -> None:
    # 14183, 14191, 14186 (pin and unpin - user choice 2026-09-14), 14187,
    # 14190, 14192.
    tenant = hb_comm_tenants["single"]
    cards = _setup(hb_login_page, app_config, hb_comm_tenants["property_name"])
    run = f"qa-{uuid.uuid4().hex[:8]}-s"
    # About 850 characters: HB shows the collapse icon (14187) only when the
    # text runs past its collapsed box, and 250 characters still fit on one
    # line at 1920x1080 (2026-09-14).
    message = (
        f"QA automation text {run}. "
        + "This long automated test message checks that a text running past two lines is shown "
        "expanded in the Communication Center, with a collapse icon, its space number, the "
        "time it was sent and its pin icon. " * 4
        + "No reply is needed."
    )

    cards.open_in_communication_center(tenant["name"])
    recipients = cards.send_text(message, space=tenant["space"])
    assert any(tenant["phone_number"] in re.sub(r"\D", "", recipient) for recipient in recipients), recipients
    # Checked on a fresh load: the card drawn straight after its own send
    # stays collapsed, while a reload shows a long text expanded (2026-09-14).
    cards.reopen_center(tenant["name"])
    cards.assert_text_card(run, message, tenant["space"])
    cards.assert_text_collapses(run)

    pinned = False
    try:
        with allure.step("14186: a pinned text is listed on top"):
            cards.pin_card(run, "text", True)
            pinned = True
            cards.reopen_center(tenant["name"])
            cards.assert_card_pinned(run, "text", True)
        cards.assert_left_card(run, tenant["name"], tenant["status"], kind="text")
        with allure.step("14186: the text can be unpinned"):
            cards.pin_card(run, "text", False)
            pinned = False
            cards.reopen_center(tenant["name"])
            cards.assert_card_pinned(run, "text", False)
    finally:
        if pinned:
            with allure.step("Unpin this run's text"):
                cards.reopen_center(tenant["name"])
                cards.pin_card(run, "text", False)


@allure.title("Incoming and outgoing text labels and icons in the Communication Center")
@allure.feature("HB Unified Communications")
@allure.story("Text UI")
def test_incoming_outgoing_text_icons(hb_login_page, app_config, test_data) -> None:
    # 14181. Read-only: the list is only filtered and read - the incoming
    # texts are other people's, so none is opened. Needs no tenant of its own,
    # only the property the session tenants live on.
    property_name = test_data("quick_launch_lease").get("property_name")
    if not property_name:
        pytest.skip("No Quick Launch lease property configured for this environment")
    cards = _setup(hb_login_page, app_config, property_name)

    cards.open_center()
    try:
        cards.filter_direction("Incoming")
        with allure.step("Incoming: only (In) items; incoming texts read Text (In) with the incoming icon"):
            texts = [item for item in cards.left_list_items("In", kind="Text") if item["kind"] == "Text"]
            assert texts, "No incoming text is listed"
            assert all("mdi-message-arrow-left" in item["icons"] for item in texts), texts
        cards.clear_direction_filter()

        cards.filter_direction("Outgoing")
        with allure.step("Outgoing: only (Out) items; outgoing texts read Text (Out) with the outgoing icon"):
            texts = [item for item in cards.left_list_items("Out", kind="Text") if item["kind"] == "Text"]
            assert texts, "No outgoing text is listed"
            assert all(
                "mdi-message-arrow-right-outline" in item["icons"] and "mdi-message-arrow-left" not in item["icons"]
                for item in texts
            ), texts
    finally:
        cards.clear_direction_filter()
