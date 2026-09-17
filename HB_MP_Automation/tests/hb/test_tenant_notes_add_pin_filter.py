import uuid

import allure

from pages.common.hb_tenant_notes_page import HBTenantNotesPage
from pages.common.hb_tenant_spaces_page import HBTenantSpacesPage


@allure.title("Notes keep their category and space, pin to the top, filter by space and category, and can't be edited")
@allure.feature("HB Unified Communications")
@allure.story("Notes categories")
def test_tenant_notes_add_pin_and_filter(
    hb_login_page, app_config, environment_config, hb_two_space_tenant
) -> None:
    # Old Robot Unified_Communications/Categories_notes 14305 (a note added from
    # the Communication Center shows its category, space and creator), 14462
    # (pin while adding), 14306 (a pinned note is listed on top), 14461 (notes
    # from the tenant profile), 14308 (space filter), 14309 (category filter -
    # 3 of today's 13, user choice) and 14467 (a saved note can't be edited;
    # its text is selectable).
    # Not migrated: 14463 - the note editor has no link tool, and a typed URL
    # stays plain text (confirmed live 2026-09-14).
    # On the session's two-space tenant (tests/hb/conftest.py). Notes can't be
    # deleted: each carries this run's token, and the test unpins its own in
    # finally (user choice 2026-09-14).
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    timeout = app_config.getint("browser", "timeout")
    page = hb_login_page.page
    dashboard_url = environment_config.hb_base_url.rstrip("/") + "/dashboard"
    property_name = hb_two_space_tenant["property_name"]
    tenant = hb_two_space_tenant["tenant"]["name"]
    spaces = hb_two_space_tenant["tenant"]["spaces"]
    first_space, second_space = spaces[:2]
    run = uuid.uuid4().hex[:8]
    rent = f"qa-{run}-r"
    misc = f"qa-{run}-m"
    delinquency = f"qa-{run}-d"
    texts = {
        rent: f"QA automation note {rent} rent change",
        misc: f"QA automation note {misc} general",
        delinquency: f"QA automation note {delinquency} delinquency",
    }

    notes = HBTenantNotesPage(page, timeout)
    tenants = HBTenantSpacesPage(page, timeout)

    def open_profile() -> None:
        page.goto(dashboard_url, wait_until="domcontentloaded")
        notes.close_restored_drawers(wait_seconds=5)
        tenants.open_tenants(property_name)
        notes.open_tenant(tenant)
        notes.reset_filters(spaces)

    pinned = []
    try:
        notes.close_restored_drawers(wait_seconds=5)
        # Also makes the property the dashboard's, which the Communication
        # Center searches.
        tenants.open_tenants(property_name)
        with allure.step("14305/14462: a pinned note from the Communication Center"):
            notes.open_in_communication_center(tenant)
            notes.add_note(texts[rent], "Rent Changes", first_space, pin=True)
            pinned.append(rent)
            notes.assert_note_card(rent, texts[rent], "Rent Changes", first_space, pinned=True)

        open_profile()
        with allure.step("14461: notes from the tenant profile"):
            notes.add_note(texts[misc], "Miscellaneous", second_space, pin=False)
            notes.assert_note_card(misc, texts[misc], "Miscellaneous", second_space, pinned=False)
            notes.add_note(texts[delinquency], "Delinquency", first_space, pin=False)
            notes.assert_note_card(
                delinquency, texts[delinquency], "Delinquency", first_space, pinned=False
            )

        with allure.step("14306: a pinned existing note is listed on top"):
            notes.set_pinned(misc, True)
            pinned.append(misc)
            # Checked on a fresh load: HB saves the pin at once, but its list can
            # go on showing the note unpinned, in its old place, until reloaded
            # (confirmed 2026-09-14) - and notes saved in the same minute have
            # no fixed order among themselves.
            open_profile()
            notes.assert_pinned_first([rent, misc])

        with allure.step("14308: the space filter"):
            notes.choose("Tenant", second_space)
            notes.expect_notes(visible=[misc], hidden=[rent, delinquency])
            notes.choose(second_space, first_space)
            notes.expect_notes(visible=[rent, delinquency], hidden=[misc])
            notes.choose(first_space, "Tenant")

        with allure.step("14309: the notes category filter"):
            notes.choose("All Communications", "Notes")
            showing = "All Notes"
            for token, category in (
                (rent, "Rent Changes"),
                (delinquency, "Delinquency"),
                (misc, "Miscellaneous"),
            ):
                notes.choose(showing, category)
                showing = category
                notes.expect_notes(
                    visible=[token], hidden=[other for other in texts if other != token]
                )
            notes.choose(showing, "All Notes")
            notes.choose("Notes", "All Communications")

        notes.assert_note_read_only(delinquency)
    finally:
        if pinned:
            with allure.step("Unpin this run's notes"):
                open_profile()
                for token in pinned:
                    notes.set_pinned(token, False)
