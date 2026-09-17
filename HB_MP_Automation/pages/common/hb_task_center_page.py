import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions


class HBTaskCenterPage:
    """HB Task Center (the app bar's "99+/99+" task counter) and the Lead
    Follow-Up panel its lead tasks open.

    Confirmed live (2026-09-13, uat_storoutlet): the panel lists tasks per
    category tab ("N/M Lead", Delinquency, Operations, Maintenance) under a
    view dropdown (All Tasks / Due Today / Overdue / Due Tomorrow). A
    storefront reservation adds a Lead task reading "New Web Reservation |
    <age, e.g. 13 mins> | Website Application | First Follow Up | Follow up
    with the lead | <space> | <guest name>". The old Robot suite's "New
    Reservation" filter menu (.menu-options) no longer exists.

    Not used by the smoke tests any more (user choice 2026-09-13): stage's
    Task Center lists ~12,000 due-today tasks across all categories, 20 per
    page, oldest first, so a new task is out of reach. Tests open Lead
    Follow-Up from the lead's own "Manage Reservation" instead
    (HBLeadManagementPage.open_reservation_follow_up); the panel itself is
    read by HBLeadFollowUpPage.
    """

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout
        self.header = page.get_by_text("Task Center", exact=True).first
        self.move_in_cost = page.get_by_text(re.compile(r"Move-In Cost:")).first

    @log_method_exceptions
    def open(self) -> None:
        with allure.step("Open Task Center"):
            if self.header.is_visible():
                return
            # Three app-bar items share this name; the first is the task
            # counter ("99+/99+") - confirmed live 2026-09-13.
            opener = self.page.locator('[name="QA-v-list-item-HbIcon-NoButtonText"]').first
            expect(opener).to_be_visible(timeout=self.timeout)
            opener.click()
            expect(self.header).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def open_lead_follow_up(self, space_number: str, guest_name: str) -> None:
        """Opens the Lead Follow-Up of the "New Web Reservation" task for
        this space and guest. Matched on both: a space number also appears
        on older leads' task cards (confirmed live 2026-09-13 - matching on
        the space alone opened an unrelated lead). Opening Follow-Up starts
        HB's follow-up timer on the lead; nothing is logged or saved here."""
        with allure.step(f"Open lead follow-up: {guest_name}, space {space_number}"):
            # Confirmed live (2026-09-13): .tasks-list lazy-loads its tasks
            # page by page as it's scrolled to the bottom (19 -> 29 -> ... ->
            # 86), and new web reservations sit near the end - so the list
            # is scrolled until its height stops growing before searching.
            task_list = self.page.locator(".tasks-list").first
            expect(task_list).to_be_visible(timeout=self.timeout)
            last_height, unchanged = -1, 0
            for _ in range(int(self.timeout / 1000)):
                height = task_list.evaluate(
                    "list => { list.scrollTop = list.scrollHeight; return list.scrollHeight; }"
                )
                unchanged = unchanged + 1 if height == last_height else 0
                if unchanged >= 2:
                    break
                last_height = height
                self.page.wait_for_timeout(1000)

            # The list runs oldest to newest, so the last matching card is
            # the newest - relevant once a later run reserves the same space.
            card = None
            spaces = task_list.get_by_text(space_number, exact=True)
            for index in range(spaces.count()):
                candidate = spaces.nth(index).locator(
                    'xpath=ancestor::*[.//text()[contains(., "Follow up with the lead")]][1]'
                )
                candidate_text = candidate.inner_text()
                if guest_name in candidate_text and "New Web Reservation" in candidate_text:
                    card = candidate
            if card is None:
                raise AssertionError(
                    f"No 'New Web Reservation' task for {guest_name} on space "
                    f"{space_number} in Task Center"
                )
            card.get_by_text("First Follow Up", exact=True).first.click()
            expect(self.move_in_cost).to_be_visible(timeout=self.timeout)
            # Guard against having opened some other lead's Follow-Up.
            follow_up_header = self.page.get_by_text(f"Space #{space_number}", exact=False).first
            expect(follow_up_header).to_be_visible(timeout=self.timeout)
