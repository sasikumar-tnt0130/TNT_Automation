import allure
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)
from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


class HBMoveOutPage:
    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def open_tenants(self, property_name: str) -> None:
        with allure.step(f"Open tenants for {property_name}"):
            self._close_live_agent_notification()
            search_box = self.page.locator("#search-box")
            expect(search_box).to_be_visible(timeout=self.timeout)
            search_box.click()
            # #search-box is a wrapper div (icon + input); the fillable
            # element is the nested input.
            search_input = search_box.locator("input")
            property_cell = self.page.get_by_role(
                "cell", name=property_name, exact=True
            )
            # The picker's default list is whatever's most-recently-used/
            # on top, so the target property isn't guaranteed to be there
            # without narrowing it down first - type the name to filter
            # down to it explicitly instead of hoping it's already visible.
            try:
                expect(property_cell).to_be_visible(timeout=waits().short)
            except AssertionError:
                search_input.fill(property_name)
                expect(property_cell).to_be_visible(timeout=self.timeout)
            property_cell.click()
            # Same multi-property picker quirk as HBLeadManagementPage.
            # open_leads: only a click on the row selects it there.
            try:
                expect(property_cell).to_be_hidden(timeout=waits().short)
            except AssertionError:
                property_cell.locator("xpath=ancestor::tr[1]").dispatch_event(
                    "click"
                )
            # Wait until the dashboard header names the property - see
            # HBTenantSpacesPage.open_tenants (a run went on company-wide).
            expect(
                self.page.get_by_role("textbox", name=property_name)
            ).to_be_visible(timeout=self.timeout)
            tenants_link = self.page.get_by_role("complementary").get_by_text(
                "Tenants", exact=True
            )
            expect(tenants_link).to_be_visible(timeout=self.timeout)
            tenants_link.locator(
                "xpath=ancestor::*[@role='listitem'][1]"
            ).dispatch_event("click")
            self._close_live_agent_notification()

    @log_method_exceptions
    def _wait_for_grid_loading_to_finish(self) -> None:
        # The ag-grid virtual row model renders one "Loading" placeholder per
        # pending row, so several can be visible at once - expect(...).to_be_hidden()
        # requires a single match and raises a strict-mode violation here.
        loading_row = self.page.get_by_text("Loading", exact=True)
        deadline = time.monotonic() + self.timeout / 1000
        while time.monotonic() < deadline and loading_row.count() > 0:
            self.page.wait_for_timeout(waits().poll_interval)

    @log_method_exceptions
    def _close_live_agent_notification(self) -> None:
            live_agent_notification = self.page.get_by_text(
                "Need to talk to a live agent?", exact=True
            )
            # Scoped to the banner's own tooltip: confirmed live (2026-09-13,
            # Chula Vista) that an unscoped ".mdi-close" .first is the
            # move-out drawer's close X whenever the drawer is open, so
            # "dismissing the banner" closed the drawer right before its
            # final Move Out. With the drawer open the banner's X is covered
            # (a .v-messages layer intercepts the click) - that just times
            # out below, harmlessly.
            close_notification = (
                self.page.locator(".v-tooltip__content.custom-tooltip-popup")
                .filter(has_text="Need to talk to a live agent?")
                .locator(".mdi-close")
            )
            if live_agent_notification.count() > 0 and live_agent_notification.first.is_visible():
                if close_notification.count() > 0 and close_notification.first.is_visible():
                    try:
                        # This banner can render pinned outside the current
                        # viewport (seen after a reload), where Playwright's
                        # own scroll-into-view never resolves it - not
                        # worth burning the full default timeout on a
                        # non-essential notification dismissal.
                        close_notification.first.click(timeout=waits().short)
                    except PlaywrightTimeoutError:
                        pass

    @log_method_exceptions
    def filter_move_in_date(
        self,
        date_filter: str,
        custom_range_start_date: str | None = None,
        custom_range_end_date: str | None = None,
    ) -> bool:
        # This filter panel can still intermittently close itself
        # mid-interaction - a stray grid re-render tearing down its
        # anchored menu, the Custom Range picker's own view resetting, a
        # forced click landing on the wrong element - even with the fixes
        # already in place for each specific cause found so far. Retrying
        # the whole "open panel, pick filter, set/verify it" sequence in
        # place, on the same page, recovers from that far more cheaply than
        # _filter_move_in_date_with_retry's page.reload() fallback, which
        # is kept as a last resort but should now rarely be needed.
        attempts = 2
        for attempt in range(attempts):
            if attempt > 0:
                # A previous attempt may have left a stray menu open (or
                # half-open) - closing it first keeps this attempt's own
                # element lookups (e.g. the filter icon's .ag-header-active
                # selector) from matching a leftover, inconsistent state.
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
            try:
                return self._attempt_filter_move_in_date(
                    date_filter, custom_range_start_date, custom_range_end_date
                )
            except (AssertionError, PlaywrightTimeoutError):
                if attempt == attempts - 1:
                    raise
        raise AssertionError("Unreachable")

    @log_method_exceptions
    def _attempt_filter_move_in_date(
        self,
        date_filter: str,
        custom_range_start_date: str | None,
        custom_range_end_date: str | None,
    ) -> bool:
        with allure.step(f"Filter tenants by move-in date: {date_filter}"):
            # Chrome throttles timers/animations for a window that isn't
            # OS-focused, which can drop a click or close the filter panel
            # mid-interaction - force focus so this window isn't throttled.
            self.page.bring_to_front()
            # The grid's own server-side row fetch can still be in flight
            # right after navigating here (e.g. straight from login), and
            # that main-thread activity can stretch the date picker's own
            # month-to-month crossfade well past its normal near-instant
            # length - confirmed by reproduction: a warm, idle page settles
            # a month change in under 50ms, but the same click hung for a
            # full 60s in a freshly-launched run. Waiting for the grid to go
            # quiet first avoids starting the date picker while it's busy.
            self._wait_for_grid_loading_to_finish()
            # The named (non-Custom-Range) options below are selected with a
            # forced click that bypasses Playwright's actionability checks,
            # which can land mid-transition while the options list is
            # switching views. Disabling transitions keeps that click from
            # landing wrong. Custom Range doesn't need this: its own option
            # click and every calendar interaction use plain, actionability
            # checked clicks instead of force=True, and disabling transitions
            # there is actively harmful - confirmed by reproduction, it stops
            # the browser's transitionend event from ever firing, which
            # Vuetify's month-paging calendar's Vue <transition-group>
            # depends on to finish swapping out the old month grid, so the
            # whole filter panel can end up closing partway through picking
            # a date and never reopening.
            if date_filter != "Custom Range":
                self.page.add_style_tag(
                    content=(
                        "*, *::before, *::after { "
                        "transition: none !important; "
                        "animation: none !important; "
                        "}"
                    )
                )
            move_in_header = self.page.get_by_role(
                "columnheader",
                name="Move In",
                description=(
                    "Press ENTER to sort. "
                    "Press CTRL ENTER to open column menu."
                ),
            )
            expect(move_in_header).to_be_visible(timeout=self.timeout)
            move_in_header.click()
            # Clicking the header (needed so the filter icon's
            # .ag-header-active selector below matches) also toggles a sort,
            # and this grid is AG Grid's Server-Side Row Model - confirmed
            # by its own console warning ("getRowId callback must be
            # provided for Server Side Row Model") - so that sort triggers a
            # real server refetch. If that fetch's response lands after the
            # Custom Range panel is already open, AG Grid redrawing the
            # header to show the new sort/data can tear down the filter
            # menu anchored to it, closing the whole panel mid-pick. Waiting
            # for the grid to go quiet here lets that fetch resolve first.
            # The "Loading" row placeholder it checks for is one signal, but
            # a sort-triggered refetch can also resolve quietly (swapping
            # rows once ready, no placeholder) - waiting on network idle
            # covers that case too, bounded short since this page can have
            # other, unrelated background requests that never go idle.
            self._wait_for_grid_loading_to_finish()
            try:
                self.page.wait_for_load_state("networkidle", timeout=waits().tiny)
            except PlaywrightTimeoutError:
                pass
            filter_icon = self.page.locator(
                ".ag-header-cell.ag-header-cell-sortable."
                "ag-header-cell-wrap-text.ag-focus-managed.ag-header-active "
                "> .ag-header-cell-comp-wrapper > .header-col > .menu-filter "
                "> span > span > span > .v-icon"
            )
            expect(filter_icon).to_be_visible(timeout=self.timeout)
            filter_icon.click()
            filter_select = self.page.get_by_role("button").filter(
                has_text="cleararrow_drop_down"
            )
            expect(filter_select).to_be_visible(timeout=self.timeout)
            filter_select.click()
            date_option = self.page.get_by_role(
                "option", name=date_filter, exact=True
            )
            expect(date_option).to_be_visible(timeout=self.timeout)
            if date_filter == "Custom Range":
                # A forced click bypasses Playwright's actionability checks
                # (visible, stable, receives events) and can land mid
                # transition, leaving the named-options list rendered on top
                # of the date-range panel instead of switching to it. A
                # normal click waits for the option to actually be stable
                # and clickable first, matching how this behaves manually.
                date_option.click()
            else:
                date_option.click(force=True)

            if date_filter == "Custom Range":
                self._open_custom_range_date_fields()
                self._set_custom_move_in_date_range(
                    custom_range_start_date, custom_range_end_date
                )

            set_filter_button = self.page.get_by_role(
                "button", name="Set Filter"
            )
            expect(set_filter_button).to_be_enabled(timeout=self.timeout)
            # A plain click, not force=True - the same class of bug already
            # fixed for the Custom Range calendar itself: a forced click
            # bypasses Playwright's "is anything else on top of this"
            # check, and can land on the popup's own outside-click backdrop
            # instead of the button, which closes the whole filter panel
            # without applying it - matching the observed failure, where
            # the grid reverted to the unfiltered "Active Tenants" default
            # right after this click instead of showing the applied range.
            set_filter_button.click()
            # Confirms the filter that was actually applied matches what was
            # picked, not just that clicking "Set Filter" did something -
            # every filter (named or Custom Range) shows an applied-filter
            # chip once it takes effect. Custom Range's chip additionally
            # spells out the exact range, so check that precisely rather
            # than just the filter's name.
            if date_filter == "Custom Range":
                applied_filter_chip = self.page.locator("div").filter(
                    has_text=re.compile(
                        rf"^Custom Range \("
                        rf"{re.escape(custom_range_start_date)} To "
                        rf"{re.escape(custom_range_end_date)}\)$"
                    )
                )
            else:
                applied_filter_chip = self.page.locator("div").filter(
                    has_text=re.compile(rf"^{re.escape(date_filter)}$")
                )
            expect(applied_filter_chip.first).to_be_visible(timeout=self.timeout)
            self._wait_for_grid_loading_to_finish()
            zero_tenants_status = self.page.get_by_text(
                "Tenants: 0 of", exact=False
            )
            if zero_tenants_status.count() > 0 and zero_tenants_status.first.is_visible():
                zero_tenants_status.first.click()
                logging.info("No active tenants to move out")
                return True
            return False

    @log_method_exceptions
    def _open_custom_range_date_fields(self) -> None:
        # Selecting "Custom Range" can leave the named-options list rendered
        # on top of the date-range panel for a moment - a click during that
        # overlap can land on a stale option underneath instead, so wait for
        # the date fields to actually render rather than clicking through it.
        date_fields = self.page.locator(".hummingbird-date-text-field-wrapper")
        expect(date_fields.first).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _set_custom_move_in_date_range(self, start_date: str, end_date: str) -> None:
        with allure.step(f"Set custom move-in date range: {start_date} to {end_date}"):
            # Each field's accessible name ("Start Date"/"End Date") only
            # holds while it's still empty - exactly the state it's in the
            # one time we click it here - so role-based lookup is a more
            # semantic, direct target than matching the shared wrapper class
            # and indexing into it.
            self._pick_calendar_date(
                self.page.get_by_role("textbox", name="Start Date", exact=True),
                start_date,
            )
            self._pick_calendar_date(
                self.page.get_by_role("textbox", name="End Date", exact=True),
                end_date,
            )

    @log_method_exceptions
    def _mouse_click(self, locator: Locator) -> None:
        # A real move+down+up at the element's own coordinates, rather than
        # Locator.click()'s stricter "visible, stable, receives events"
        # actionability gate - confirmed necessary by direct reproduction:
        # a ripple/overlay div (e.g. ".v-input--selection-controls__ripple")
        # repeatedly intercepts pointer events on this app's Vuetify
        # radios/pickers under real automation timing, which a genuine
        # mouse click isn't sensitive to, matching how this behaves when
        # driven by an actual mouse by hand.
        # Locator.click() also auto-scrolls the element into view as part of
        # its actionability checks - bypassing it here means that has to be
        # done explicitly, or bounding_box() can return coordinates that are
        # CSS-visible but scrolled outside a container's actual viewport
        # (e.g. below the fold in the move-out drawer's own scroll area),
        # so the click silently lands on nothing.
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        if box is None:
            locator.click()
            return
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.up()

    @log_method_exceptions
    def _pick_calendar_date(self, field: Locator, date_str: str) -> None:
        # Expected format: "Jan 1, 2016"
        target = datetime.strptime(date_str, "%b %d, %Y")
        # A plain click here, not _mouse_click's raw coordinates - confirmed
        # by direct reproduction: this picker's Previous/Next/day buttons
        # have no ripple/overlay intercepting them (unlike the move-out
        # radios _mouse_click exists for), so Playwright's own actionability
        # checks land reliably, whereas a raw click can land on whatever the
        # popup's outside-click backdrop is instead - which reads to Vuetify
        # as a click outside the menu and closes the whole filter panel.
        field.click()
        # Under real automation timing this picker's popup can end up in a
        # bad state (a stale/hidden button left over from another render,
        # or the whole panel closing) in a handful of different ways - the
        # exact symptom has varied by run. Whichever way it fails, it fails
        # fast (elements go stale/invisible almost immediately, not after a
        # long wait), so every wait below uses a short, calendar-specific
        # timeout instead of the page's full self.timeout - there's no
        # value in spending a full minute reconfirming a failure that's
        # already evident in a couple of seconds, and a short timeout here
        # lets _filter_move_in_date_with_retry's reload-and-retry actually
        # cycle through its attempts quickly instead of each one eating a
        # minute-plus.
        calendar_timeout = 10000
        # Paged month-by-month via the picker's own Previous/Next buttons
        # rather than drilling into a year-list view, since that never
        # leaves the day-grid view and so avoids the year-list's
        # CSS-transition view-switches.
        # Scoped to ".last" throughout, not just ":visible" - Start Date's
        # popup isn't guaranteed to be closed by the time End Date's opens,
        # so more than one can genuinely be visible at once. The
        # most-recently-opened one (this field's own) is always the last
        # match in DOM order, so ".last" reliably targets it regardless of
        # what the other field's popup is doing.
        header_button = self.page.locator(
            ".v-date-picker-header__value button:visible"
        ).last
        expect(header_button).to_be_visible(timeout=calendar_timeout)
        # Everything else below is scoped inside THIS SAME popup, found as
        # header_button's own enclosing menu, rather than independently
        # queried page-wide with its own ".last" - independent ".last"
        # calls on different element types (header vs. nav button vs. day
        # button) only agree on "which popup is most recent" if their
        # relative DOM order happens to match, which isn't guaranteed. That
        # mismatch is a plausible explanation for failures seen where a day
        # button resolved successfully but then sat permanently not
        # visible - it could have kept resolving into the OTHER field's
        # popup throughout. Scoping to one confirmed-current container
        # removes the cross-popup ambiguity outright.
        popup = header_button.locator(
            "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), "
            "' v-menu__content ')][1]"
        )
        # This picker cycles through three views, each one click on the
        # header away from the next: day-grid ("September 2026") -> click
        # header -> month-grid for that year ("2026", 12 months) -> click
        # the year number -> a scrollable year-list (confirmed live: 201
        # years, plain clickable <li> items, no incremental scrolling
        # needed - Playwright's own click scrolls the target year into
        # view). Picking an item drops back down one level. That reaches
        # ANY date in a small constant number of clicks regardless of how
        # far away it is - unlike paging month-by-month or even year-by-
        # year, both of which scale with the distance and made a 26-year-
        # out date effectively never finish navigating.
        day_grid = popup.locator(".v-date-picker-table--date")
        month_grid = popup.locator(".v-date-picker-table--month")
        year_list = popup.locator(".v-date-picker-years")
        month_option = popup.locator(
            ".v-date-picker-table--month button:visible"
        ).filter(has_text=re.compile(rf"^{target.strftime('%b')}$"))
        day_option = popup.locator(
            ".v-date-picker-table--date button:visible"
        ).filter(has_text=re.compile(rf"^{target.day}$"))
        year_option = year_list.locator("li").filter(
            has_text=re.compile(rf"^{target.year}$")
        )
        # Confirmed by direct reproduction: this picker can silently reset
        # its own displayed page back to today's month on its own - a run
        # navigated cleanly from September to August and even matched the
        # target day button, but by the time the click actually ran the
        # header had already reverted to September, so the click landed on
        # nothing. Since that reset isn't tied to any wait we control (it
        # happened whether or not extra settle time was added), the only
        # reliable defense is to not trust a single navigate-then-click
        # pass at all - re-derive what to click from whatever view is
        # actually on screen on every attempt, right up to the moment of
        # the final click, so a reset just costs a retry instead of a
        # failure.
        # Every click below is wrapped the same way: try it with a short
        # timeout, and on ANY failure just fall through to the next
        # attempt, which re-derives what to click from whatever's actually
        # on screen by then. A click that isn't wrapped this way (an
        # earlier version only wrapped the final day click) lets that one
        # exception escape the whole loop instead of being retried - and
        # confirmed by reproduction, the month click can hit the exact same
        # transient state the day click does (a leftover fade-transition
        # wrapper intercepting the click), so it needs the same protection.
        click_timeout = 3000
        attempts = 30
        for attempt in range(attempts):
            try:
                if year_list.count() > 0 and year_list.first.is_visible():
                    expect(year_option).to_be_visible(timeout=click_timeout)
                    year_option.click(timeout=click_timeout)
                elif month_grid.count() > 0 and month_grid.first.is_visible():
                    current_year = int(
                        re.sub(r"\D", "", header_button.inner_text())
                    )
                    if current_year != target.year:
                        header_button.click(timeout=click_timeout)
                    else:
                        expect(month_option).to_be_visible(timeout=click_timeout)
                        month_option.click(timeout=click_timeout)
                elif day_grid.count() > 0 and day_grid.first.is_visible():
                    current = datetime.strptime(
                        header_button.inner_text(), "%B %Y"
                    )
                    if (current.year, current.month) != (
                        target.year,
                        target.month,
                    ):
                        header_button.click(timeout=click_timeout)
                    else:
                        expect(day_option).to_be_visible(timeout=click_timeout)
                        day_option.click(timeout=click_timeout)
                        return
                else:
                    # No view is visible yet - a view-switch transition
                    # still settling.
                    pass
            except (PlaywrightTimeoutError, AssertionError, ValueError):
                # ValueError covers header text mid-transition (neither a
                # full "%B %Y" nor purely a year for a moment).
                pass
            if attempt == attempts - 1:
                diagnostic_path = (
                    Path(__file__).resolve().parents[2]
                    / "reports"
                    / "screenshots"
                    / f"custom-range-day-click-failure-{int(time.time())}.png"
                )
                diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
                self.page.screenshot(path=str(diagnostic_path), full_page=True)
                logging.error(
                    "Could not select %s in the calendar after %s attempts - "
                    "diagnostic screenshot at %s",
                    date_str,
                    attempts,
                    diagnostic_path,
                )
                raise AssertionError(
                    f"Could not select {date_str} in the calendar after "
                    f"{attempts} attempts"
                )
            self.page.wait_for_timeout(50)

    @log_method_exceptions
    def _filter_move_in_date_with_retry(
        self,
        property_name: str,
        date_filter: str,
        custom_range_start_date: str | None,
        custom_range_end_date: str | None,
    ) -> bool:
        # This account's live filter panel can still intermittently close
        # itself mid-interaction regardless of click strategy - a full page
        # reload gives each retry a clean state instead of resuming on top
        # of whatever broke. filter_move_in_date already retries itself
        # in-place first, so getting here at all means that recovery also
        # failed - kept small since each attempt here is a full reload.
        attempts = 2
        for attempt in range(attempts):
            try:
                return self.filter_move_in_date(
                    date_filter, custom_range_start_date, custom_range_end_date
                )
            except (AssertionError, PlaywrightTimeoutError):
                if attempt == attempts - 1:
                    raise
                self.page.reload()
                self.open_tenants(property_name)
        raise AssertionError("Unreachable")

    @log_method_exceptions
    def move_out_all_spaces(
        self,
        property_name: str,
        date_filter: str,
        reason: str,
        custom_range_start_date: str | None = None,
        custom_range_end_date: str | None = None,
    ) -> bool:
        space_rows = self.page.locator(
            ".ag-center-cols-viewport [role='row']"
        )
        moved_out_space_count = 0
        known_issue_space_numbers: set[str] = set()

        while True:
            self.open_tenants(property_name)
            if self._filter_move_in_date_with_retry(
                property_name,
                date_filter,
                custom_range_start_date,
                custom_range_end_date,
            ):
                break
            try:
                expect(space_rows.first).to_be_visible(timeout=self.timeout)
            except (PlaywrightTimeoutError, AssertionError):
                break

            next_space = self._find_next_movable_row(
                space_rows, known_issue_space_numbers
            )
            if next_space is None:
                logging.warning(
                    "Stopping move-out sweep: every remaining filtered space "
                    "(%s) hit a known application issue and cannot be moved out",
                    ", ".join(sorted(known_issue_space_numbers)),
                )
                break

            row, space_number = next_space
            with allure.step(f"Move out filtered space: {space_number}"):
                row.locator("[role='gridcell']").first.click()

            if self._complete_move_out(reason, space_number):
                moved_out_space_count += 1
            else:
                known_issue_space_numbers.add(space_number)

        if moved_out_space_count == 0 and not known_issue_space_numbers:
            logging.info("No active tenants to move out")

        if known_issue_space_numbers:
            allure.attach(
                "Move-out could not be completed for these spaces due to "
                "application-side issues (Invoice ID not set on a pending "
                "refund, a stalled refund, no working Move Out flow, or an "
                "empty move-out reasons list) - see the warning logged for "
                "each space's specific cause: "
                + ", ".join(sorted(known_issue_space_numbers)),
                name="Known-issue move-out skips",
                attachment_type=allure.attachment_type.TEXT,
            )

        return True

    @log_method_exceptions
    def current_space_number(self) -> str:
        # The tenant page titles each of the tenant's spaces "Space 0018"
        # (confirmed live, 2026-09-11, Bellflower) - for a single-space
        # tenant the first such heading is that space.
        heading = self.page.get_by_text(re.compile(r"^Space \d+$")).first
        expect(heading).to_be_visible(timeout=self.timeout)
        return heading.inner_text().strip().removeprefix("Space ").strip()

    @log_method_exceptions
    def move_out_space(self, space_number: str, reason: str) -> None:
        """Moves out one specific space from the tenant page that's already
        open - the single-tenant counterpart of move_out_all_spaces, for the
        old Robot suite's "Move out without balance" scenario.

        Confirmed live (2026-09-11, Bellflower): the drawer still has that
        suite's three steps (Intent to Move-Out, Prepare Space, Move-Out
        Statement), but Prepare Space now defaults to "Space is clean and
        ready for move-in" with its checklist pre-ticked, and the
        statement's final action is a single Move Out (+ Confirm) instead of
        the suite's Close Lease / Move Space back to Inventory pair - exactly
        what _complete_move_out already drives. Unlike the sweep, a move-out
        that doesn't complete is a failure here, not a skip."""
        with allure.step(f"Move out space {space_number}"):
            if not self._complete_move_out(reason, space_number):
                raise AssertionError(
                    f"Move-out of space {space_number} did not complete - "
                    "see the warning logged above for the cause"
                )

    @log_method_exceptions
    def _find_next_movable_row(
        self, space_rows: Locator, known_issue_space_numbers: set[str]
    ) -> tuple[Locator, str] | None:
        for index in range(space_rows.count()):
            row = space_rows.nth(index)
            cell = row.locator("[role='gridcell']").first
            space_number = cell.inner_text().strip().lstrip("#")
            if space_number not in known_issue_space_numbers:
                return row, space_number
        return None

    @log_method_exceptions
    def _complete_move_out(self, reason: str, space_number: str) -> bool:
        with allure.step("Open move-out actions"):
            self._close_live_agent_notification()
            space_heading = self.page.get_by_text(
                f"Space {space_number}", exact=True
            ).first
            expect(space_heading).to_be_visible(timeout=self.timeout)
            space_settings = space_heading.locator(
                "xpath=following::button"
                "[contains(normalize-space(.), 'Space Settings & Information')][1]"
            )
            expect(space_settings).to_be_visible(timeout=self.timeout)
            space_settings.click()
            move_out_button = space_heading.locator(
                "xpath=following::button[normalize-space(.)='Move Out'][1]"
            )
            expect(move_out_button).to_be_visible(timeout=self.timeout)
            move_out_button.click()

            # .first: confirmed live (2026-09-13, Chula Vista) the drawer can
            # show this text three times (stepper label, heading, button).
            intent_to_move_out = self.page.get_by_text(
                "Intent to Move-Out", exact=True
            ).first
            try:
                expect(intent_to_move_out).to_be_visible(timeout=waits().short)
            except AssertionError:
                logging.warning(
                    "Skipping Space %s: no working Move Out flow opened for "
                    "this tenant (for example, a Pending lease has no "
                    "move-out action)",
                    space_number,
                )
                return False

            # Confirmed live 2026-09-14 (Chula Vista, straight after removing
            # AutoPay): the drawer can open blank - header "Move-Out:" with no
            # space, only the stepper, no Next - while opening it again a
            # little later loads normally. The stepper label above doesn't
            # tell the two apart, so wait for the real Next and reopen once.
            intent_next = self.page.locator(
                'button[name="QA-IntentMoveOut-hb-primary-button-Next"]'
            )
            try:
                expect(intent_next).to_be_visible(timeout=waits().extra_long)
            except AssertionError:
                with allure.step("Verify move-out drawer opened blank - reopening it once"):
                    blank_drawer = self.page.locator(".v-navigation-drawer.move_out")
                    blank_drawer.locator(
                        'button[name="QA-v-card-HbIcon-mdi-close"]'
                    ).first.click()
                    expect(blank_drawer).to_be_hidden(timeout=self.timeout)
                    if not move_out_button.is_visible():
                        space_settings.click()
                    move_out_button.click()
                    try:
                        expect(intent_next).to_be_visible(timeout=self.timeout)
                    except AssertionError:
                        logging.warning(
                            "Skipping Space %s: the move-out drawer opened blank "
                            "twice (no Intent to Move-Out content)",
                            space_number,
                        )
                        return False

        with allure.step("Review the move-out statement"):
            self.page.get_by_role("button", name="Next", exact=True).click()
            self.page.get_by_role(
                "button", name="Review Move-Out Statement", exact=True
            ).click()

        with allure.step(f"Confirm move-out reason: {reason}"):
            self.page.get_by_role(
                "button", name="Select Reason for Move Out", exact=True
            ).click()
            # Scoped to the dropdown's option role - a plain text/div match
            # here can also hit unrelated "Reason: <reason>" text in this
            # tenant's older move-out notes elsewhere on the page.
            reason_option = self.page.get_by_role(
                "option", name=reason, exact=True
            )
            no_reasons_available = self.page.get_by_text(
                "No data available", exact=True
            )
            try:
                expect(reason_option).to_be_visible(timeout=self.timeout)
            except AssertionError:
                if (
                    no_reasons_available.count() > 0
                    and no_reasons_available.first.is_visible()
                ):
                    logging.warning(
                        "Skipping Space %s: move-out reasons failed to load "
                        'for this lease ("No data available" in the reasons '
                        "dropdown)",
                        space_number,
                    )
                    self._cancel_move_out_drawer()
                    return False
                raise
            reason_option.click()

            move_out_drawer = self.page.locator(".v-navigation-drawer.move_out")
            skip_payment = self.page.get_by_text("Skip Payment", exact=True)
            # Take Payment is the top-level radio (alongside Skip Payment and
            # Write Off) that must be selected before its "Cash" sub-option
            # even exists in the DOM - gate on Take Payment's own presence
            # rather than Cash's, which can otherwise never appear if it's
            # only checked for before Take Payment has been selected.
            take_payment = self.page.get_by_role(
                "radio", name="Take Payment", exact=True
            )
            cash_button = self.page.get_by_role(
                "radio", name="Cash", exact=True
            )
            refund_button = self.page.get_by_role("button").filter(
                has_text=re.compile(r"Refunds")
            )
            # The Charges panel only auto-expands when there's an actual
            # balance due; at $0.00 it stays collapsed and hides Skip
            # Payment, so expand it ourselves when neither option is
            # visible yet.
            charges_panel = self.page.get_by_role(
                "button", name=re.compile(r"^Charges")
            )
            if (
                charges_panel.count() > 0
                and charges_panel.first.is_visible()
                and not (take_payment.count() > 0 and take_payment.first.is_visible())
                and not (skip_payment.count() > 0 and skip_payment.first.is_visible())
            ):
                charges_panel.first.click()
            payment_option_found = self._wait_for_payment_option_or_none_needed(
                move_out_drawer, take_payment, skip_payment, refund_button
            )
            if payment_option_found is None:
                logging.warning(
                    "Skipping Space %s: the move-out drawer closed "
                    "unexpectedly after selecting the reason (a client-side "
                    "error in the application for this lease)",
                    space_number,
                )
                return False

            # Cash/Skip Payment (the outstanding-charges choice) and the
            # Refunds toggle below are independent panels that can both be
            # present at once, so each is handled whenever it applies rather
            # than treating them as mutually exclusive.
            
            if skip_payment.count() > 0 and skip_payment.first.is_visible():
                with allure.step("Select skip payment"):
                    skip_payment.first.click()

            elif take_payment.count() > 0 and take_payment.first.is_visible():
                            with allure.step("Select cash when available"):
                                if not take_payment.first.is_checked():
                                    self._mouse_click(take_payment.first)
                                # Selecting Take Payment expands the panel to reveal
                                # Cash/Credit/ACH/Check - clicking Cash immediately can
                                # land at coordinates from mid-expansion, registering no
                                # selection at all. Wait for it to become visible (the
                                # expansion settled) and confirm the click actually
                                # checked it rather than assuming it landed.
                                expect(cash_button.first).to_be_visible(timeout=self.timeout)
                                for _ in range(5):
                                    self._mouse_click(cash_button.first)
                                    if cash_button.first.is_checked():
                                        break
                                    self.page.wait_for_timeout(300)
                                else:
                                    raise AssertionError(
                                        "Cash radio never became checked after clicking it"
                                    )

            if refund_button.count() > 0 and refund_button.first.is_visible():
                refund_switch = refund_button.first.get_by_role("switch")
                if refund_switch.count() > 0 and refund_switch.first.is_checked():
                    with allure.step("Disable refund"):
                        refund_switch.first.click(force=True)
            self._close_live_agent_notification()
            move_out_confirm_button = self.page.locator(
                'button[name="QA-MoveOutStatementIndex-hb-primary-button-Move-Out"]'
            )
            # Same class of client-side error _wait_for_payment_option_or_none_needed
            # guards against, just later in the flow: the drawer can still close
            # itself unexpectedly after the payment/refund step, before this final
            # button ever renders. Without this check that hangs the full timeout
            # then crashes the whole test instead of skipping this one tenant.
            try:
                expect(move_out_confirm_button).to_be_visible(timeout=self.timeout)
            except AssertionError:
                logging.warning(
                    "Skipping Space %s: the move-out drawer closed unexpectedly "
                    "after the payment/refund step, before the final Move Out "
                    "button appeared (a client-side error in the application "
                    "for this lease)",
                    space_number,
                )
                return False
            self._mouse_click(move_out_confirm_button)
            self._mouse_click(
                self.page.get_by_role("button", name="Confirm", exact=True)
            )

        with allure.step("Confirm the move-out was applied"):
            move_out_drawer = self.page.locator(".v-navigation-drawer.move_out")
            if self._wait_for_move_out_drawer_closed(move_out_drawer):
                with allure.step("Return to the previous page after move out"):
                    self.page.locator("a").filter(
                        has_text="Back to Previous Page"
                    ).click()
                return True

        with allure.step(
            f"Known issue: Space {space_number} did not complete the "
            "move-out - cancelling and skipping"
        ):
            logging.warning(
                "Skipping Space %s: the application did not complete the "
                "move-out (for example, an 'Invoice ID not set' error, or "
                "a stalled refund) - see the drawer state in the attached "
                "screenshot if this test ultimately fails",
                space_number,
            )
            self._cancel_move_out_drawer()
        return False

    @log_method_exceptions
    def _cancel_move_out_drawer(self) -> None:
        move_out_drawer = self.page.locator(".v-navigation-drawer.move_out")
        move_out_drawer.get_by_text("Cancel", exact=True).click()
        expect(move_out_drawer).to_be_hidden(timeout=self.timeout)

    @log_method_exceptions
    def _wait_for_payment_option_or_none_needed(
        self,
        move_out_drawer: Locator,
        take_payment: Locator,
        skip_payment: Locator,
        refund_button: Locator,
    ) -> bool | None:
        # Returns True if a Take Payment/Skip Payment/Refunds option
        # appeared, False if the drawer stayed open with none of them
        # needed (charges and refund both $0.00, so there's nothing to
        # pick), or None if the drawer closed unexpectedly (a client-side
        # application error).
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if take_payment.count() > 0 and take_payment.first.is_visible():
                return True
            if skip_payment.count() > 0 and skip_payment.first.is_visible():
                return True
            if refund_button.count() > 0 and refund_button.first.is_visible():
                return True
            if not move_out_drawer.is_visible():
                return None
            self.page.wait_for_timeout(waits().poll_interval)

        return None if not move_out_drawer.is_visible() else False

    @log_method_exceptions
    def _wait_for_move_out_drawer_closed(self, move_out_drawer: Locator) -> bool:
        # A handful of distinct application-side errors (Invoice ID not set,
        # a stalled security-deposit refund, ...) all manifest the same way:
        # the drawer just never closes. Rather than chase each one by its
        # specific error text, treat "still open after the full timeout" as
        # a known-issue skip generically.
        deadline = time.monotonic() + self.timeout / 1000
        while time.monotonic() < deadline:
            if not move_out_drawer.is_visible():
                return True
            self.page.wait_for_timeout(waits().poll_interval)
        return False
