import re
import time
from collections.abc import Callable

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import first_visible, log_method_exceptions


class MPUnitSearchPage:
    """MP storefront: search a facility and select an available unit.
    Shared entry point for both the Legacy and 2-Step reservation flows -
    which flow a selected unit lands on is decided by Hummingbird's
    "Enable 2-Step Rental" setting (see MPFMSInitialSetupPage), not by
    anything on this page."""

    @log_method_exceptions
    def __init__(self, page: Page, base_url: str, timeout: float) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout = timeout

    @log_method_exceptions
    def open_storefront(self) -> None:
        with allure.step("Open MP storefront"):
            self.page.goto(self.base_url, wait_until="domcontentloaded")
            self._dismiss_banners()

    @log_method_exceptions
    def open_property_page(self, url: str) -> None:
        """Navigates straight to a known property landing page URL
        (e.g. captured from an earlier search_storage_location() call's
        own page.url - see the property_landing_page_url fixture in
        conftest.py) instead of repeating the state/city click-through
        search. Confirmed live (2026-09-08, stage, mobile viewport):
        that click-through has been observed landing on a bare "N
        Locations found near" search-results page instead of the
        intended property - a mobile-specific instance of the same
        storefront routing flakiness search_storage_location's own
        docstring documents for desktop. A direct goto to an already-
        known-good URL sidesteps the click chain entirely rather than
        working around it."""
        with allure.step(f"Open property page directly: {url}"):
            self.page.goto(url, wait_until="domcontentloaded")
            self._dismiss_banners()

    @log_method_exceptions
    def _dismiss_banners(self) -> None:
        """Dismisses every popup/banner confirmed live on the storefront
        that can otherwise intercept clicks on the real page underneath:
        the Termly cookie-consent dialog (its own "Accept" button, a
        distinct element from the site's simpler cookie banner below),
        the site's own cookie banner, a promo banner's "×" close, the
        "President's Day Sale" ribbon's own close icon, and the
        "AI Customer Service" chat widget (confirmed live, 2026-09-08:
        loads inside its own iframe, title="Chatbot", and auto-opens
        expanded on page load rather than starting collapsed - its
        ".chat-window-close-btn" is the only way to collapse it back).
        Cookie banners and the chat widget in particular were observed
        reappearing after navigating to a new page within the same
        session, not just on first load - callers that navigate mid-flow
        (e.g. search_storage_location) call this again rather than
        assuming once is enough."""
        cookie_dialog_accept = self.page.get_by_role(
            "alertdialog", name="Cookie Consent Prompt"
        ).get_by_role("button", name="Accept", exact=True)
        if cookie_dialog_accept.count() > 0 and cookie_dialog_accept.first.is_visible():
            cookie_dialog_accept.first.click()

        # Termly's "Cookie Consent Manager" bar (Preferences / Decline /
        # Accept) - confirmed live (2026-09-15, stage/Garden Grove): it
        # covers the bottom of the tier-selection dialog, right over the
        # tier's "Select" button, and isn't the alertdialog above. Declined
        # like MPTwoStepReservationFormPage._dismiss_cookie_banner; the
        # dialog has no "Decline" button, so this is safe while it's open.
        termly_banner = self.page.get_by_text("Cookie Consent Manager", exact=False).first
        if termly_banner.count() > 0 and termly_banner.is_visible():
            decline = self.page.get_by_role("button", name="Decline", exact=True)
            if decline.count() > 0 and decline.first.is_visible():
                decline.first.click()

        # Mobile-only cookie banner. Skip while a real dialog (e.g. tier
        # modal) is open — confirmed 2026-09-17: clicking Accept under
        # tier-section-modal-mobile times out (dialog intercepts pointer).
        mobile_cookie_popup = self.page.locator(".cookie-content-wrapper.mobile-popup")
        dialog_open = self.page.get_by_role("dialog").count() > 0
        if (
            not dialog_open
            and mobile_cookie_popup.count() > 0
            and mobile_cookie_popup.first.is_visible()
        ):
            mobile_accept = mobile_cookie_popup.first.locator(".okay-button-mobile")
            if mobile_accept.count() > 0 and mobile_accept.first.is_visible():
                mobile_accept.first.click()
            else:
                mobile_cookie_popup.first.locator(".icon-close-white").first.click()

        # The generic "×"/"Accept" text matches below are page-wide and
        # unscoped - safe when only a banner is up, but the storefront's
        # own in-flow modals (unit tier-selection, etc, role="dialog")
        # reuse the exact same "×" close-icon pattern for their own close
        # control. Confirmed live (2026-09-08, stage): calling this while
        # one of those dialogs is legitimately open closes *that* dialog
        # instead of a banner - skip both while any dialog is up rather
        # than risk dismissing real in-progress UI.
        if self.page.get_by_role("dialog").count() == 0:
            for banner_close in (
                self.page.get_by_text("×⚠️ Storage Outlet Company", exact=False),
                self.page.get_by_text("×", exact=True),
            ):
                if banner_close.count() > 0 and banner_close.first.is_visible():
                    banner_close.first.click()

            cookie_accept = self.page.get_by_text("Accept", exact=True)
            if cookie_accept.count() > 0 and cookie_accept.first.is_visible():
                cookie_accept.first.click()

        chat_widget_close = self.page.frame_locator(
            'iframe[title="Chatbot"]'
        ).locator(".chat-window-close-btn")
        if chat_widget_close.count() > 0 and chat_widget_close.first.is_visible():
            chat_widget_close.first.click()

    @log_method_exceptions
    def _open_storage_locations(self) -> None:
        """Navigates straight to the Storage Locations page by URL rather
        than clicking the header's "Storage Locations" link - confirmed
        live (2026-09-08, stage) that click lands on/near a hover
        mega-menu the nav renders for that same link (which duplicates
        state names like "California" into the nav banner itself) instead
        of triggering the real navigation: the URL and #main-content are
        left unchanged on the home page, so every state/city lookup
        scoped to #main-content afterwards finds nothing, no matter how
        long it retries."""
        self.page.goto(
            f"{self.base_url}/storage-units/locations/", wait_until="domcontentloaded"
        )
        self._dismiss_banners()

    @log_method_exceptions
    def _wait_visible(self, locator, timeout: float | None = None) -> None:
        """expect(locator).to_be_visible(), but re-runs _dismiss_banners()
        throughout the wait rather than only once beforehand - the cookie
        dialog and chat widget have both been observed rendering
        asynchronously partway through a wait (not just on load), sitting
        on top of the real page and leaving the SPA's own navigation
        looking like it silently never happened underneath."""
        timeout = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout / 1000
        poll_timeout_ms = 2000
        while True:
            self._dismiss_banners()
            remaining_ms = (deadline - time.monotonic()) * 1000
            if remaining_ms <= 0:
                expect(locator).to_be_visible(timeout=1)
                return
            try:
                expect(locator).to_be_visible(timeout=min(poll_timeout_ms, remaining_ms))
                return
            except AssertionError:
                continue

    @log_method_exceptions
    def _click_until_gone(self, click_locator, gone_locator, timeout: float | None = None) -> None:
        """Clicks click_locator, then waits for gone_locator to
        disappear - re-clicking on every retry, same click-can-silently
        drop reasoning as _click_until_visible, for actions whose success
        signal is something closing (e.g. the tier-selection dialog)
        rather than something new appearing."""
        timeout = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout / 1000
        poll_timeout_ms = 2000
        while True:
            self._dismiss_banners()
            remaining_ms = (deadline - time.monotonic()) * 1000
            if remaining_ms <= 0:
                expect(gone_locator).to_be_hidden(timeout=1)
                return
            if gone_locator.count() > 0:
                # Bounded so a click that never resolves/registers can't
                # swallow the entire remaining budget in one attempt -
                # leaves room to actually retry within the deadline.
                try:
                    click_locator.click(timeout=min(poll_timeout_ms, remaining_ms))
                except Exception:
                    pass
            remaining_ms = (deadline - time.monotonic()) * 1000
            if remaining_ms <= 0:
                expect(gone_locator).to_be_hidden(timeout=1)
                return
            try:
                expect(gone_locator).to_be_hidden(timeout=min(poll_timeout_ms, remaining_ms))
                return
            except AssertionError:
                continue

    @log_method_exceptions
    def _click_until_visible(self, click_locator, wait_locator, timeout: float | None = None) -> None:
        """Clicks click_locator, then waits for wait_locator to render -
        re-clicking click_locator on every retry rather than clicking
        once and only re-checking. Confirmed live (2026-09-08, stage):
        clicking a state (e.g. "California") to expand its city list is
        intermittently a no-op - no error is raised, the click is
        accepted, but the state list never expands - roughly 1 in a few
        attempts, with no overlay or banner involved. A single click
        can't be told apart from a dropped one, so the only reliable
        recovery is to click again rather than just waiting longer."""
        timeout = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout / 1000
        poll_timeout_ms = 2000
        while True:
            self._dismiss_banners()
            remaining_ms = (deadline - time.monotonic()) * 1000
            if remaining_ms <= 0:
                expect(wait_locator).to_be_visible(timeout=1)
                return
            if wait_locator.count() == 0:
                # Bounded so a click that never resolves/registers can't
                # swallow the entire remaining budget in one attempt -
                # leaves room to actually retry within the deadline.
                try:
                    click_locator.click(timeout=min(poll_timeout_ms, remaining_ms))
                except Exception:
                    pass
            remaining_ms = (deadline - time.monotonic()) * 1000
            if remaining_ms <= 0:
                expect(wait_locator).to_be_visible(timeout=1)
                return
            try:
                expect(wait_locator).to_be_visible(timeout=min(poll_timeout_ms, remaining_ms))
                return
            except AssertionError:
                continue

    @log_method_exceptions
    def search_storage_location(self, state: str, city: str) -> None:
        """Confirmed live (2026-09-07, stage): on the state-overview page,
        each state (e.g. "California") is plain clickable text, not an
        ARIA heading/link - matched by exact text, scoped to
        "#main-content" since the nav header can render its own duplicate
        of the same text (e.g. a hover dropdown), which would otherwise
        make an unscoped exact-text match ambiguous. Once a state is
        selected, each city/property is a real link (its display text is
        rendered upper-case, e.g. "GARDEN GROVE"), matched by role with a
        case-insensitive substring name so the caller's own casing
        doesn't have to match exactly."""
        with allure.step(f"Search storage location: {city}, {state}"):
            slug_state = re.sub(r"\s+", "-", state.strip().lower())
            slug_city = re.sub(r"\s+", "-", city.strip().lower())
            city_slug_path = f"/{slug_state}/{slug_city}/"

            self._open_storage_locations()
            main_content = self.page.locator("#main-content")
            state_link = main_content.get_by_text(state, exact=True)
            self._wait_visible(state_link.first)
            # The property link shares its visible text with the bare
            # city-aggregator link above, but always has an extra path
            # segment beyond the city slug - .and_(), not a fresh
            # CSS-only locator, since this codebase also has CSS-hidden
            # duplicate elements sharing the exact same href as their
            # visible counterpart (mobile/desktop variants of the same
            # card), and searching by href alone can land .first on the
            # hidden duplicate instead of the one text_link (role +
            # accessible name) reliably resolves to visible.
            text_link = self.page.get_by_role("link", name=city, exact=False)
            property_link = text_link.and_(
                self.page.locator(
                    f'a[href*="{city_slug_path}"]:not([href$="{city_slug_path}"])'
                )
            )
            self._click_until_visible(state_link.first, text_link.first)
            city_link = property_link if property_link.count() > 0 else text_link

            # Confirmed live (2026-09-08, stage): clicking this link
            # (a client-side SPA route change, not a real navigation)
            # has been observed landing on the bare "/storage-units/
            # {state}/{city}/" aggregator page - a "N Locations found
            # near" search-results page listing unrelated nearby
            # properties - instead of the specific property. Root
            # cause: self.page.url read shortly after the click can
            # still show the pre-click URL, since the SPA's own route
            # update is asynchronous and nothing here structurally
            # waits for it - the exact same class of race
            # MPUnitSearchPage._wait_visible's own docstring documents
            # elsewhere for banners reappearing mid-wait. This link's
            # href is already resolved above to specifically the
            # property (not the bare aggregator, via the CSS
            # href-suffix exclusion) - a real page.goto() straight to
            # that href sidesteps the click/route race entirely,
            # rather than clicking and hoping the SPA's own router
            # lands where its href already says it will.
            href = city_link.first.get_attribute("href")
            if not href:
                city_link.first.click()
                self._dismiss_banners()
                return
            target_url = href if href.startswith("http") else f"{self.base_url}{href}"
            self.page.goto(target_url, wait_until="domcontentloaded")
            self._dismiss_banners()

    @log_method_exceptions
    def select_first_available_location(self) -> None:
        """Discovers and opens the first state + first city/property
        listed on the Storage Locations page, without needing to know
        either in advance - lets a test run against whatever a given
        environment actually has configured, instead of hardcoding a
        specific property."""
        with allure.step("Select the first available storage location"):
            self._open_storage_locations()
            main_content = self.page.locator("#main-content")
            # Each state entry is a plain clickable text node holding a
            # count and the state name as two separate children (e.g.
            # "5" + "California") - the state name is whichever of those
            # isn't purely numeric.
            state_candidates = main_content.locator("main, [class]").get_by_text(
                re.compile(r"^[A-Za-z][A-Za-z .]*$")
            )
            self._wait_visible(state_candidates.first)
            state_candidates.first.click()
            self._dismiss_banners()

            city_link = self.page.get_by_role("link").filter(
                has=self.page.locator(":visible")
            )
            self._wait_visible(city_link.first)
            city_link.first.click()

    @log_method_exceptions
    def search_from_locations_page(self, query: str) -> None:
        """Old Robot suite's "Click the Storage Locations link on the
        Header" + "Select City To Find": the Storage Locations page's own
        "ZIP or City, State" box (#pac-input), submitted with Enter,
        landing on /storage-units/?address=... with "N Locations found
        near:". Confirmed live (2026-09-12, uat_storoutlet): the home
        page's identically-id'd box is a bare <form> with no submit
        handler, so Enter there just reloads "/?"; and the search icon
        next to either box ignores the typed text and searches the
        browser's geolocation instead - hence the address check below.
        This box is also pre-filled after load with an IP-based location
        (e.g. "Bengaluru, Karnataka" - why the old Robot keyword cleared
        it first), which in a fresh browser can land after the query was
        typed and before Enter took effect, leaving the page unchanged -
        so fill + Enter is retried until the results page appears."""
        with allure.step(f"Search storage locations: {query}"):
            self._open_storage_locations()
            search_box = first_visible(
                self.page.locator("#main-content").locator("#pac-input")
            )
            self._wait_visible(search_box)
            found = self.page.get_by_text(re.compile(r"\d+ Locations? found near")).first
            max_attempts = 3
            for attempt in range(max_attempts):
                self._dismiss_banners()
                search_box.fill(query)
                expect(search_box).to_have_value(query, timeout=self.timeout)
                search_box.press("Enter")
                try:
                    self._wait_visible(found, timeout=self.timeout / max_attempts)
                    break
                except AssertionError:
                    if attempt == max_attempts - 1:
                        raise
            city = query.split(",")[0].strip()
            expect(self.page).to_have_url(
                re.compile(r"address=" + re.escape(city).replace(r"\ ", "(%20|\\+| )"), re.IGNORECASE)
            )

    @log_method_exceptions
    def locations_found_count(self) -> int:
        found = self.page.get_by_text(re.compile(r"\d+ Locations? found near")).first
        expect(found).to_be_visible(timeout=self.timeout)
        return int(re.search(r"\d+", found.inner_text()).group())

    @log_method_exceptions
    def location_card(self, name_contains: str):
        # Each search result is a div.location-container holding the
        # distance, the property name (an <h2>), address, phone and "BEST
        # PRICE* $x WEB RATE" - confirmed live (2026-09-12, uat_storoutlet).
        return (
            self.page.locator(".location-container")
            .filter(
                has=self.page.get_by_role(
                    "heading", name=re.compile(re.escape(name_contains), re.IGNORECASE)
                )
            )
            .first
        )

    @log_method_exceptions
    def open_location_from_results(self, name_contains: str) -> None:
        """Confirmed live (2026-09-12, uat_storoutlet): the result card has
        no link of its own (its only anchor is the phone number) and the
        same overlapping content block intercepts a real click on it - a
        click event dispatched on the card itself is what opens the
        property page."""
        with allure.step(f"Open location from search results: {name_contains}"):
            card = self.location_card(name_contains)
            expect(card).to_be_visible(timeout=self.timeout)
            results_url = self.page.url
            card.dispatch_event("click")
            expect(self.page).not_to_have_url(results_url, timeout=self.timeout)
            self._dismiss_banners()

    @log_method_exceptions
    def assert_unit_size_sections_listed(self) -> None:
        """The facility landing page renders under one of two live,
        HB-configurable layouts (Settings > Website > FMS Initial Setup >
        Landing Page Layout): "List View" - one category card
        (".size-wrapper") per store type, each with a "Select Size:" chip
        picker and a single CTA button that updates to match whichever
        chip is active - or "Grid View" - an accordion per store type
        ("...See what fits") listing every unit inline, each with its own
        always-visible "Select ... unit" button. Checks below accept
        either rendering rather than assuming one. List View additionally
        duplicates its chip picker for mobile (".feature-block-list",
        CSS-hidden on desktop) alongside the desktop copy
        (".details-block") - both present in the DOM at once - so the
        List View checks are scoped to ".details-block" rather than
        risking an unqualified match landing on the hidden mobile copy."""
        with allure.step("Assert unit-size sections with available counts are listed"):
            list_view = self.page.locator(".size-wrapper").count() > 0

            size_section = self.page.get_by_text(
                re.compile(r"^(X-Small|Small|Medium|Large|X-Large)$")
            ).first
            accordion_section = self.page.get_by_role(
                "button",
                name=re.compile(r"(X-Small|Small|Medium|Large|X-Large)\s+See what fits"),
            ).first
            # .first on the union too: in Grid View the "X-Small" <span>
            # sits inside its own accordion button, so both halves match
            # (confirmed live 2026-09-13, uat_storoutlet/Bellflower).
            expect(size_section.or_(accordion_section).first).to_be_visible(timeout=self.timeout)

            controls = self.page.locator(".details-block") if list_view else self.page
            if list_view:
                select_size_prompt = controls.get_by_text(
                    "Select Size:", exact=True
                ).first
                expect(select_size_prompt).to_be_visible(timeout=self.timeout)
            select_unit_button = controls.get_by_role(
                "button", name=re.compile(r"^Select .+ unit")
            ).first
            expect(select_unit_button).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_facility_landing_page_content(self) -> None:
        with allure.step("Assert key facility landing page content is present"):
            expect(
                self.page.get_by_role("heading", name=re.compile(r"Storage (Units|Outlet)"))
                .first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_unit_details_in_lease_summary(self) -> None:
        """first_visible throughout: this sidebar is also duplicated for
        mobile/desktop, and unlike the unit-size selector, an unqualified
        ".first" here can land on the hidden copy rather than the live
        one."""
        with allure.step("Assert unit details are shown in the Lease Summary sidebar"):
            lease_summary = first_visible(
                self.page.get_by_text("Lease Summary", exact=True)
            )
            expect(lease_summary).to_be_visible(timeout=self.timeout)
            expect(
                first_visible(self.page.get_by_text(re.compile(r"per month")))
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def change_space(self) -> None:
        with allure.step("Change Space: return to the unit listing"):
            change_space_link = self.page.get_by_role(
                "link", name="Change Space"
            ).first
            expect(change_space_link).to_be_visible(timeout=self.timeout)
            change_space_link.click()
            expect(
                self.page.get_by_role(
                    "button", name=re.compile(r"^Select .+ unit")
                ).first
            ).to_be_visible(timeout=self.timeout)

    def _reservation_form_cta(self):
        """Legacy Reserve This Space / Submit, or Two-Step Reserve Now."""
        return (
            self.page.get_by_role("button", name="Reserve This Space", exact=True)
            .or_(self.page.get_by_role("button", name="Reserve Now", exact=True))
            .or_(self.page.get_by_role("button", name="Submit", exact=True))
        )

    def _space_no_longer_available(self):
        """Waitlist / hold-lost page heading (Default Select often lands here)."""
        return self.page.get_by_role(
            "heading", name=re.compile(r"Space No Longer Available", re.I)
        )

    def _recover_from_space_no_longer_available(self) -> bool:
        """Default Select can open /rent_or_reserve/ with Lease Summary
        still showing but the chosen unit already gone (walked 2026-09-16
        stage/Garden Grove). Prefer a Suggested-spaces Select (same page)
        before backing out to the listing for the next category unit."""
        self._dismiss_banners()
        space_gone = self._space_no_longer_available()
        if not (space_gone.count() and space_gone.first.is_visible()):
            return self._reservation_form_ready()

        suggested = self.page.get_by_role(
            "heading", name=re.compile(r"Suggested spaces", re.I)
        )
        if suggested.count() and suggested.first.is_visible():
            selects = self.page.get_by_role("button", name="Select", exact=True)
            for index in range(selects.count()):
                button = selects.nth(index)
                if not (button.is_visible() and button.is_enabled()):
                    continue
                with allure.step(
                    f"Try Suggested spaces Select #{index + 1}"
                ):
                    self._dismiss_banners()
                    button.click()
                    try:
                        expect(
                            self._reservation_form_cta()
                            .first.or_(space_gone.first)
                            .first
                        ).to_be_visible(timeout=min(30_000, self.timeout))
                    except AssertionError:
                        continue
                    if self._reservation_form_ready():
                        return True
                    if not (space_gone.count() and space_gone.first.is_visible()):
                        break

        change_space = self.page.get_by_role("link", name="Change Space")
        if change_space.count() and change_space.first.is_visible():
            try:
                change_space.first.click()
                self.page.wait_for_load_state("domcontentloaded")
                return False
            except Exception:
                pass
        try:
            self.page.go_back(wait_until="domcontentloaded")
        except Exception:
            self.page.reload(wait_until="domcontentloaded")
        return False

    def _reservation_form_ready(self) -> bool:
        """True when a real reserve CTA is up and Space No Longer Available
        is not. Lease Summary alone is not enough - the waitlist page also
        renders Lease Summary beside the gone-space heading."""
        if self._space_no_longer_available().count() and self._space_no_longer_available().first.is_visible():
            return False
        cta = self._reservation_form_cta()
        return bool(cta.count() and cta.first.is_visible())

    @log_method_exceptions
    def _unit_selection_succeeded(self, select_button) -> bool:
        """Clicks select_button (retrying the click itself, not just
        waiting - confirmed live 2026-09-08, stage: this button's click
        is intermittently a no-op, same unexplained behavior as the
        state-search click _click_until_visible retries around). Even a
        click that does register can still lose its live inventory in
        the gap before the tier-confirmation dialog opens - observed
        live as an inline "Sorry, This space is no longer available."
        notice, or a "Some error occured" message inside the dialog
        itself. Returns whether the tier dialog opened cleanly; on
        failure, dismisses whatever error surfaced (via "Back to Search"
        or the dialog's close control) so the next candidate starts from
        a clean listing.

        Default Landing Page Layout (walked 2026-09-16 stage/Garden Grove)
        can skip the tier dialog entirely and navigate straight to
        /rent_or_reserve/ - only counts as success when a Reserve CTA is
        present, not when Lease Summary sits next to Space No Longer
        Available (waitlist / suggested-spaces page)."""
        # Desktop and mobile render this same dialog with different
        # copy in different elements - confirmed live (2026-09-08,
        # stage): desktop's "Select the space best fitting your needs!"
        # is a real <h2>, but mobile's "Select the feature level best
        # fitting your needs!" is a plain <span> with no heading role at
        # all, so get_by_role("heading", ...) can never match it - text
        # matched directly instead, which works against either element.
        # Handled dynamically rather than as two separate desktop/mobile
        # code paths, same as this file already handles Grid/List/
        # Default Landing Page Layout variants.
        tier_dialog_heading = self.page.get_by_text(
            re.compile(r"^Select the (space|feature level) best fitting your needs!$"),
        )
        unavailable_notice = self.page.get_by_text(
            re.compile(r"no longer available|Some error occured", re.IGNORECASE)
        )
        lease_summary = self.page.get_by_text("Lease Summary", exact=True)
        space_gone = self._space_no_longer_available()
        reserve_cta = self._reservation_form_cta()
        try:
            self._click_until_visible(
                select_button,
                tier_dialog_heading.or_(unavailable_notice)
                .or_(lease_summary)
                .or_(space_gone)
                .or_(reserve_cta)
                .first,
            )
        except AssertionError:
            # Confirmed live (2026-09-15, stage/Garden Grove): the Select
            # button can sit in its loading state for the whole minute with
            # neither the tier dialog nor an error ever showing - treated
            # like an unavailable unit (page reloaded, next candidate tried)
            # rather than failing the whole case.
            if space_gone.count() and space_gone.first.is_visible():
                return self._recover_from_space_no_longer_available()
            if self._reservation_form_ready():
                return True
            allure.attach(
                self.page.screenshot(full_page=True),
                name="Select stuck loading - trying the next unit",
                attachment_type=allure.attachment_type.PNG,
            )
            self.page.reload(wait_until="domcontentloaded")
            return False

        # Default Select race: /rent_or_reserve/ + Lease Summary can paint
        # before the Space No Longer Available heading - brief settle.
        if "/rent_or_reserve/" in self.page.url or (
            lease_summary.count() and lease_summary.first.is_visible()
        ):
            self.page.wait_for_timeout(750)
            if space_gone.count() and space_gone.first.is_visible():
                return self._recover_from_space_no_longer_available()
            if self._reservation_form_ready():
                return True
            try:
                expect(reserve_cta.first).to_be_visible(
                    timeout=min(15_000, self.timeout)
                )
            except AssertionError:
                pass
            if self._reservation_form_ready():
                return True
            if space_gone.count() and space_gone.first.is_visible():
                return self._recover_from_space_no_longer_available()
            try:
                self.page.go_back(wait_until="domcontentloaded")
            except Exception:
                self.page.reload(wait_until="domcontentloaded")
            return False

        if space_gone.count() and space_gone.first.is_visible():
            return self._recover_from_space_no_longer_available()

        if tier_dialog_heading.is_visible():
            # User request (2026-09-13): skip units whose tier dialog warns
            # of low stock - "Only 1 left - Rent soon!" / "Only 5 left -
            # Rent soon!", confirmed live on uat_storoutlet/Bellflower as
            # div.space-availability-desktop. A last unit is easily still
            # held by an earlier run (hold -> 400 SpaceHeld). select_unit
            # clears this flag for a second pass only when every unit
            # carries the warning.
            low_stock_warning = first_visible(
                self.page.get_by_role("dialog").get_by_text(
                    re.compile(r"Only \d+ left", re.IGNORECASE)
                )
            )
            if getattr(self, "_skip_low_stock_units", False) and low_stock_warning.is_visible():
                with allure.step(
                    f"Skip low-stock unit "
                    f"({low_stock_warning.inner_text().strip()}); try next"
                ):
                    self._tier_dialog_close().click()
                    expect(tier_dialog_heading.first).to_be_hidden(timeout=self.timeout)
                return False
            return True

        back_to_search = self.page.get_by_role("button", name="Back to Search")
        if back_to_search.count() > 0 and back_to_search.first.is_visible():
            back_to_search.first.click()
        else:
            close_dialog = self._tier_dialog_close()
            if close_dialog.count() > 0 and close_dialog.is_visible():
                close_dialog.click()
        return False

    @log_method_exceptions
    def _tier_dialog_close(self):
        """The tier dialog's close control: a.close-icon on both layouts -
        desktop exposes it as link "×", but the mobile dialog has no "×"
        link or button at all (confirmed live 2026-09-14, uat_storoutlet/
        Bellflower at 390x844, where it also reads "Only 1 left!")."""
        return (
            self.page.locator("a.close-icon")
            .or_(self.page.get_by_role("link", name="×", exact=True))
            .filter(visible=True)
            .first
        )

    @log_method_exceptions
    def _select_available_unit_in_list_view_category(self, category) -> bool:
        """List View: try every size chip in one store-type category card
        (".size-wrapper"), in listed order, looking for one that leaves a
        real "Select ... unit" CTA in place rather than "Join Waitlist".
        The chips/CTA live in ".details-block" on desktop - the card also
        renders a mobile-only duplicate, CSS-hidden on desktop, that must not
        be interacted with there. On a phone it's the other way round
        (confirmed live 2026-09-15, uat_storoutlet/Chula Vista at 390x844):
        ".details-block" is hidden and the same chip ("5' x 5'") and CTA
        ("Select 5' x 5' unit, ...") render in ".feature-block"
        (".mobile-size-block" / ".mobile-amenities-block"), so whichever
        block is visible is used. Returns whether an available unit was
        found and selected."""
        desktop_controls = category.locator(".details-block")
        controls = (
            desktop_controls
            if desktop_controls.count() > 0 and desktop_controls.first.is_visible()
            else category.locator(".feature-block")
        )
        select_button = controls.get_by_role(
            "button", name=re.compile(r"^Select .+ unit")
        )
        cta_button = controls.get_by_role(
            "button", name=re.compile(r"^(Select .+ unit|Join Waitlist)")
        )
        size_chips = controls.get_by_role(
            "button", name=re.compile(r"^\d+'\s*x\s*\d+'")
        )

        for chip_index in range(size_chips.count()):
            size_chips.nth(chip_index).click()
            expect(cta_button).to_be_visible(timeout=self.timeout)
            if select_button.count() > 0 and select_button.is_visible():
                self._dismiss_banners()
                if self._unit_selection_succeeded(select_button):
                    return True
        return False

    @log_method_exceptions
    def _select_available_unit_in_grid_view_category(self, accordion_button) -> bool:
        """Grid View: a store-type's units are all listed inline under
        its accordion toggle, each with its own "Select ... unit" button
        - disabled rather than swapped to "Join Waitlist" when that unit
        has sold out online. Confirmed live (2026-09-08, stage): the
        toggle button's immediate parent is only its own "card-header"
        div (no units in there) - the card wrapping both the toggle and
        its listed units is one level further up, so that's the scope
        searched for a real, enabled Select button. Returns whether one
        was found and clicked."""
        category_wrapper = accordion_button.locator("xpath=../..")
        select_buttons = category_wrapper.get_by_role(
            "button", name=re.compile(r"^Select .+ unit")
        )
        for index in range(select_buttons.count()):
            button = select_buttons.nth(index)
            if button.is_enabled():
                self._dismiss_banners()
                if self._unit_selection_succeeded(button):
                    return True
        return False

    @log_method_exceptions
    def _select_available_unit_in_default_view_category(self, accordion_button) -> bool:
        """Default Landing Page Layout.

        Confirmed live 2026-09-08 (Hawaii): accordion like Grid View, but
        the toggle's accessible name is an aria-label such as
        \"X-Small - best price $44\" (not Grid's \"Click this arrow...\"),
        and sold-out units used \"a.check.btn\" links labeled Call / Text /
        Join Waitlist.

        Confirmed live 2026-09-16 stage/Garden Grove: available units under
        Default expose a plain enabled button named exactly \"Select\" (not
        Grid/List's \"Select ... unit\"), with \"$20 Admin Fee...\" under it.
        Expand the category when collapsed, try those Select buttons first,
        then fall back to any non-Call/Text/Join-Waitlist a.check.btn.
        """
        expanded = accordion_button.get_attribute("aria-expanded")
        if expanded == "false":
            accordion_button.click()
            self.page.wait_for_timeout(500)
        panel_id = accordion_button.get_attribute("aria-controls")
        category_wrapper = accordion_button.locator("xpath=../..")
        # Prefer the accordion panel named by aria-controls when present -
        # Default's unit cards (plain "Select" buttons) live there
        # (walked 2026-09-16 stage/Garden Grove).
        scope = (
            self.page.locator(f"[id='{panel_id}']")
            if panel_id
            else category_wrapper
        )
        if scope.count() == 0:
            scope = category_wrapper
        select_buttons = scope.get_by_role(
            "button", name=re.compile(r"Select For Price Details", re.I)
        ).or_(
            scope.get_by_role(
                "button", name=re.compile(r"^Select .+ unit", re.I)
            )
        ).or_(
            # Default (2026-09-16 Garden Grove): class base-button btn;
            # accessible name sometimes omits "Select" for get_by_role.
            scope.locator("button.base-button.btn").filter(
                has_text=re.compile(r"Select", re.I)
            )
        )
        for index in range(select_buttons.count()):
            button = select_buttons.nth(index)
            if button.is_enabled() and button.is_visible():
                self._dismiss_banners()
                if self._unit_selection_succeeded(button):
                    return True
        action_links = scope.locator("a.check.btn").or_(
            category_wrapper.locator("a.check.btn")
        )
        not_available_labels = {"Call", "Text", "Join Waitlist"}
        for index in range(action_links.count()):
            link = action_links.nth(index)
            if (link.text_content() or "").strip() in not_available_labels:
                continue
            self._dismiss_banners()
            if self._unit_selection_succeeded(link):
                return True
        return False

    @log_method_exceptions
    def select_unit(
        self,
        unit_type: str | None = None,
        protection_plan: str | None = None,
        on_value_tier_dialog: Callable[[Page], None] | None = None,
    ) -> tuple[str, str]:
        """Returns `(landing_page_layout, value_tier_layout)` - which of
        each pair of live layout variants (see below) actually rendered,
        so callers that configured a specific Landing Page Layout/Value
        Tier Layout beforehand can assert the storefront really used it,
        without needing to duplicate this method's own detection logic.

        Optional `on_value_tier_dialog` runs once the Value Tier dialog is
        visible (Grid or List) and before a protection plan is chosen -
        layout combination tests use it to screenshot that step.

        The facility landing page renders under one of three live,
        HB-configurable Landing Page Layout values (see
        assert_unit_size_sections_listed): "List View" (chip-per-size
        categories, ".size-wrapper"), "Grid View" (accordion-per-category
        with "Select ... unit" buttons, every unit listed inline), or
        "Default" (accordion-per-category with price aria-labels and
        plain "Select" buttons / a.check.btn links - see
        _select_available_unit_in_default_view_category). Which specific
        size - and even which store type (Small/Medium/Large/X-Large/
        Parking/Commercial) - actually supports online rental is decided
        by live inventory in all three layouts, not config, so unit_type
        is only a preference: every size in that category is tried
        first, and if the whole category is sold out, the same probe
        repeats against each remaining category in listed order. Leaving
        unit_type/protection_plan unset (the normal case - live inventory
        changes constantly, so pinning a preference just means more
        sold-out fallbacks) picks whichever category is first in listed
        order and accepts whichever tier is already selected by default,
        rather than searching for a specific name."""
        step_label = (
            f"Select an available unit, preferring the {unit_type} category"
            if unit_type
            else "Select an available unit"
        )
        with allure.step(step_label):
            # The facility landing page is a client-rendered SPA - right
            # after navigating in, none of ".size-wrapper" (List View),
            # a Grid View accordion button, or a Default View accordion
            # button (see below) has mounted yet, and every branch below
            # starts with a synchronous .count() that doesn't wait.
            # Without first waiting for some layout's own unit-size
            # heading, .count() can read 0 candidates from a still-empty
            # DOM and fail immediately instead of finding the units that
            # render a moment later.
            grid_view_heading = self.page.get_by_role(
                "button",
                name=re.compile(
                    r"^Click this arrow to collapse this accordion tab"
                ),
            )
            list_view_heading = self.page.locator(".size-wrapper")
            # Default View's toggle buttons don't expose the "Click this
            # arrow..." accessible name (an explicit aria-label overrides
            # it - see _select_available_unit_in_default_view_category),
            # so a stable aria-controls="accordion-..." wired to its
            # panel is used to detect it instead - but that same wiring
            # is reused sitewide for unrelated accordions (confirmed
            # live, 2026-09-08, mobile: office-hours/"Facility features"/
            # "BLOG" footer toggles all carry aria-controls="accordion-*"
            # too, with aria-label="Toggle section" - an unscoped match
            # latches onto those instead of any real unit category
            # whenever Grid View's own "Click this arrow..." toggle name
            # isn't present). Scoped to aria-label containing a price
            # (e.g. "X-Small - best price $44", per
            # _select_available_unit_in_default_view_category) since
            # that's specific to a real unit-category toggle.
            default_view_heading = self.page.locator(
                '[aria-controls^="accordion-"][aria-label*="$"]'
            )
            # _wait_visible, not a raw expect() - same reappearing-banner
            # risk _wait_visible's own docstring documents (confirmed
            # live, 2026-09-08, mobile: the Termly cookie dialog
            # reappearing after the property-page navigation immediately
            # before this call left the units section never mounting
            # underneath, timing out with no unit-size locator ever
            # found).
            self._wait_visible(
                grid_view_heading.first.or_(list_view_heading.first).or_(
                    default_view_heading.first
                ).first
            )

            list_view_categories = self.page.locator(".size-wrapper")
            grid_view_categories = self.page.get_by_role(
                "button",
                name=re.compile(
                    r"^Click this arrow to collapse this accordion tab"
                ),
            )
            if list_view_categories.count() > 0:
                candidates = list_view_categories
                is_preferred_category = (
                    lambda candidate: candidate.get_by_text(
                        unit_type, exact=True
                    ).count()
                    > 0
                )
                try_category = self._select_available_unit_in_list_view_category
                landing_page_layout = "List View"
            elif grid_view_categories.count() > 0:
                candidates = grid_view_categories
                is_preferred_category = (
                    lambda candidate: re.search(
                        rf"(?:^|\s){re.escape(unit_type)}(?:\s|$)",
                        candidate.inner_text(),
                    )
                    is not None
                )
                try_category = self._select_available_unit_in_grid_view_category
                landing_page_layout = "Grid View"
            else:
                candidates = default_view_heading
                # Default View's toggle carries the size/category name in
                # its aria-label (e.g. "X-Small - best price $44") rather
                # than in its own inner text.
                is_preferred_category = (
                    lambda candidate: unit_type.lower()
                    in (candidate.get_attribute("aria-label") or "").lower()
                )
                try_category = self._select_available_unit_in_default_view_category
                landing_page_layout = "Default"

            candidate_count = candidates.count()
            # No preference: take categories in listed order (index 0
            # first) rather than searching for a name match.
            preferred_index = (
                next(
                    (
                        index
                        for index in range(candidate_count)
                        if is_preferred_category(candidates.nth(index))
                    ),
                    0,
                )
                if unit_type
                else 0
            )
            ordered_indices = [preferred_index] + [
                index for index in range(candidate_count) if index != preferred_index
            ]

            # First pass skips low-stock units ("Only N left" - see
            # _unit_selection_succeeded); the second accepts them, so a
            # property where every unit is low on stock still gets one.
            for skip_low_stock in (True, False):
                self._skip_low_stock_units = skip_low_stock
                if any(try_category(candidates.nth(index)) for index in ordered_indices):
                    break
            else:
                raise AssertionError(
                    "No store type currently has a unit available for online "
                    "selection"
                )
            self._skip_low_stock_units = False

        tier_step_label = (
            f"Select {protection_plan} protection plan"
            if protection_plan
            else "Select protection plan"
        )
        with allure.step(tier_step_label):
            # Default Landing Page Layout can skip the Value Tier dialog
            # and land on /rent_or_reserve/ with Lease Summary already
            # showing the unit's tier (walked 2026-09-16 stage/Garden Grove).
            # Require a Reserve CTA - the waitlist page also shows Lease
            # Summary beside "Space No Longer Available".
            space_gone = self._space_no_longer_available()
            if space_gone.count() and space_gone.first.is_visible():
                if not self._recover_from_space_no_longer_available():
                    raise AssertionError(
                        "Storefront showed Space No Longer Available after unit "
                        "selection - no live inventory left to open a reservation"
                    )
            if self._reservation_form_ready() and self.page.get_by_role("dialog").count() == 0:
                return landing_page_layout, "n/a"
            if "/rent_or_reserve/" in self.page.url and self.page.get_by_role("dialog").count() == 0:
                # Form may still be painting after a successful Select.
                try:
                    expect(self._reservation_form_cta().first).to_be_visible(
                        timeout=min(15_000, self.timeout)
                    )
                except AssertionError:
                    pass
                if self._reservation_form_ready():
                    return landing_page_layout, "n/a"

            # The tier-selection dialog renders under one of two live,
            # HB-configurable layouts (Settings > Website > FMS Initial
            # Setup > Value Tier Layout - a separate setting from Landing
            # Page Layout, confirmed live 2026-09-08 on the same form):
            # "Grid View" - one ".tier-card-wrap" card per tier
            # (Economy/Standard/Premium), each with its own "Select"
            # button - or "List View" - a row of plain tier-name buttons
            # (disabled when that tier is sold out) that switch which
            # tier is active, sharing a single "Select" button at the
            # bottom of the dialog for whichever tier is currently
            # active. Both variants are handled here rather than
            # assuming one, the same way select_unit above handles both
            # Landing Page Layout variants.
            dialog = self.page.get_by_role("dialog")
            expect(dialog).to_be_visible(timeout=self.timeout)
            tier_cards = dialog.locator(".tier-card-wrap:visible")
            # Screenshot / inspect while the dialog is still open - before
            # choosing a plan dismisses it into the reservation form.
            if on_value_tier_dialog is not None:
                expect(
                    tier_cards.first.or_(
                        dialog.get_by_role("button", name="Select", exact=True)
                    ).first
                ).to_be_visible(timeout=self.timeout)
                on_value_tier_dialog(self.page)
            if tier_cards.count() > 0:
                # Grid View: scoped to the matching tier's own card, same
                # as unit selection above is scoped to its own category
                # card, rather than assuming tier position on the page.
                # Falls back to the first tier that isn't sold out if no
                # preference was given, or the requested one isn't
                # offered here. Not ".tier-card-wrap.selected" - which
                # tier the dialog defaults to selecting is decided by a
                # separate, slower live-inventory fetch than the
                # "soldout" class itself (confirmed live, 2026-09-08:
                # "soldout" is already present on first render, several
                # seconds before ".selected" lands on whichever tier
                # remains, which was long enough to blow past the
                # dialog's own click timeout waiting for it).
                chosen_plan = protection_plan
                if not chosen_plan:
                    available_tier_cards = dialog.locator(
                        ".tier-card-wrap:visible:not(.soldout)"
                    )
                    pick_from = (
                        available_tier_cards
                        if available_tier_cards.count() > 0
                        else tier_cards
                    )
                    # Read the tier's own name (".title") now and re-find
                    # the card by that name on every retry, rather than
                    # holding a ".not(.soldout)"-based locator across
                    # retries - confirmed live (2026-09-08, stage): which
                    # tier carries "soldout" can itself flip between the
                    # dialog first rendering and _click_until_gone's later
                    # retries as the same live-inventory fetch settles,
                    # so a class-based locator can silently re-resolve to
                    # a *different* tier mid-retry instead of the one
                    # actually confirmed available.
                    chosen_plan = (
                        pick_from.first.locator(".title").first.text_content() or ""
                    ).strip()
                tier_card = (
                    tier_cards.filter(has=self.page.get_by_text(chosen_plan, exact=True))
                    if chosen_plan
                    else tier_cards
                ).first
                expect(tier_card).to_be_visible(timeout=self.timeout)
                self._click_until_gone(
                    tier_card.get_by_role("button", name="Select", exact=True), dialog
                )
                value_tier_layout = "Grid View"
            else:
                # List View: switch to the requested tier's tab only if
                # it's actually available (a disabled tab is sold out,
                # same "fall back to whatever's already active" spirit
                # as Grid View's sold-out-tier fallback above) - Premium
                # confirmed live as the default active tab.
                if protection_plan:
                    tier_tab = dialog.get_by_role(
                        "button", name=protection_plan, exact=True
                    )
                    if tier_tab.count() > 0 and tier_tab.first.is_enabled():
                        tier_tab.first.click()
                self._click_until_gone(
                    dialog.get_by_role("button", name="Select", exact=True), dialog
                )
                value_tier_layout = "List View"

        return landing_page_layout, value_tier_layout

    @log_method_exceptions
    def wait_for_reservation_flow(self, timeout: float | None = None) -> str:
        """Which reservation flow's form actually renders once the tier
        dialog closes - Legacy ("Reserve This Space") or Two-Step
        ("Reserve Now") - is decided by the storefront per-session, and
        has been observed live (2026-09-08, stage) not reliably matching
        this property's own Two-Step Rental setting in HB. Waits for
        whichever one actually shows up and returns "legacy" or
        "two_step" so the caller (MPLegacyReservationSetup.reserve_unit,
        MPTwoStepReservationSetup.reserve_unit) can compare it against
        the flow their suite configured the property for and raise a
        clear, actionable error on a mismatch, rather than assuming one
        upfront and failing with a bare button timeout."""
        with allure.step("Detect which reservation flow the storefront served"):
            legacy_button = self.page.get_by_role(
                "button", name="Reserve This Space", exact=True
            )
            # A variant of the Legacy form (seen once, 2026-09-14, uat_storoutlet/
            # Bellflower, mobile): same "Reserve This Space" heading, but the
            # button reads "Submit" (see MPLegacyReservationFormPage.reserve_unit).
            legacy_submit = self.page.get_by_role("button", name="Submit", exact=True)
            two_step_button = self.page.get_by_role(
                "button", name="Reserve Now", exact=True
            )
            expect(
                legacy_button.first.or_(two_step_button.first).or_(legacy_submit.first).first
            ).to_be_visible(timeout=timeout if timeout is not None else self.timeout)
            return "two_step" if two_step_button.first.is_visible() else "legacy"
