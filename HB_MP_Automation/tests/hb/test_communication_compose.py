import re
import uuid

import allure
import pytest
from playwright.sync_api import expect

from common_utils.mailinator_utils import get_email_plain_text, wait_for_email
from pages.common.hb_communication_compose_page import CARD_KINDS, SENT_TODAY, HBCommunicationComposePage
from pages.common.hb_lead_management_page import HBLeadManagementPage
from pages.common.hb_leads_grid_page import HBLeadsGridPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage
from pages.hummingbird.hb_quick_launch_page import HBQuickLaunchPage

# Old Robot Unified_Communications/Communications_test. The tenants are created
# for the session (hb_comm_tenants / hb_two_space_tenant, tests/hb/conftest.py).
# Emails go only to Mailinator test inboxes and texts only to fictional
# (707)/(714) 555-01xx numbers - HBCommunicationComposePage refuses anything
# else (user choices 2026-09-14). Robot's own alternate contact (an Outlook
# address and a +91 mobile) is never used.
# Not migrated:
# - 14802/14803: a new contact's onboarding drawer has no communication icon.
# - 14804: it opens other people's Collection Call tasks.
# - 14299: pinning is covered by test_tenant_notes_add_pin_filter; the sends
#   below check each new card is dated "Today, h:mm".


def _login(hb_login_page, app_config) -> HBCommunicationComposePage:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    compose = HBCommunicationComposePage(hb_login_page.page, app_config.getint("browser", "timeout"))
    compose.close_restored_drawers(wait_seconds=5)
    return compose


def _select_property(compose: HBCommunicationComposePage, property_name: str) -> None:
    # One property, checked on the dashboard header: a run found the picker on
    # "Company (7 Properties Selected)", where the communication type filter
    # showed "Email" but the list kept every note (2026-09-14).
    HBQuickLaunchPage(compose.page, compose.timeout).select_property(property_name)


def _open_tenant(compose: HBCommunicationComposePage, property_name: str, tenant: dict) -> None:
    _select_property(compose, property_name)
    HBTenantSpacesPage(compose.page, compose.timeout).open_tenants(property_name)
    compose.open_tenant(tenant["name"])
    compose.reset_filters(tenant["spaces"])


def _send_everything(compose: HBCommunicationComposePage, run: str, space: str | None) -> list[str]:
    """An email, a text, a phone log and a note, each checked on its card.
    Returns the email's recipients."""
    recipients = compose.send_email(
        f"QA automation email {run}-e", f"QA automation email body {run}-e", space=space
    )
    compose.expect_sent_card(f"{run}-e", "email", space)
    compose.send_text(f"QA automation text {run}-t", space)
    compose.expect_sent_card(f"{run}-t", "text", space)
    compose.log_phone_call(f"QA automation phone log {run}-c")
    compose.expect_sent_card(f"{run}-c", "call")
    compose.add_plain_note(f"QA automation note {run}-n")
    compose.expect_sent_card(f"{run}-n", "note")
    return recipients


def _expect_email(address: str, token: str) -> None:
    with allure.step(f"The email {token} reached {address}"):
        message = wait_for_email(address, subject_contains=token, timeout=180)
        assert token in get_email_plain_text(message), message.get("subject")


def _expect_alternate_text_card(compose: HBCommunicationComposePage, token: str, name: str, space: str) -> None:
    """The one card carrying `token` is a text to the Alternate `name`, dated
    today, for `space`. The card's Alternate marker is expected to read like
    the email's "Email (Out)-Alternate ... To: <name>"."""
    with allure.step(f"Text {token}: to the Alternate {name}, today, space {space}"):
        cards = compose._cards().filter(has_text=token)
        expect(cards).to_have_count(1, timeout=compose.timeout)
        card = cards.first
        expect(card).to_contain_text(CARD_KINDS["text"])
        expect(card).to_contain_text("Alternate")
        expect(card).to_contain_text(re.compile(r"To:\s*" + r"\s+".join(map(re.escape, name.split()))))
        expect(card).to_contain_text(SENT_TODAY)
        expect(card).to_contain_text(re.compile(rf"Space\s+{re.escape(space)}\b"))


