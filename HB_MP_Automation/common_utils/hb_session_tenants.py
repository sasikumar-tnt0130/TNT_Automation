import re
import uuid

import allure
from playwright.sync_api import Page, expect

from common_utils.hb_quick_launch_lease_setup import (
    add_space_and_lease_for_tenant,
    create_lease_through_quick_action,
)
from common_utils.test_identities import new_additional_contact, new_hb_lead_guest
from config.config_reader import EnvironmentConfig
from pages.common.hb_additional_contacts_page import HBAdditionalContactsPage
from pages.common.hb_communication_compose_page import HBCommunicationComposePage
from pages.common.hb_move_out_page import HBMoveOutPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage

# About 850 characters: long enough to overflow a text card's collapsed box
# at 1920x1080, so HB shows its collapse icon (see
# HBEmailCardsPage.assert_text_card).
LONG_TEXT = (
    "QA automation seed text {run}. "
    + "This long automated test message runs past two lines so the Communication Center "
    "shows it expanded, with a collapse icon, its space number and the time it was sent. " * 4
    + "No reply is needed."
)


def _dashboard(page: Page, environment_config: EnvironmentConfig) -> None:
    page.goto(environment_config.hb_base_url.rstrip("/") + "/dashboard", wait_until="domcontentloaded")


def _tenant(guest: dict, spaces: list[str]) -> dict:
    return {
        "name": f"{guest['first_name']} {guest['last_name']}",
        "first_name": guest["first_name"],
        "last_name": guest["last_name"],
        "email": guest["email"],
        "phone_number": guest["phone_number"],
        "spaces": spaces,
        "space": spaces[0],
        # A lease paid in full at move-in.
        "status": "Current",
    }


def _open_new_tenant(page: Page, timeout: float, environment_config: EnvironmentConfig, property_name: str, tenant: dict) -> None:
    """Opens a just-created tenant's page from the Tenants list and records
    its contact id ("/contacts/<id>"), which move_out_tenants opens directly
    rather than searching the list again: at teardown the list once showed
    every tenant with the search box empty (it had reloaded after the
    search was typed) and the tenant's row wasn't among those drawn
    (2026-09-14)."""
    _dashboard(page, environment_config)
    spaces_page = HBTenantSpacesPage(page, timeout)
    spaces_page.open_tenants(property_name)
    spaces_page.open_tenant_details(tenant["first_name"], tenant["last_name"])
    expect(page).to_have_url(re.compile(r"/contacts/[A-Za-z0-9]+"), timeout=timeout)
    tenant["contact_id"] = re.search(r"/contacts/([A-Za-z0-9]+)", page.url).group(1)


def create_single_tenant(
    page: Page,
    timeout: float,
    environment_config: EnvironmentConfig,
    lease_data: dict,
    created: list[dict],
) -> tuple[dict, dict]:
    """A fresh one-space tenant on lease_data's property (Quick Launch lease,
    cash) and its Alternate contact - returned as (tenant, alternate). The
    tenant is appended to `created` as soon as it exists, so a failure
    part-way still gets it moved out."""
    guest = new_hb_lead_guest()
    with allure.step("A one-space tenant"):
        # Quick Actions ("Move In/Reserve") are on the dashboard only - the
        # page can still be on the two-space tenant's page (2026-09-14).
        _dashboard(page, environment_config)
        lease = create_lease_through_quick_action(
            page, timeout, environment_config, lease_data, guest, payment_method="cash"
        )
        tenant = _tenant(guest, [lease.space_number])
        created.append(tenant)

    contact = new_additional_contact()
    with allure.step("Its Alternate contact"):
        _open_new_tenant(page, timeout, environment_config, lease_data["property_name"], tenant)
        # SMS on, so texts can go to it too - its number is fictional as well.
        HBAdditionalContactsPage(page, timeout).add_contact(contact, "Alternate", [tenant["space"]], sms=True)
    digits = contact["phone_number"]
    alternate = {
        "name": f"{contact['first_name']} {contact['last_name']}",
        "designation": "Alternate",
        "email": contact["email"],
        # The contact tooltip shows the number with its country code.
        "phone": "1" + digits,
        # As Send Text's To list shows it, e.g. "(707) 555-0123".
        "phone_display": f"({digits[:3]}) {digits[3:6]}-{digits[6:]}",
    }
    return tenant, alternate


