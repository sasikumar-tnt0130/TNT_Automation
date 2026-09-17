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
    """Legacy Flow: "Reserve This Space" (a no-payment hold) -> resume the
    reservation via "Rent online now" -> complete the consolidated rental
    application (guest info, notice delivery, payment, agreement) ->
    move-in confirmation.

    Storefront search/unit-selection is shared with the direct-rent flow
    and lives on MPUnitSearchPage; this page object picks up from the unit
    selection page (the "Reserve This Space" form) onward.

    Confirmed live (2026-09-14, uat_storoutlet/Bellflower): the resumed
    reservation's application now has an account password, an alternate
    contact, Renter Identity Verification and a protection plan before
    payment (fill_rental_application), Card or ACH with one autopay box
    (pay_with), and ends one of two ways by the property's lease
    configuration (submit_rental) - "Sign Agreements" and a separate
    document-signing step with Traditional signing (Clickwrap off), or the
    agreement box and "Pay Now". The 2026-09-07 stage walk found a single
    form with no signing step whatever the configuration; that no longer
    holds.
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
        # MPUnitSearchPage._dismiss_banners for details. Scoped by class, so
        # runs unconditionally even while a real dialog is open.
        mobile_cookie_popup = self.page.locator(".cookie-content-wrapper.mobile-popup")
        if mobile_cookie_popup.count() > 0 and mobile_cookie_popup.first.is_visible():
            mobile_accept = mobile_cookie_popup.first.locator(".okay-button-mobile")
            if mobile_accept.count() > 0 and mobile_accept.first.is_visible():
                mobile_accept.first.click()
            else:
                mobile_cookie_popup.first.locator(".icon-close-white").first.click()

        # Unscoped, so skipped while any in-flow modal is open - see
        # MPUnitSearchPage._dismiss_banners for why (confirmed live,
        # 2026-09-08: this exact class of unscoped text match closed the
        # tier-selection dialog there instead of a banner).
        if self.page.get_by_role("dialog").count() == 0:
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
    def select_move_in_date(self, days_from_today: int = 1) -> None:
        """The "Reserve This Space" move-in date field defaults to
        today and opens a calendar picker rather than accepting free
        text - selects a future date (tomorrow by default) instead of
        leaving it on today. Doesn't handle the target date falling in
        a different calendar month than the one the picker opens to
        (not needed for a same-month offset like "tomorrow")."""
        with allure.step(f"Select move-in date: {days_from_today} day(s) from today"):
            # The form's "Submit" variant (seen once, 2026-09-14, mobile) has a
            # plain textbox "date" ("Move-in date (MM/DD/YYYY) *"), no picker.
            variant_date = self.page.get_by_role("textbox", name="date", exact=True)
            if variant_date.count() > 0 and variant_date.first.is_visible():
                target_date = date.today() + timedelta(days=days_from_today)
                variant_date.first.fill(target_date.strftime("%m/%d/%Y"))
                variant_date.first.press("Tab")
                return
            # This page can render two "move in date" fields at once -
            # one on the "Rent Online Today" section above, one on
            # "Reserve This Space" below it - both sharing this same
            # accessible name (confirmed live, 2026-09-08, stage). The
            # Reserve This Space one is always the second/last in DOM
            # order.
            move_in_date = self.page.get_by_role(
                "textbox", name=re.compile(r"move.?in date", re.IGNORECASE)
            ).last
            # A floating field label (and, near the top of the
            # viewport, the sticky nav header) can sit directly over
            # this field's click point once it has a value - force
            # bypasses that overlap instead of waiting out an
            # actionability check that never clears.
            move_in_date.click(force=True)

            target_date = date.today() + timedelta(days=days_from_today)
            # Each calendar day has its own accessible label ("Tuesday,
            # September 1,") on the date cell itself. Trailing comma
            # matters: e.g. Sept 1 and Sept 15, 2026 are both Tuesdays,
            # so "September 1" alone is a substring of "September 15" -
            # "September 1," is not.
            target_label = (
                target_date.strftime("%A, %B ") + str(target_date.day) + ","
            )
            target_cell = self.page.get_by_label(target_label, exact=False).last
            expect(target_cell).to_be_visible(timeout=self.timeout)
            target_cell.click()
            # The modal's own close animation/network round-trip isn't
            # instant - leaving it open intercepts every later click on
            # this page (including the eventual "Reserve This Space"
            # submit) until it actually finishes closing.
            expect(self.page.locator("#calendar_modal")).to_be_hidden(
                timeout=self.timeout
            )

    @log_method_exceptions
    def reserve_unit(
        self,
        email: str,
        mobile: str,
        first_name: str,
        last_name: str,
        renting_as_business: bool = False,
        business_name: str | None = None,
    ) -> None:
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

        self.select_move_in_date()

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
                        self.select_move_in_date()
                        expect(business_checkbox).to_be_visible(timeout=self.timeout)
                business_checkbox.check()
                self.page.get_by_role("textbox", name="Business Name").fill(
                    business_name or f"{first_name} {last_name} Business"
                )
                self.page.get_by_role("textbox", name="Business Phone").fill(mobile)
                self.page.get_by_role("textbox", name="Business Email").fill(email)

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
                    # that lookup for these digits; a refill with an
                    # unchanged value may not re-trigger it, hence the pass.
                    digits = re.sub(r"\D", "", field_value)
                    try:
                        with self.page.expect_response(
                            lambda response: "/validate-phone/" in response.url
                            and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                            timeout=10000,
                        ):
                            field.fill(field_value)
                    except PlaywrightTimeoutError:
                        pass

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
                expect(radio.first).to_be_checked(timeout=5000)
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
    def fill_rental_application(self, rental_data: dict, alternate: dict, guest: dict | None = None) -> None:
        """The resumed reservation's rental application, up to payment.
        Confirmed live (2026-09-14, uat_storoutlet/Bellflower, reservation
        64W1X4): it renders about 10 s after "Rent online now" changes the
        URL; email, name and mobile come pre-filled from the reservation.
        New since the Robot suite: a required "Account Password" (the rental
        creates the online account), an alternate contact block that is
        always shown, five "Additional Information" yes/no questions, a
        Protection Plan and Renter Identity Verification before payment."""
        with allure.step("Fill the rental application"):
            expect(self.page.locator("#idtenantemail")).to_be_visible(timeout=self.timeout * 2)
            self._dismiss_banners()
            password = self.page.locator("#idtenantpassword")
            if password.count() > 0 and password.is_visible() and not password.input_value():
                password.fill(rental_data["account_password"])
            self._check_radio("id_notice_deliveryemail")
            for question in ADDITIONAL_QUESTIONS:
                if self.page.locator(f'[id^="id_{question}"]:checked').count() == 0:
                    self._check_radio(f"id_{question}no")
            self._fill_alternate_contact(rental_data, alternate)
            coverage = self.page.locator('input[id^="coverageAmount-ins"]')
            if coverage.count() > 0:
                # The first plan offered ($2,000 on Bellflower). Its "Coverage
                # Amount" button left the radio unticked in the walk.
                self._check_radio(coverage.first.get_attribute("id"))
            self._verify_id_later(rental_data)
            if guest is not None:
                self._fill_business_representative(guest, rental_data)

    @log_method_exceptions
    def _fill_alternate_contact(self, rental_data: dict, alternate: dict) -> None:
        """Always shown and required (confirmed live 2026-09-14) - filled
        with a fictional contact from test_identities.new_additional_contact:
        a Mailinator email and a (707) 555-01xx number."""
        first_name = self.page.locator("#idalternatefirst_name")
        if not first_name.is_visible():
            return
        digits = alternate["phone_number"]
        if not re.fullmatch(r"(707|714)55501\d\d", digits):
            raise ValueError(f"Alternate contact number {digits} isn't a fictional 555-01xx number")
        with allure.step(f"Alternate contact: {alternate['first_name']} {alternate['last_name']}"):
            first_name.fill(alternate["first_name"])
            self.page.locator("#idalternatelast_name").fill(alternate["last_name"])
            self.page.locator("#idalternateemail").fill(alternate["email"])
            # Same async phone check as the reservation form's Mobile field.
            try:
                with self.page.expect_response(
                    lambda response: "/validate-phone/" in response.url
                    and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                    timeout=10000,
                ):
                    self.page.locator("#phonealternate").fill(
                        f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                    )
            except PlaywrightTimeoutError:
                pass
            self.page.locator("#idalternateaddress1").fill(rental_data["address1"])
            self.page.locator("#idalternateaddress2").fill(rental_data["address2"])
            self.page.locator("#idalternatezip").fill(rental_data["zip"])
            select_state(
                self.page.locator("#idalternatestate"), rental_data["state"], rental_data["state_code"]
            )
            self.page.locator("#idalternatecity").fill(rental_data["city"])

    @log_method_exceptions
    def _verify_id_later(self, rental_data: dict) -> None:
        """Renter Identity Verification sits inside this form, before
        payment (confirmed live 2026-09-14) - the Two-Step form asks after
        the rental. "Verify ID Later" reveals the tenant's mailing address
        and driver's licence fields, filled directly."""
        later = self.page.get_by_role("button", name=re.compile(r"Verify ID Later"))
        if later.count() == 0 or not later.first.is_visible():
            return
        with allure.step("Verify ID later: mailing address and licence"):
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
        Mailinator email and fictional (714) 555-01xx mobile."""
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
        """The Lease Summary's space ("#0094 | 8' x 5'"), Security Deposit and
        "Total Cost to Move-in: $X", read once the total has held for 3 s -
        the protection plan and proration change it while the form fills
        (confirmed live 2026-09-14: $177.20 before the $2,000 plan, $188.53
        on the signed lease after it)."""
        with allure.step("Read the Lease Summary"):
            total_pattern = re.compile(r"Total Cost to Move-in:\s*\$([\d,]+\.\d{2})")
            readings: list[str | None] = []
            text = ""
            for _ in range(int(self.timeout / 500)):
                text = self.page.locator("body").inner_text()
                total = total_pattern.search(text)
                readings.append(total.group(1) if total else None)
                if readings[-1] and len(readings) >= 6 and len(set(readings[-6:])) == 1:
                    break
                self.page.wait_for_timeout(500)
            else:
                raise AssertionError(f"Lease Summary total never settled: {readings[-6:]}")
            space = re.search(r"#(\S+)\s*\|", text)
            deposit = re.search(r"Security Deposit\s*\$([\d,]+\.\d{2})", text)
            # The rental's move-in date, as the form shows it: today on the
            # desktop form, but the mobile one kept the reservation's date
            # (tomorrow) - confirmed 2026-09-14 by the rental email.
            move_in = re.search(
                r"Select a Move-in Date\s*\*?\s*(\d{2}/\d{2}/\d{4})|Rent\s*\((\d{2}/\d{2}/\d{4})\s*-", text
            )
            totals = {
                "space_number": space.group(1) if space else None,
                "security_deposit": float(deposit.group(1).replace(",", "")) if deposit else None,
                "total": float(readings[-1].replace(",", "")),
                "move_in_date": (
                    datetime.strptime(move_in.group(1) or move_in.group(2), "%m/%d/%Y").date()
                    if move_in else None
                ),
            }
            allure.attach(
                repr(totals), name="storefront lease summary", attachment_type=allure.attachment_type.TEXT
            )
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
            with allure.step("Sign Agreements, then sign every document"):
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
        with allure.step("Agree to the rental agreement and Pay Now"):
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
            expect(
                self.page.get_by_text(re.compile(r"You['’]re Ready to Move-In!|You['’]ve got your space!")).first
            ).to_be_visible(timeout=self.timeout * 4)
            match = re.search(r"[?&]unit_number=([^&#]+)", self.page.url)
            if "type=rental" not in self.page.url or not match:
                raise AssertionError(f"Not a rental confirmation page: {self.page.url}")
            return unquote(match.group(1))
