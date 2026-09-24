import re
from datetime import date, datetime, timedelta
from urllib.parse import unquote

import allure
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from common_utils.wrapper_methods import first_visible, log_method_exceptions
from pages.mariposa.mp_document_signing_page import MPDocumentSigningPage
from pages.mariposa.mp_rental_payment_form import (
    ensure_payment_method_offered,
    enter_ach,
    enter_card,
    fill_billing_address,
    fill_business_representative,
    select_payment_method,
    select_state,
    set_autopay,
    tick_agreement,
)
from common_utils.waits import waits

# The rental application's "Additional Information" yes/no questions - the
# vehicle one has no default answer (confirmed live 2026-09-14).
ADDITIONAL_QUESTIONS = (
    "active_military",
    "lien_holder_confirmation",
    "emergency",
    "access_authorized",
    "vehicle_confirmation",
)


class MPLegacyReservationFormPage:
    """Legacy Flow: the unit form at .../rent_or_reserve/... offers both
    **Rent Now** (immediate paid move-in) and **Reserve This Space** (hold)
    side by side — confirmed live 2026-09-21 on uat_storoutlet/Bellflower.
    Reserve → thank-you → Rent online now; Rent Now lands on the same
    rental application. Unit/tier selection lives on MPUnitSearchPage.

    Confirmed live (2026-09-14, uat_storoutlet/Bellflower): the rental
    application has account password, alternate contact, Renter Identity
    Verification and a protection plan before payment (fill_rental_application),
    Card or ACH with one autopay box (pay_with), and ends one of two ways by
    the property's lease configuration (submit_rental) - "Sign Agreements"
    (Traditional) or the agreement box and "Pay Now" (Clickwrap / Superlease).
    """

    @log_method_exceptions
    def __init__(self, page: Page, base_url: str, timeout: float) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout = timeout

    @log_method_exceptions
    def _dismiss_banners(self) -> None:
        """Same popups as MPUnitSearchPage._dismiss_banners (cookie consent,
        AI chat widget) - this page picks up after the tier-selection
        dialog closes, which is its own separate SPA transition and can
        just as easily have either reappear on top of the reservation
        form underneath."""
        cookie_dialog_accept = self.page.get_by_role(
            "alertdialog", name="Cookie Consent Prompt"
        ).get_by_role("button", name="Accept", exact=True)
        if cookie_dialog_accept.count() > 0 and cookie_dialog_accept.first.is_visible():
            cookie_dialog_accept.first.click()

        # Mobile-only site-native cookie banner - see
        # MPUnitSearchPage._dismiss_banners. Skip while a real dialog is
        # open (2026-09-17: Accept under tier-section-modal-mobile times out).
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

        # Unscoped, so skipped while any in-flow modal is open - see
        # MPUnitSearchPage._dismiss_banners for why (confirmed live,
        # 2026-09-08: this exact class of unscoped text match closed the
        # tier-selection dialog there instead of a banner).
        if not dialog_open:
            cookie_accept = self.page.get_by_text("Accept", exact=True)
            if cookie_accept.count() > 0 and cookie_accept.first.is_visible():
                cookie_accept.first.click()

        chat_widget_close = self.page.frame_locator(
            'iframe[title="Chatbot"]'
        ).locator(".chat-window-close-btn")
        if chat_widget_close.count() > 0 and chat_widget_close.first.is_visible():
            chat_widget_close.first.click()

    @log_method_exceptions
    def _hard_refresh(self) -> None:
        """Bypasses HTTP cache (not just a plain reload) - the automated
        equivalent of the manual Ctrl+Shift+R staging teams use to rule
        out a stale client-side render before treating something as a
        real bug. The reservation hold is tied to the server-side
        session in the URL, so it survives this."""
        with allure.step("Hard refresh (bypass cache)"):
            cdp = self.page.context.new_cdp_session(self.page)
            cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
            self.page.reload()
            cdp.send("Network.setCacheDisabled", {"cacheDisabled": False})
            self._dismiss_banners()
            expect(
                self.page.get_by_role("textbox", name="Email *")
            ).to_be_visible(timeout=self.timeout)
            self._dismiss_banners()

    @log_method_exceptions
    def select_move_in_date(self, days_from_today: int = 1) -> date:
        """Pick a move-in date on the Reserve This Space / Rent Now calendar.

        ``days_from_today=0`` (Rent Now) keeps today when the field is already
        pre-filled; otherwise opens the calendar (or types into the date
        textbox variant).
        """
        with allure.step(f"Select move-in date: {days_from_today} day(s) from today"):
            target_date = date.today() + timedelta(days=max(days_from_today, 0))
            wanted = f"{target_date:%m/%d/%Y}"
            variant_date = self.page.get_by_role("textbox", name="date", exact=True)
            if variant_date.count() > 0 and variant_date.first.is_visible():
                current = (variant_date.first.input_value() or "").strip()
                if current not in (wanted, f"{target_date.month}/{target_date.day}/{target_date.year}"):
                    variant_date.first.fill(wanted)
                    variant_date.first.press("Tab")
                return target_date
            move_in_date = self.page.get_by_role(
                "textbox", name=re.compile(r"move.?in date", re.IGNORECASE)
            ).last
            current = ""
            try:
                current = (move_in_date.input_value() or "").strip()
            except Exception:
                pass
            if current in (
                wanted,
                f"{target_date.month}/{target_date.day}/{target_date.year}",
            ):
                return target_date
            move_in_date.click(force=True)
            calendar = self.page.locator("#calendar_modal")
            try:
                expect(calendar).to_be_visible(timeout=waits().short)
            except AssertionError:
                move_in_date.fill(wanted)
                move_in_date.press("Tab")
                return target_date
            self._click_calendar_day(target_date)
            expect(calendar).to_be_hidden(timeout=self.timeout)
            return target_date

    def _click_calendar_day(self, target_date: date) -> None:
        """Click the day cell; advance the month if the cell isn't visible yet.

        Confirmed live (2026-09-16, stage/Garden Grove): V-Calendar days outside
        the advance window stay visible but gray (`vc-text-gray-400`) and a
        click does not close #calendar_modal or change the field. The modal
        copy is "Reservations can only be done up to N days in advance" with
        selectable days today..today+(N-1). Reject grayed cells instead of
        waiting for to_be_hidden.
        """
        target_label = target_date.strftime("%A, %B ") + str(target_date.day) + ","
        calendar = self.page.locator("#calendar_modal")
        expect(calendar).to_be_visible(timeout=self.timeout)
        for _ in range(14):
            cell = self.page.get_by_label(target_label, exact=False).last
            try:
                if cell.count() > 0 and cell.is_visible():
                    classes = cell.get_attribute("class") or ""
                    if "vc-text-gray-400" in classes:
                        raise AssertionError(
                            f"Calendar day {target_label!r} is outside the "
                            f"advance-reservation window (grayed out). "
                            f"Modal: {calendar.inner_text()[:200]!r}"
                        )
                    cell.click()
                    return
            except AssertionError:
                raise
            except Exception:
                pass
            next_btn = calendar.locator(
                ".flatpickr-next-month, .datepicker-next, .next-month, "
                "[aria-label*='Next' i], .icon-arrow-right, .icon-right"
            ).first
            if next_btn.count() == 0 or not next_btn.is_visible():
                next_btn = calendar.get_by_role(
                    "button", name=re.compile(r"next|›|»", re.I)
                ).first
            if next_btn.count() == 0:
                break
            next_btn.click()
        raise AssertionError(
            f"Calendar day {target_label!r} not found in #calendar_modal"
        )

    @log_method_exceptions
    def start_rental_now(
        self,
        email: str,
        mobile: str,
        first_name: str,
        last_name: str,
        renting_as_business: bool = False,
        business_name: str | None = None,
        days_from_today: int = 0,
    ) -> date:
        """Click **Rent Now** on the Legacy unit form (direct paid move-in).

        Guest Email / Name / Mobile (and RAB Business Email / Name / Phone)
        are **not** required on this page — they are filled on the rental
        application (live 2026-09-21 Garden Grove). Still sets move-in date
        and optional business checkbox. Skips Reserve This Space / hold
        thank-you / confirmation email.
        """
        with allure.step("Wait for the unit Rent Now form"):
            self._dismiss_banners()
            rent_button = self.page.get_by_role(
                "button", name="Rent Now", exact=True
            )
            expect(rent_button).to_be_visible(timeout=self.timeout)
            self._dismiss_banners()

        if renting_as_business:
            # Unit Rent Now: only tick RAB. Business Email/Name/Phone are
            # filled on the rental application (same as individual
            # Email/Name/Mobile — live 2026-09-21 Garden Grove).
            with allure.step(
                f"Mark renting as a business"
                + (f": {business_name}" if business_name else "")
            ):
                business_checkbox = self.page.get_by_role(
                    "checkbox", name="I am renting as a business"
                )
                try:
                    expect(business_checkbox).to_be_visible(timeout=self.timeout)
                except AssertionError:
                    with allure.step(
                        "Business checkbox not visible - hard refresh and check again"
                    ):
                        self._hard_refresh()
                        expect(business_checkbox).to_be_visible(timeout=self.timeout)
                business_checkbox.check()

        move_in_date = self.select_move_in_date(days_from_today)

        with allure.step("Click Rent Now (guest details on application)"):
            self._dismiss_banners()
            expect(rent_button).to_be_visible(timeout=self.timeout)
            arrived = self.page.locator("#idtenantemail")
            max_attempts = 3
            for attempt in range(max_attempts):
                self._dismiss_banners()
                rent_button.click()
                try:
                    expect(arrived).to_be_visible(
                        timeout=self.timeout / max_attempts
                    )
                    break
                except AssertionError:
                    if attempt == max_attempts - 1:
                        raise
                    if not rent_button.is_visible():
                        raise
        return move_in_date

    @log_method_exceptions
    def reserve_unit(
        self,
        email: str,
        mobile: str,
        first_name: str,
        last_name: str,
        renting_as_business: bool = False,
        business_name: str | None = None,
        days_from_today: int = 1,
    ) -> date:
        with allure.step("Wait for the reservation form to load"):
            # The tier dialog closing (see MPUnitSearchPage.select_unit) is a
            # separate SPA transition from this form actually rendering -
            # confirmed live (2026-09-08, stage): the gap between the two
            # can exceed the dialog-close wait's own timeout, so this
            # form's own presence is waited on explicitly here rather
            # than assumed the moment the dialog is gone.
            self._dismiss_banners()
            expect(
                self.page.get_by_role("textbox", name="Email *")
            ).to_be_visible(timeout=self.timeout)
            self._dismiss_banners()

        if renting_as_business:
            with allure.step(f"Fill business information: {business_name}"):
                business_checkbox = self.page.get_by_role(
                    "checkbox", name="I am renting as a business"
                )
                try:
                    expect(business_checkbox).to_be_visible(timeout=self.timeout)
                except AssertionError:
                    with allure.step(
                        "Business checkbox not visible - hard refresh and check again"
                    ):
                        self._hard_refresh()
                        expect(business_checkbox).to_be_visible(timeout=self.timeout)
                business_checkbox.check()
                self.page.get_by_role("textbox", name="Business Name").fill(
                    business_name or f"{first_name} {last_name} Business"
                )
                self.page.get_by_role("textbox", name="Business Phone").fill(mobile)
                self.page.get_by_role("textbox", name="Business Email").fill(email)

        # After the RAB checkbox: same reset as Two-Step (2026-09-17) -
        # picking the date before "I am renting as a business" loses it.
        move_in_date = self.select_move_in_date(days_from_today)

        with allure.step("Fill and submit the reservation form"):
            self._dismiss_banners()

            # Confirmed live: field labels are "First Name *"/"Last Name *"
            # (capitalized), not "First name *"/"Last name *". Confirmed
            # live (2026-09-08, stage): checking "I am renting as a
            # business" swaps the form to Business Email/Business Phone/
            # Business Name only - the personal fields below stop
            # existing at all (not just hidden), so filling them here
            # for a business reservation just times out. Business Email/
            # Business Phone already carry email/mobile (filled above),
            # and Business Name carries the name.
            required_fields = (
                {}
                if renting_as_business
                else {
                    "Email *": email,
                    "Mobile *": mobile,
                    "First Name *": first_name,
                    "Last Name *": last_name,
                }
            )
            # Confirmed live (2026-09-08, stage): the submit button's
            # own accessible name is "Reserve This Space" (a <span>
            # inside the <button>) - same text as this page's own tab
            # heading (an <h1>, not a button), but get_by_role("button")
            # disambiguates since only the real button carries that
            # role. Which flow's form renders here at all is decided
            # upstream, before this page object is ever used - see
            # MPUnitSearchPage.wait_for_reservation_flow.
            # The form's variant (seen once, 2026-09-14, mobile) submits with
            # "Submit" instead - its confirmation page hasn't been seen yet.
            reserve_button = (
                self.page.get_by_role("button", name="Reserve This Space", exact=True)
                .or_(self.page.get_by_role("button", name="Submit", exact=True))
                .first
            )
            expect(reserve_button).to_be_visible(timeout=self.timeout)
            continue_as_guest = self.page.get_by_text(
                "Continue as Guest", exact=True
            ).first
            confirmed_heading = self.page.get_by_text(
                "Your reservation is confirmed", exact=False
            ).first
            # Confirmed live (2026-09-13, uat_storoutlet/Bellflower): the
            # storefront can answer a submit with a ".../thank-you/?hold=
            # true" page - "Thank you for your interest in <facility>.
            # Please contact the facility to confirm the availability of
            # your space." - and no reservation code or email. The old
            # Robot suite knew it too ("Reservation Confirmation and
            # Login"). Waited on here so it fails fast below instead of the
            # retry loop refilling a form that no longer exists.
            contact_facility = self.page.get_by_text(
                re.compile(r"contact the facility to confirm the availability", re.IGNORECASE)
            ).first
            submitted = continue_as_guest.or_(confirmed_heading).or_(contact_facility).first

            def fill_required_fields() -> None:
                for field_name, field_value in required_fields.items():
                    field = self.page.get_by_role("textbox", name=field_name)
                    if field_name != "Mobile *":
                        field.fill(field_value)
                        continue
                    # Confirmed live (2026-09-13, uat_storoutlet): the phone
                    # check is an async GET .../validate-phone/ (~0.5 s) and
                    # counts as invalid while pending, so a click right
                    # after filling is silently dropped (console only:
                    # "validPhoneNumber failed for field phone"). Wait for
                    # that lookup for these digits; clear+refill to re-trigger
                    # when a plain refill would not (live 2026-09-21 hold
                    # thank-you after validate-phone timeout).
                    digits = re.sub(r"\D", "", field_value)
                    validated = False
                    for _phone_try in range(3):
                        field.click()
                        field.fill("")
                        try:
                            with self.page.expect_response(
                                lambda response: "/validate-phone/" in response.url
                                and digits
                                in re.sub(
                                    r"%[0-9A-Fa-f]{2}|\D", "", response.url
                                ),
                                timeout=waits().medium,
                            ):
                                field.fill(field_value)
                            validated = True
                            break
                        except PlaywrightTimeoutError:
                            self.page.wait_for_timeout(waits().poll_interval)
                    if not validated:
                        allure.attach(
                            f"phone validate-phone did not complete for {digits}",
                            name="phone-validation-timeout",
                            attachment_type=allure.attachment_type.TEXT,
                        )
                        field.fill(field_value)
                        self.page.wait_for_timeout(waits().settle_short)

            # This form's "Holding Space For MM:SS" countdown re-renders
            # the card on a live interval, which can silently swallow a
            # submit that lands mid-re-render - refilling and re-clicking
            # a few times self-heals against that without needing to pin
            # the exact re-render trigger down to a fixed wait.
            max_attempts = 3
            for attempt in range(max_attempts):
                self._dismiss_banners()
                fill_required_fields()
                reserve_button.click()
                try:
                    expect(submitted).to_be_visible(timeout=self.timeout / max_attempts)
                    break
                except AssertionError:
                    if attempt == max_attempts - 1:
                        raise

            if contact_facility.is_visible():
                raise AssertionError(
                    "Storefront answered the reservation with its 'Thank you for "
                    "your interest ... Please contact the facility to confirm "
                    "the availability of your space' page instead of a "
                    f"confirmed reservation (no code, no email): {self.page.url}"
                )

        with allure.step("Continue as guest if this email is already registered"):
            if continue_as_guest.is_visible():
                continue_as_guest.click()
                reserve_button = self.page.get_by_role(
                    "button", name="Reserve Now"
                )
                if reserve_button.is_visible():
                    reserve_button.click()

        with allure.step("Assert reservation is confirmed"):
            expect(confirmed_heading).to_be_visible(timeout=self.timeout)
        return move_in_date

    @log_method_exceptions
    def get_reservation_code(self) -> str:
        """Confirmed live 2026-09-08: the confirmation page now renders
        the label ("Your reservation code:") and the code itself as two
        separate sibling paragraphs, not the single "Reservation Code:
        KDX2SL" text node this used to be (site content change)."""
        with allure.step("Read reservation code"):
            label = self.page.get_by_text(
                re.compile(r"Your reservation code:", re.IGNORECASE)
            )
            expect(label.first).to_be_visible(timeout=self.timeout)
            code_element = label.first.locator(
                "xpath=ancestor-or-self::p[1]/following-sibling::p[1]"
            )
            expect(code_element).to_be_visible(timeout=self.timeout)
            value = (code_element.text_content() or "").strip()
            allure.attach(
                value, name="reservation code", attachment_type=allure.attachment_type.TEXT
            )
            return value

    @log_method_exceptions
    def rent_online_now(self) -> None:
        with allure.step("Resume reservation: click 'Rent online now'"):
            first_visible(
                self.page.get_by_role("button", name="Rent online now")
            ).click()

    @log_method_exceptions
    def select_notice_delivery(self, method: str = "Electronic Mail (Email)") -> None:
        with allure.step(f"Select notice delivery method: {method}"):
            # This form's radios are custom-styled: the native input sits
            # behind a decorative checkmark span that intercepts plain
            # clicks - force bypasses that overlap, matching how this
            # codebase already handles other custom-styled Vuetify
            # switches/radios elsewhere (e.g. MPFMSInitialSetupPage).
            self.page.get_by_text(method, exact=True).click(force=True)

    @log_method_exceptions
    def _select_first_coverage(self) -> None:
        """Select the first coverage option when the form offers one.

        When the radios are absent or hidden, the rental continues without
        a plan. When they are on screen and none is selected, the first
        one is ticked."""
        coverage = self.page.locator('input[id^="coverageAmount-ins"]')
        offered = []
        for index in range(coverage.count()):
            radio = coverage.nth(index)
            radio_id = radio.get_attribute("id")
            if not radio_id:
                continue
            label = self.page.locator(f'label[for="{radio_id}"]')
            label_visible = label.count() > 0 and label.first.is_visible()
            try:
                input_visible = radio.is_visible()
            except Exception:
                input_visible = False
            if label_visible or input_visible:
                offered.append(radio)
        if not offered:
            allure.attach(
                "Coverage is not on this rental form; skipped",
                name="coverage",
                attachment_type=allure.attachment_type.TEXT,
            )
            return
        if any(radio.is_checked() for radio in offered):
            return
        radio_id = offered[0].get_attribute("id")
        if radio_id:
            self._check_radio(radio_id)

    @log_method_exceptions
    def _check_radio(self, radio_id: str) -> None:
        """This form's radios are custom-styled - the native input sits
        behind a decorative span - so they're ticked through their labels
        (see select_notice_delivery)."""
        radio = self.page.locator(f'[id="{radio_id}"]')
        if radio.count() == 0 or radio.first.is_checked():
            return
        label = self.page.locator(f'label[for="{radio_id}"]').first
        # One forced label click left "Electronic Mail (Email)" unticked on a
        # mobile run (2026-09-14; it worked in 30+ other rentals) - likely the
        # form still re-rendering - so each try is followed by a short check,
        # with more direct clicks after the label.
        for tick in (
            lambda: label.click(force=True),
            lambda: radio.first.check(force=True),
            lambda: label.dispatch_event("click"),
        ):
            try:
                tick()
                expect(radio.first).to_be_checked(timeout=waits().short)
                return
            except Exception:
                continue
        expect(radio.first).to_be_checked(timeout=self.timeout)

    @log_method_exceptions
    def ensure_payment_method(self, method: str) -> None:
        """Checked right after "Rent online now", before anything is filled,
        so a reload for a missing method loses nothing - see
        mp_rental_payment_form.ensure_payment_method_offered."""
        ensure_payment_method_offered(
            self.page, self.timeout, method, self.page.locator("#idtenantemail")
        )

    @log_method_exceptions
    def fill_rental_application(
        self,
        rental_data: dict,
        alternate: dict | None,
        guest: dict | None = None,
        extras: dict | None = None,
    ) -> None:
        """The rental application, up to payment.
        Confirmed live (2026-09-14, uat_storoutlet/Bellflower, reservation
        64W1X4): after Reserve → Rent online now, email/name/mobile are
        pre-filled. After **Rent Now** they are empty and must be filled
        from ``guest`` (live 2026-09-21 Garden Grove). Also: Account
        Password, alternate contact, Additional Information, Protection
        Plan and Renter Identity Verification before payment.

        extras (optional, walked stage/Garden Grove 2026-09-16): tick and
        fill military / lien holder / vehicle / emergency / authorized-access
        blocks. Keys:
        - military: dict of military fields (ticks active_military yes)
        - lien_holder: dict of lien holder fields
        - emergency: dict of emergency contact fields
        - authorized_access: dict of authorized-access contact fields
        - vehicle_type: e.g. "Car" (ticks vehicle_confirmation yes)
        - coverage: False to skip selecting a protection plan (default True)

        alternate: contact dict, or None / {} to leave the secondary/alternate
        contact unticked (Superlease then shows N/A - walked 2026-09-16).
        """
        extras = extras or {}
        with allure.step("Fill the rental application"):
            expect(self.page.locator("#idtenantemail")).to_be_visible(timeout=self.timeout * 2)
            self._dismiss_banners()
            # Rent Now leaves identity empty (unlike Reserve → Rent online
            # now). Individual: Email / First / Last / Mobile. RAB: Business
            # Email / Name / Phone + Business Representative — do not use
            # tenant identity or First/Last/Mobile land in the rep block
            # (live 2026-09-21 clickwrap RAB).
            business = self.page.get_by_role(
                "checkbox", name="I am renting as a business"
            )
            renting_as_business = (
                business.count() > 0 and business.first.is_checked()
            )
            if guest is not None:
                if renting_as_business:
                    self._fill_business_identity(guest)
                else:
                    self._fill_tenant_identity(guest)
            password = self.page.locator("#idtenantpassword")
            if password.count() > 0 and password.is_visible() and not password.input_value():
                password.fill(rental_data["account_password"])
            self._check_radio("id_notice_deliveryemail")
            self._answer_additional_questions(extras)
            if alternate:
                self._fill_alternate_contact(rental_data, alternate)
            elif self.page.locator('[id="id_secondary_contactno"]').count():
                self._check_radio("id_secondary_contactno")
            if extras.get("military"):
                self._fill_military(extras["military"], rental_data)
            if extras.get("lien_holder"):
                self._fill_lien_holder(extras["lien_holder"], rental_data)
            if extras.get("emergency"):
                self._fill_named_contact("emergency", extras["emergency"], rental_data)
            if extras.get("authorized_access"):
                self._fill_named_contact(
                    "access_authorized", extras["authorized_access"], rental_data
                )
            if extras.get("vehicle_type"):
                self._fill_vehicle(extras["vehicle_type"], extras.get("vehicle"))
            if extras.get("coverage", True):
                self._select_first_coverage()
            self._verify_id_later(rental_data)
            if guest is not None:
                self._fill_business_representative(guest, rental_data)

    @log_method_exceptions
    def _fill_tenant_identity(self, guest: dict) -> None:
        """Rental Agreement Information: Email / First / Last / Mobile.

        Required after **Rent Now** (empty). After Reserve → Rent online now
        these are usually pre-filled — only empty fields are written.
        """
        with allure.step(
            f"Tenant identity: {guest['first_name']} {guest['last_name']}"
        ):
            email = self.page.locator("#idtenantemail")
            if not (email.input_value() or "").strip():
                email.fill(guest["email"])
            # .first = tenant block (alternate / lien share the same labels
            # but are filled later).
            for name, value in (
                ("First Name *", guest["first_name"]),
                ("Last Name *", guest["last_name"]),
            ):
                field = self.page.get_by_role("textbox", name=name).first
                if field.is_visible() and not (field.input_value() or "").strip():
                    field.fill(value)
            mobile = self.page.get_by_role("textbox", name="Mobile *").first
            if mobile.is_visible() and not (mobile.input_value() or "").strip():
                digits = re.sub(r"\D", "", guest["mobile"])
                try:
                    with self.page.expect_response(
                        lambda response: "/validate-phone/" in response.url
                        and digits
                        in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                        timeout=waits().medium,
                    ):
                        mobile.fill(guest["mobile"])
                except PlaywrightTimeoutError:
                    mobile.fill(guest["mobile"])

    @log_method_exceptions
    def _fill_business_identity(self, guest: dict, business_name: str | None = None) -> None:
        """RAB Rental Agreement Information: Business Email / Name / Phone.

        Required after **Rent Now** (empty even when the unit-page RAB
        checkbox carried over — live 2026-09-21 Garden Grove). After
        Reserve → Rent online now these are usually pre-filled.
        """
        name = business_name or (
            f"{guest['first_name']} {guest['last_name']} Business"
        )
        with allure.step(f"Business identity: {name}"):
            for field_name, value in (
                ("Business Email", guest["email"]),
                ("Business Name", name),
            ):
                field = self.page.get_by_role("textbox", name=field_name).first
                if field.count() and field.is_visible() and not (
                    field.input_value() or ""
                ).strip():
                    field.fill(value)
            phone = self.page.get_by_role("textbox", name="Business Phone").first
            if phone.count() and phone.is_visible() and not (
                phone.input_value() or ""
            ).strip():
                digits = re.sub(r"\D", "", guest["mobile"])
                try:
                    with self.page.expect_response(
                        lambda response: "/validate-phone/" in response.url
                        and digits
                        in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                        timeout=waits().medium,
                    ):
                        phone.fill(guest["mobile"])
                except PlaywrightTimeoutError:
                    phone.fill(guest["mobile"])

    @log_method_exceptions
    def _answer_additional_questions(self, extras: dict) -> None:
        """Yes for each extras block present; otherwise No (default).
        Vehicle confirmation Yes is only ticked when that question exists
        (storage); parking spaces skip straight to Vehicle Type*."""
        yes_for = {
            "active_military": bool(extras.get("military")),
            "lien_holder_confirmation": bool(extras.get("lien_holder")),
            "vehicle_confirmation": bool(extras.get("vehicle_type")),
            "emergency": bool(extras.get("emergency")),
            "access_authorized": bool(extras.get("authorized_access")),
        }
        for question in ADDITIONAL_QUESTIONS:
            yes_id = f"id_{question}yes"
            no_id = f"id_{question}no"
            if yes_for.get(question) and self.page.locator(f'[id="{yes_id}"]').count():
                self._check_radio(yes_id)
            elif self.page.locator(f'[id="{no_id}"]').count():
                self._check_radio(no_id)

    @log_method_exceptions
    def _fill_military(self, military: dict, rental_data: dict) -> None:
        """Active-duty military block (revealed after Yes). Walked live
        2026-09-16 stage/Garden Grove: ids under idmilitary* / phonemilitary."""
        with allure.step("Fill active military details"):
            expect(self.page.locator("#idmilitarymilitary_identification_number")).to_be_visible(
                timeout=self.timeout
            )
            self.page.locator("#idmilitarymilitary_identification_number").fill(
                military["identification_number"]
            )
            self.page.locator("#idmilitarymilitary_service_members_dob").fill(military["dob"])
            self.page.locator("#idmilitarysocial_security_number").fill(military["ssn"])
            self.page.locator("#idmilitarymilitary_ets").fill(military["ets"])
            self.page.locator("#idmilitarymilitary_branch").fill(military["branch"])
            self.page.locator("#idmilitarymilitary_unit_name").fill(military["unit_name"])
            digits = re.sub(r"\D", "", military["unit_phone"])
            try:
                with self.page.expect_response(
                    lambda response: "/validate-phone/" in response.url
                    and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                    timeout=waits().medium,
                ):
                    self.page.locator("#phonemilitary").fill(
                        f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                    )
            except PlaywrightTimeoutError:
                self.page.locator("#phonemilitary").fill(
                    f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                )
            self.page.locator("#idmilitarymilitary_unit_address1").fill(
                military.get("address1") or rental_data["address1"]
            )
            if military.get("address2") or rental_data.get("address2"):
                self.page.locator("#idmilitarymilitary_unit_address2").fill(
                    military.get("address2") or rental_data["address2"]
                )
            self.page.locator("#idmilitarymilitary_unit_zip").fill(
                military.get("zip") or rental_data["zip"]
            )
            select_state(
                self.page.locator("#idmilitarymilitary_unit_state"),
                military.get("state") or rental_data["state"],
                military.get("state_code") or rental_data["state_code"],
            )
            self.page.locator("#idmilitarymilitary_unit_city").fill(
                military.get("city") or rental_data["city"]
            )
            self.page.locator("#idmilitarymilitary_commanding_officer_first_name").fill(
                military["officer_first_name"]
            )
            self.page.locator("#idmilitarymilitary_commanding_officer_last_name").fill(
                military["officer_last_name"]
            )

    @log_method_exceptions
    def _fill_lien_holder(self, lien: dict, rental_data: dict) -> None:
        """Lien / secured interest block. Walked live 2026-09-16 stage/
        Garden Grove: ids under idlien_holder* / phonelien_holder."""
        with allure.step(f"Fill lien holder: {lien['first_name']} {lien['last_name']}"):
            expect(self.page.locator("#idlien_holderfirst_name")).to_be_visible(
                timeout=self.timeout
            )
            self.page.locator("#idlien_holderfirst_name").fill(lien["first_name"])
            self.page.locator("#idlien_holderlast_name").fill(lien["last_name"])
            self.page.locator("#idlien_holderemail").fill(lien["email"])
            digits = re.sub(r"\D", "", lien["phone"])
            try:
                with self.page.expect_response(
                    lambda response: "/validate-phone/" in response.url
                    and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                    timeout=waits().medium,
                ):
                    self.page.locator("#phonelien_holder").fill(
                        f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                    )
            except PlaywrightTimeoutError:
                self.page.locator("#phonelien_holder").fill(
                    f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                )
            self.page.locator("#idlien_holderaddress1").fill(
                lien.get("address1") or rental_data["address1"]
            )
            if lien.get("address2") or rental_data.get("address2"):
                self.page.locator("#idlien_holderaddress2").fill(
                    lien.get("address2") or rental_data["address2"]
                )
            self.page.locator("#idlien_holderzip").fill(lien.get("zip") or rental_data["zip"])
            select_state(
                self.page.locator("#idlien_holderstate"),
                lien.get("state") or rental_data["state"],
                lien.get("state_code") or rental_data["state_code"],
            )
            self.page.locator("#idlien_holdercity").fill(lien.get("city") or rental_data["city"])

    @log_method_exceptions
    def _fill_vehicle(self, vehicle_type: str, vehicle: dict | None = None) -> None:
        """After vehicle_confirmation Yes: pick Vehicle Type then fill the
        revealed Car fields. Walked live 2026-09-16 stage/Garden Grove:
        type radio id_parking_type_fieldscar is hidden; Vin / Plate / Value /
        Insurance / Policy appear after Car is ticked."""
        vehicle = vehicle or {}
        with allure.step(f"Select vehicle type: {vehicle_type}"):
            radio_id = f"id_parking_type_fields{vehicle_type.lower()}"
            radio = self.page.locator(f'[id="{radio_id}"]')
            expect(radio.first).to_be_attached(timeout=self.timeout)
            self._check_radio(radio_id)
            expect(radio.first).to_be_checked(timeout=self.timeout)
            vin = self.page.get_by_role("textbox", name="Vin Number *", exact=True)
            expect(vin.first).to_be_visible(timeout=self.timeout)
            vin.first.fill(vehicle.get("vin", "1HGBH41JXMN109186"))
            self.page.get_by_role(
                "textbox", name="License Plate Number *", exact=True
            ).first.fill(vehicle.get("license_plate", "AUTO123"))
            self.page.get_by_role(
                "textbox", name="Approximate Value *", exact=True
            ).first.fill(vehicle.get("approximate_value", "5000"))
            self.page.get_by_role(
                "textbox", name="Insurance Provider *", exact=True
            ).first.fill(vehicle.get("insurance_provider", "State Farm"))
            self.page.get_by_role(
                "textbox", name="Policy Number *", exact=True
            ).first.fill(vehicle.get("policy_number", "POL-AUTO-001"))
            registered = self.page.locator(
                '[id^="id_"][id*="registered"][id$="yes"], '
                '[id^="id_"][id*="owner"][id$="yes"]'
            )
            # Prefer exact known pattern if present; else Yes in the registered-owner group.
            owner_yes = self.page.get_by_role(
                "group", name=re.compile(r"Registered owner", re.I)
            ).get_by_role("radio", name="Yes", exact=True)
            if owner_yes.count():
                label_for = owner_yes.first.get_attribute("id")
                if label_for:
                    self._check_radio(label_for)
                else:
                    owner_yes.first.check(force=True)
            elif registered.count():
                self._check_radio(registered.first.get_attribute("id"))

    @log_method_exceptions
    def _fill_named_contact(self, prefix: str, contact: dict, rental_data: dict) -> None:
        """Emergency / authorized-access blocks (id{prefix}* / phone{prefix}).
        Walked live 2026-09-16 stage/Garden Grove under Super Lease: prefixes
        emergency and access_authorized."""
        phone_key = "phone" if "phone" in contact else "phone_number"
        with allure.step(
            f"Fill {prefix}: {contact['first_name']} {contact['last_name']}"
        ):
            first_name = self.page.locator(f"#id{prefix}first_name")
            expect(first_name).to_be_visible(timeout=self.timeout)
            first_name.fill(contact["first_name"])
            self.page.locator(f"#id{prefix}last_name").fill(contact["last_name"])
            email = self.page.locator(f"#id{prefix}email")
            if email.count():
                email.fill(contact["email"])
            digits = re.sub(r"\D", "", contact[phone_key])
            phone = self.page.locator(f"#phone{prefix}")
            try:
                with self.page.expect_response(
                    lambda response: "/validate-phone/" in response.url
                    and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                    timeout=waits().medium,
                ):
                    phone.fill(f"({digits[:3]}) {digits[3:6]}-{digits[6:]}")
            except PlaywrightTimeoutError:
                phone.fill(f"({digits[:3]}) {digits[3:6]}-{digits[6:]}")
            self.page.locator(f"#id{prefix}address1").fill(
                contact.get("address1") or rental_data["address1"]
            )
            if contact.get("address2") or rental_data.get("address2"):
                self.page.locator(f"#id{prefix}address2").fill(
                    contact.get("address2") or rental_data["address2"]
                )
            self.page.locator(f"#id{prefix}zip").fill(
                contact.get("zip") or rental_data["zip"]
            )
            select_state(
                self.page.locator(f"#id{prefix}state"),
                contact.get("state") or rental_data["state"],
                contact.get("state_code") or rental_data["state_code"],
            )
            self.page.locator(f"#id{prefix}city").fill(
                contact.get("city") or rental_data["city"]
            )

    @log_method_exceptions
    def _fill_alternate_contact(self, rental_data: dict, alternate: dict) -> None:
        """Secondary / alternate contact. Walked live 2026-09-16 stage/Garden
        Grove under Super Lease: tick id_secondary_contactyes ("I would like
        to provide a secondary contact to receive lien notices") first - without
        it the Superlease PDF keeps the alternate block as N/A even when the
        idalternate* fields were filled. Gmail test-inbox email and
        (707)/(714) 555-01xx number from test_identities.new_additional_contact."""
        if self.page.locator('[id="id_secondary_contactyes"]').count():
            self._check_radio("id_secondary_contactyes")
        else:
            provide = self.page.get_by_role(
                "radio",
                name=re.compile(r"provide a secondary contact", re.I),
            )
            if provide.count():
                provide.first.check(force=True)
        first_name = self.page.locator("#idalternatefirst_name")
        expect(first_name).to_be_visible(timeout=self.timeout)
        digits = re.sub(r"\D", "", alternate["phone_number"])
        if not re.fullmatch(r"(707|714)55501\d\d", digits):
            raise ValueError(
                f"Alternate contact number {digits} isn't a fictional 555-01xx number"
            )
        with allure.step(
            f"Fill alternate contact: {alternate['first_name']} {alternate['last_name']}"
        ):
            first_name.fill(alternate["first_name"])
            self.page.locator("#idalternatelast_name").fill(alternate["last_name"])
            self.page.locator("#idalternateemail").fill(alternate["email"])
            # Same async phone check as the reservation form's Mobile field.
            try:
                with self.page.expect_response(
                    lambda response: "/validate-phone/" in response.url
                    and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                    timeout=waits().medium,
                ):
                    self.page.locator("#phonealternate").fill(
                        f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                    )
            except PlaywrightTimeoutError:
                self.page.locator("#phonealternate").fill(
                    f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                )
            self.page.locator("#idalternateaddress1").fill(rental_data["address1"])
            self.page.locator("#idalternateaddress2").fill(rental_data["address2"])
            self.page.locator("#idalternatezip").fill(rental_data["zip"])
            select_state(
                self.page.locator("#idalternatestate"),
                rental_data["state"],
                rental_data["state_code"],
            )
            self.page.locator("#idalternatecity").fill(rental_data["city"])

    @log_method_exceptions
    def _verify_id_later(self, rental_data: dict) -> None:
        """Renter Identity Verification sits inside this form, before
        payment (confirmed live 2026-09-14) - the Two-Step form asks after
        the rental. "Verify ID Later" reveals the tenant's mailing address
        and driver's licence fields, filled directly."""
        later = self.page.get_by_role("button", name=re.compile(r"Verify ID Later"))
        if later.count() == 0:
            return
        with allure.step("Verify ID later: mailing address and licence"):
            later.first.scroll_into_view_if_needed()
            later.first.click()
            address1 = self.page.locator("#idtenant_contactaddress1")
            expect(address1).to_be_visible(timeout=self.timeout)
            address1.fill(rental_data["address1"])
            self.page.locator("#idtenant_contactaddress2").fill(rental_data["address2"])
            self.page.locator("#idtenant_contactzip").fill(rental_data["zip"])
            select_state(
                self.page.locator("#idtenant_contactstate"), rental_data["state"], rental_data["state_code"]
            )
            self.page.locator("#idtenant_contactcity").fill(rental_data["city"])
            licence_number = self.page.locator("#iddrivers_licensedrivers_license_number")
            if licence_number.count() > 0 and licence_number.is_visible():
                licence_number.fill(rental_data["drivers_license_number"])
            select_state(
                self.page.locator("#iddrivers_licensedrivers_license_state"),
                rental_data["drivers_license_state"],
                rental_data["state_code"],
            )
            # Filled, not clicked - the expiry sits under its floating label.
            expiry = self.page.locator("#iddrivers_licensedrivers_license_expiration_date")
            if expiry.count() > 0 and expiry.is_visible():
                expiry.fill(rental_data["drivers_license_expiration"])

    @log_method_exceptions
    def _fill_business_representative(self, guest: dict, rental_data: dict) -> None:
        """Renting as a business only (confirmed 2026-09-14, uat_storoutlet/
        Bellflower): the reservation collects just Business Name/Phone/Email,
        so the rental form's "Business Representative Information" - Email,
        Mobile, First/Last Name and an address - comes up empty and required
        (Sign Agreements is refused until it's filled). Its labels repeat the
        alternate contact's, so each field is the first empty, visible one of
        its name: the business address and alternate blocks are filled by the
        time this runs. The representative is the renter - the guest's
        Gmail address and fictional (714) 555-01xx mobile."""
        fill_business_representative(self.page, self.timeout, guest, rental_data)

    @log_method_exceptions
    def pay_with(self, method: str, enroll_autopay: bool, payer: dict, billing_address: dict) -> None:
        """method is "card" or "ach" - see mp_rental_payment_form. In the
        walked order (2026-09-14): method, its fields, billing address, then
        autopay."""
        label = "ACH / E-Check" if method == "ach" else "Credit Card"
        with allure.step(f"Payment: {label}" + (" with autopay" if enroll_autopay else "")):
            self._dismiss_banners()
            select_payment_method(self.page, self.timeout, method)
            if method == "ach":
                enter_ach(
                    self.page, self.timeout, payer["name"], payer["routing_number"], payer["account_number"]
                )
            else:
                enter_card(
                    self.page, self.timeout, payer["card_number"], payer["card_expiry"],
                    payer["card_cvc"], payer["name"],
                )
            fill_billing_address(self.page, self.timeout, billing_address)
            set_autopay(self.page, self.timeout, enroll_autopay)

    @log_method_exceptions
    def read_lease_totals(self) -> dict:
        """The Lease Summary's space ("#0094 | 8' x 5'"), charge rows,
        Security Deposit and "Total Cost to Move-in: $X", read once the
        total has held for 3 s - the protection plan and proration change
        it while the form fills (confirmed live 2026-09-14: $177.20 before
        the $2,000 plan, $188.53 on the signed lease after it)."""
        from common_utils.mp_lease_costs import (
            parse_charges_from_summary_text,
            security_deposit_amount,
        )

        # allure.step("Read the lease summary") — omitted from report; still read.
        # Prefer the Lease Summary sidebar (same as Two-Step). Whole-body
        # `#unit |` can match another unit on the page and fail the
        # summary-vs-confirmation assert (live 2026-09-21: load139 vs load138).
        total_pattern = re.compile(r"Total Cost to Move-in:\s*\$([\d,]+\.\d{2})")
        sidebar = self.page.locator(
            ".unit-sidebarwrapper:not(:has(.unit-sidebarwrapper))"
        ).first

        def summary_text() -> str:
            try:
                if sidebar.count() and sidebar.is_visible():
                    return sidebar.inner_text()
            except Exception:
                pass
            return self.page.locator("body").inner_text()

        readings: list[str | None] = []
        text = ""
        for _ in range(int(self.timeout / 500)):
            text = summary_text()
            total = total_pattern.search(text)
            readings.append(total.group(1) if total else None)
            if readings[-1] and len(readings) >= 6 and len(set(readings[-6:])) == 1:
                break
            self.page.wait_for_timeout(waits().poll_interval)
        else:
            raise AssertionError(f"Lease Summary total never settled: {readings[-6:]}")
        # Prefer .unit-size ("#load141 | 6' x 6'") over any other #unit | on
        # the sidebar / page (recommended units caused load142 vs load141 —
        # live 2026-09-21 non-tenant clickwrap).
        space = None
        try:
            unit_size = sidebar.locator(".unit-size").first
            if sidebar.count() and unit_size.count() and unit_size.is_visible():
                space = re.search(r"#(\S+)\s*\|", unit_size.inner_text())
        except Exception:
            space = None
        if space is None:
            space = re.search(r"#(\S+)\s*\|", text)
        charges = parse_charges_from_summary_text(text)
        deposit = security_deposit_amount(charges)
        if deposit is None:
            deposit_match = re.search(r"Security Deposit\s*\$([\d,]+\.\d{2})", text)
            deposit = (
                float(deposit_match.group(1).replace(",", "")) if deposit_match else None
            )
        # The rental's move-in date, as the form shows it: today on the
        # desktop form, but the mobile one kept the reservation's date
        # (tomorrow) - confirmed 2026-09-14 by the rental email.
        move_in = re.search(
            r"Select a Move-in Date\s*\*?\s*(\d{2}/\d{2}/\d{4})|Rent\s*\((\d{2}/\d{2}/\d{4})\s*-", text
        )
        totals = {
            "space_number": space.group(1) if space else None,
            "charges": charges,
            "security_deposit": deposit,
            "total": float(readings[-1].replace(",", "")),
            "move_in_date": (
                datetime.strptime(move_in.group(1) or move_in.group(2), "%m/%d/%Y").date()
                if move_in else None
            ),
        }
        # allure.attach(
        #     repr(totals), name="storefront lease summary", attachment_type=allure.attachment_type.TEXT
        # )
        return totals

    @log_method_exceptions
    def submit_rental(self) -> str:
        """Finishes the application one of two ways, set by the property's
        lease configuration. "Sign Agreements" (Traditional signing, confirmed
        live 2026-09-14) opens "Sign Documents", where every document is
        signed; the storefront then creates the rental with the payment
        details already entered - there is no Pay step. Otherwise the
        rental agreement box and "Pay Now". Returns "sign_agreements" or
        "pay_now"."""
        sign_agreements = self.page.get_by_role("button", name="Sign Agreements", exact=True)
        pay_now = self.page.get_by_role("button", name=re.compile(r"^Pay Now"))
        expect(sign_agreements.or_(pay_now).first).to_be_visible(timeout=self.timeout)
        if sign_agreements.first.is_visible():
            with allure.step("Sign agreements, then sign every document"):
                sign_agreements.first.click()
                try:
                    expect(self.page).to_have_url(re.compile(r"/documents/"), timeout=self.timeout)
                except AssertionError:
                    # A field the form rejects keeps it on this page (seen
                    # 2026-09-14: "Name contains invalid characters").
                    messages = self.page.get_by_text(
                        re.compile(r"invalid|required|please enter|must be", re.IGNORECASE)
                    ).filter(visible=True).all_inner_texts()
                    raise AssertionError(
                        "Sign Agreements didn't open Sign Documents - the form shows: "
                        f"{[' '.join(text.split()) for text in messages][:10]}"
                    )
                MPDocumentSigningPage(self.page, self.timeout).sign_all()
            return "sign_agreements"
        with allure.step("Agree to the rental agreement and pay now"):
            if self.page.locator("#clickwrap").count() > 0:
                tick_agreement(self.page, self.timeout)
            else:
                self.page.get_by_role("checkbox", name=re.compile(r"^I agree to the terms")).check()
            pay_now.first.click()
        return "pay_now"

    @log_method_exceptions
    def assert_rental_complete(self) -> str:
        """thank-you/?type=rental&unit_number=<space> - "You're Ready to
        Move-In!" after signing (confirmed live 2026-09-14), "You've got your
        space!" on the Pay Now path. The URL can also carry
        errorMessage=WEBSITE RENTAL COMM APP Pre on a rental that succeeded
        (2026-09-14) - not treated as a failure. Returns the space number."""
        with allure.step("Rental confirmed"):
            success = self.page.get_by_text(
                re.compile(r"You['’]re Ready to Move-In!|You['’]ve got your space!")
            ).first
            oops = self.page.get_by_text(
                re.compile(r"Oops\.\.\.\s*your rental did not go through", re.I)
            ).first
            # Race success vs failure so a declined payment fails in seconds,
            # not after self.timeout * 4 (~4 min).
            expect(success.or_(oops)).to_be_visible(timeout=self.timeout * 4)
            if oops.is_visible() and not success.is_visible():
                raise AssertionError(
                    'The storefront answered with "Oops... your rental did not go through" '
                    f"(URL {self.page.url})"
                )
            expect(success).to_be_visible(timeout=waits().short)
            match = re.search(r"[?&]unit_number=([^&#]+)", self.page.url)
            if "type=rental" not in self.page.url or not match:
                raise AssertionError(f"Not a rental confirmation page: {self.page.url}")
            return unquote(match.group(1))