def create_two_space_tenant(
    page: Page,
    timeout: float,
    environment_config: EnvironmentConfig,
    lease_data: dict,
    created: list[dict],
) -> dict:
    """A fresh tenant with two spaces on lease_data's property (a Quick Launch
    lease, then Add Space - both paid in cash: with the second skipped, the
    moved-out tenant kept a $66.71 balance, 2026-09-14), seeded with what
    the read-only communication tests read - see seed_history. Appended to
    `created` as soon as it exists."""
    guest = new_hb_lead_guest()
    with allure.step("A two-space tenant"):
        _dashboard(page, environment_config)
        lease = create_lease_through_quick_action(
            page, timeout, environment_config, lease_data, guest, payment_method="cash"
        )
        tenant = _tenant(guest, [lease.space_number])
        created.append(tenant)
        _open_new_tenant(page, timeout, environment_config, lease_data["property_name"], tenant)
        _dashboard(page, environment_config)
        second = add_space_and_lease_for_tenant(page, timeout, lease_data, guest, payment_method="cash")
        tenant["spaces"] = sorted([*tenant["spaces"], second.space_number])
        tenant["space"] = tenant["spaces"][0]
    seed_history(page, timeout, environment_config, lease_data["property_name"], tenant)
    return tenant


def seed_history(
    page: Page,
    timeout: float,
    environment_config: EnvironmentConfig,
    property_name: str,
    tenant: dict,
) -> None:
    """What the read-only communication tests read: an email and a text on
    each of the tenant's spaces, a long text and a phone log. Emails go only
    to Mailinator and texts only to the fictional number
    (HBCommunicationComposePage refuses anything else)."""
    run = uuid.uuid4().hex[:8]
    with allure.step(f"Seed {tenant['name']}'s communications"):
        compose = HBCommunicationComposePage(page, timeout)
        _dashboard(page, environment_config)
        HBTenantSpacesPage(page, timeout).open_tenants(property_name)
        compose.open_tenant(tenant["name"])
        compose.reset_filters(tenant["spaces"])
        for space in tenant["spaces"]:
            compose.send_email(
                f"QA automation seed email {run} {space}", f"QA automation seed email body {run}", space=space
            )
            compose.send_text(f"QA automation seed text {run} {space}", space=space)
        compose.send_text(LONG_TEXT.format(run=run), space=tenant["spaces"][0])
        compose.log_phone_call(f"QA automation seed phone log {run}")


def move_out_tenants(
    page: Page,
    timeout: float,
    environment_config: EnvironmentConfig,
    property_name: str,
    tenants: list[dict],
    reason: str,
) -> list[str]:
    """Moves out every space of `tenants`, freeing them, and checks each is
    gone from its tenant's page; returns what couldn't be moved out. Each
    space is tried on its own - one failure mustn't leave the rest
    occupied. A tenant is opened by its contact id when recorded (see
    _open_new_tenant), else from the Tenants list."""
    problems = []
    for tenant in tenants:
        for space in tenant["spaces"]:
            with allure.step(f"Move out {tenant['name']} space {space}"):
                try:
                    compose = HBCommunicationComposePage(page, timeout)
                    if tenant.get("contact_id"):
                        page.goto(
                            environment_config.hb_base_url.rstrip("/") + f"/contacts/{tenant['contact_id']}",
                            wait_until="domcontentloaded",
                        )
                        compose.close_restored_drawers(wait_seconds=3)
                    else:
                        _dashboard(page, environment_config)
                        HBTenantSpacesPage(page, timeout).open_tenants(property_name)
                        # .first: a two-space tenant has a row per space.
                        compose.open_tenant(tenant["name"])
                    HBMoveOutPage(page, timeout).move_out_space(space, reason)
                    # A moved-out space loses its "Space 0040" heading on the
                    # tenant's page (the lease shows under CLOSED LEASES,
                    # confirmed 2026-09-14) - checked on a fresh load.
                    page.reload(wait_until="domcontentloaded")
                    compose.close_restored_drawers(wait_seconds=3)
                    expect(page.get_by_text(re.compile(rf"^\s*Space {re.escape(space)}\s*$"))).to_have_count(
                        0, timeout=timeout
                    )
                except Exception as error:  # reported, not raised - see the docstring
                    problems.append(f"{tenant['name']} space {space}: {error}")
    return problems