@allure.title("Email cards start collapsed, texts expanded, phone logs have no toggle")
@allure.feature("HB Unified Communications")
@allure.story("Communications")
def test_expand_collapse_icons(hb_login_page, app_config, hb_two_space_tenant) -> None:
    # 16447 (email collapsed by default) and 14173 (texts of more than two
    # lines expanded; phone logs have no toggle). Read-only, on the session's
    # two-space tenant - seeded with emails, a long text and a phone log.
    compose = _login(hb_login_page, app_config)
    _open_tenant(compose, hb_two_space_tenant["property_name"], hb_two_space_tenant["tenant"])

    compose.choose("All Communications", "Email")
    with allure.step("16447: every email card is collapsed"):
        cards = compose.card_chevrons("Email")
        assert cards and all(chevron == "down" for _, chevron in cards), cards
    compose.choose("Email", "Text")
    with allure.step("14173: multi-line texts are expanded"):
        cards = compose.card_chevrons("Text")
        assert any(chevron == "up" for _, chevron in cards), cards
        assert not any(chevron == "down" for _, chevron in cards), cards
    compose.choose("Text", "Phone")
    with allure.step("14173: phone logs have no expand/collapse icon"):
        cards = compose.card_chevrons("Call")
        assert cards and all(chevron == "" for _, chevron in cards), cards
    compose.choose("Phone", "All Communications")


@allure.title("Email, text, phone log and note from a tenant's profile")
@allure.feature("HB Unified Communications")
@allure.story("Communications")
def test_send_from_tenant_profile(hb_login_page, app_config, hb_comm_tenants) -> None:
    # 14800 (+ 14299's "Today" date on each new card).
    compose = _login(hb_login_page, app_config)
    tenant = hb_comm_tenants["single"]
    run = f"qa-{uuid.uuid4().hex[:8]}-p"

    _open_tenant(compose, hb_comm_tenants["property_name"], tenant)
    recipients = _send_everything(compose, run, tenant["space"])
    assert any(tenant["email"] in recipient for recipient in recipients), recipients
    _expect_email(tenant["email"], f"{run}-e")


@allure.title("Email, text, phone log and note from the Communication Center")
@allure.feature("HB Unified Communications")
@allure.story("Communications")
def test_send_from_communication_center(hb_login_page, app_config, hb_comm_tenants) -> None:
    # 14799.
    compose = _login(hb_login_page, app_config)
    tenant = hb_comm_tenants["single"]
    run = f"qa-{uuid.uuid4().hex[:8]}-c"

    _select_property(compose, hb_comm_tenants["property_name"])
    compose.open_in_communication_center(tenant["name"])
    _send_everything(compose, run, tenant["space"])
    _expect_email(tenant["email"], f"{run}-e")


@allure.title("Email, text, phone log and note from a lead")
@allure.feature("HB Unified Communications")
@allure.story("Communications")
def test_send_from_lead(hb_login_page, app_config, test_data) -> None:
    # 14801: the first lead in the Reservations view - a storefront guest
    # (Mailinator email, (714) 555-01xx phone); the sends refuse otherwise.
    lead_property = test_data("communication").get("lead_property")
    if not lead_property:
        pytest.skip("No lead property configured for this environment")
    compose = _login(hb_login_page, app_config)
    page = hb_login_page.page
    run = f"qa-{uuid.uuid4().hex[:8]}-l"

    _select_property(compose, lead_property)
    HBLeadManagementPage(page, compose.timeout).open_leads(lead_property)
    grid = HBLeadsGridPage(page, compose.timeout)
    grid.switch_view("Reservations")
    try:
        compose.open_first_lead_communication()
        recipients = _send_everything(compose, run, None)
        compose.close_lead_view()
    finally:
        grid.switch_view("Active Leads")
    address = recipients[0].split(" ")[0]
    _expect_email(address, f"{run}-e")


