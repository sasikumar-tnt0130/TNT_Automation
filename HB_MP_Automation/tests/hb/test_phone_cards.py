import uuid

import allure

from pages.common.hb_phone_cards_page import HBPhoneCardsPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

# Old Robot Unified_Communications/Phone_uiupdate. The tenant is created for the
# session (hb_comm_tenants, tests/hb/conftest.py); logging a call sends nothing
# to anyone.
# Not migrated (user choice 2026-09-14): 14300 (call playback and call back),
# 14297 (property and source on the card), 14303 (voicemail) and 14301 (missed
# call) - they need calls through HB's Charm phone integration, and
# uat_storoutlet has no Charm-enabled property (Bakersfield x2, Bellflower,
# Chino, Chula Vista, Fullerton, Gardena; Robot used "Port Royal - Charm
# enabled"). Recordings, voicemails and missed calls only come from real calls.


@allure.title("Logged incoming and outgoing calls show their label and icon, and filter by direction")
@allure.feature("HB Unified Communications")
@allure.story("Phone UI")
def test_logged_call_cards(hb_login_page, app_config, hb_comm_tenants) -> None:
    # 14298 (Call (In) and Call (Out) with their icons), plus the Phone type
    # filter and the Incoming/Outgoing filter (user choice 2026-09-14).
    tenant = hb_comm_tenants["single"]
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    cards = HBPhoneCardsPage(hb_login_page.page, app_config.getint("browser", "timeout"))
    cards.close_restored_drawers(wait_seconds=5)
    # One property, checked on the dashboard header - see
    # test_communication_compose._select_property.
    HBQuickLaunchPage(cards.page, cards.timeout).select_property(hb_comm_tenants["property_name"])
    run = f"qa-{uuid.uuid4().hex[:8]}-k"
    notes = {
        "Incoming": f"QA automation incoming call {run}-in",
        "Outgoing": f"QA automation outgoing call {run}-out",
    }

    cards.open_in_communication_center(tenant["name"])
    cards.log_phone_call(notes["Incoming"], direction="Incoming")
    # The direction filter picks contacts by their latest message, so each call
    # is checked there as it's logged (user choice 2026-09-14) - under Outgoing
    # only the listing, as a same-minute pair can show "Call (In)".
    cards.assert_left_call(tenant["name"], "Incoming")
    cards.reopen_center(tenant["name"])
    cards.log_phone_call(notes["Outgoing"], direction="Outgoing")
    cards.assert_left_call(tenant["name"], "Outgoing", check_label=False)

    # The cards, checked on a fresh load as the other card tests do.
    cards.reopen_center(tenant["name"])
    cards.assert_call_card(f"{run}-in", "Incoming", notes["Incoming"])
    cards.assert_call_card(f"{run}-out", "Outgoing", notes["Outgoing"])

    with allure.step("The Phone filter lists both calls, and only calls"):
        cards.choose("All Communications", "Phone")
        listed = cards.card_chevrons("Call")
        assert listed and all(kind == "Call" for kind, _ in listed), listed
        cards.expect_notes(visible=[f"{run}-in", f"{run}-out"], hidden=[])
        cards.choose("Phone", "All Communications")