@allure.title("Send is refused with no recipient; an email reaches the alternate contact")
@allure.feature("HB Unified Communications")
@allure.story("Communications")
def test_recipients_and_alternate_contact(hb_login_page, app_config, hb_comm_tenants) -> None:
    # 14599 (removing the contacts from the compose list - Send is refused, so
    # nothing goes out) and 14597's email part (to the alternate contact too).
    compose = _login(hb_login_page, app_config)
    tenant, alternate = hb_comm_tenants["single"], hb_comm_tenants["alternate"]
    run = f"qa-{uuid.uuid4().hex[:8]}-a"

    _open_tenant(compose, hb_comm_tenants["property_name"], tenant)
    compose.send_without_recipient("Send Email", "All fields are required.")
    compose.send_without_recipient("Send Text", "Please review fields")

    with allure.step("14597: an email to the primary and the alternate contact"):
        recipients = compose.send_email(
            f"QA automation email {run}-e", f"QA automation email body {run}-e",
            also_to=alternate["email"], space=tenant["space"],
        )
        assert any("(Alternate)" in recipient for recipient in recipients), recipients
        compose.expect_sent_card(f"{run}-e", "email", tenant["space"])
    _expect_email(alternate["email"], f"{run}-e")


@allure.title("A text reaches only the alternate contact, from the tenant profile and from the Communication Center with a space picked")
@allure.feature("HB Unified Communications")
@allure.story("Communications")
def test_text_alternate_contact(hb_login_page, app_config, environment_config, hb_comm_tenants) -> None:
    # 14597's text part (to the alternate contact from the tenant profile) and
    # 14598 (a space picked in the Communication Center, then a text to the
    # alternate). Each goes to the Alternate alone, like Robot (user choice
    # 2026-09-14): the session adds it with SMS on and a fictional
    # (707) 555-01xx number.
    compose = _login(hb_login_page, app_config)
    tenant, alternate = hb_comm_tenants["single"], hb_comm_tenants["alternate"]
    run = f"qa-{uuid.uuid4().hex[:8]}-t"

    with allure.step("14597: a text to the alternate from the tenant profile"):
        _open_tenant(compose, hb_comm_tenants["property_name"], tenant)
        recipients = compose.send_text(
            f"QA automation text {run}-p", space=tenant["space"], only_to=alternate["phone_display"]
        )
        assert len(recipients) == 1 and "(Alternate)" in recipients[0], recipients
        _expect_alternate_text_card(compose, f"{run}-p", alternate["name"], tenant["space"])

    with allure.step("14598: the space picked in the Communication Center, then a text to the alternate"):
        # From the dashboard: over the tenant profile, the profile's own
        # "Tenant" select (behind the drawer) was the first match (2026-09-14).
        compose.page.goto(environment_config.hb_base_url.rstrip("/") + "/dashboard", wait_until="domcontentloaded")
        compose.close_restored_drawers(wait_seconds=5)
        _select_property(compose, hb_comm_tenants["property_name"])
        compose.open_in_communication_center(tenant["name"])
        compose.reset_filters(tenant["spaces"])
        compose.choose("Tenant", tenant["space"])
        try:
            recipients = compose.send_text(
                f"QA automation text {run}-c", space=tenant["space"], only_to=alternate["phone_display"]
            )
            assert len(recipients) == 1 and "(Alternate)" in recipients[0], recipients
            _expect_alternate_text_card(compose, f"{run}-c", alternate["name"], tenant["space"])
        finally:
            # After a send HB puts the filter back on "Tenant" itself (seen
            # 2026-09-14), so only restore it when the space still shows.
            if compose._select_showing(tenant["space"]).is_visible():
                compose.choose(tenant["space"], "Tenant")
