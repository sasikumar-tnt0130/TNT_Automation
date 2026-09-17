import re
from datetime import date, timedelta

import allure
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from common_utils.wrapper_methods import first_visible, log_method_exceptions
from pages.mariposa.mp_rental_payment_form import (
    ensure_payment_method_offered,
    enter_ach,
    fill_billing_address,
    fill_business_representative,
    select_payment_method,
    set_autopay,
    tick_agreement,
    tick_checkbox,
)


class MPTwoStepReservationFormPage:
    """Two-Step Rental Flow: pick a unit/tier (shared with the Legacy flow
    and lives on MPUnitSearchPage; this page object picks up from unit
    selection onward, same split as MPLegacyReservationFormPage) -> a single
    consolidated form at .../rent/{unit}/v1/ offering two actions, "Rent
    Now" (immediate paid move-in) or "Reserve Now" (a no-payment hold) ->
    for "Reserve Now", straight to a "thank-you/?type=reservation"
    confirmation page with a reservation code.

    Confirmed live (2026-09-08, stage/Lightning Storage, Rutland): kept
    as its own page object rather than a shared method with
    MPLegacyReservationFormPage - the two flows differ in field set (this form
    has a required "Select a Move-in Date"), button name ("Reserve Now"
    vs "Reserve This Space"), and confirmation URL/heading. Which flow's
    form actually renders for a given session is decided once, upstream,
    by MPUnitSearchPage.wait_for_reservation_flow (the storefront has been
    observed intermittently serving one flow's form when the other was
    expected, regardless of this property's own Two-Step Rental
    setting) - callers dispatch to this page object only once that's
    confirmed, so nothing here needs to know the other flow's button
    exists at all.
    """

    @log_method_exceptions
    def __init__(self, page: Page, base_url: str, timeout: float) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout = timeout

    @log_method_exceptions
    def _dismiss_banners(self) -> None:
        """Same popups as MPUnitSearchPage._dismiss_banners (cookie consent,
        AI chat widget, mobile-native cookie popup) - this page picks up
        after the tier-selection dialog closes, which is its own
        separate SPA transition and can just as easily have any of them
        reappear on top of the reservation form underneath."""
        cookie_dialog_accept = self.page.get_by_role(
            "alertdialog", name="Cookie Consent Prompt"
        ).get_by_role("button", name="Accept", exact=True)
        if cookie_dialog_accept.count() > 0 and cookie_dialog_accept.first.is_visible():
            cookie_dialog_accept.first.click()

        mobile_cookie_popup = self.page.locator(".cookie-content-wrapper.mobile-popup")
        if mobile_cookie_popup.count() > 0 and mobile_cookie_popup.first.is_visible():
            mobile_accept = mobile_cookie_popup.first.locator(".okay-button-mobile")
            if mobile_accept.count() > 0 and mobile_accept.first.is_visible():
                mobile_accept.first.click()
            else:
                mobile_cookie_popup.first.locator(".icon-close-white").first.click()

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
    def select_move_in_date(self, days_from_today: int = 1) -> None:
        """This form's "Select a Move-in Date" field defaults to today
        and opens a calendar picker rather than accepting free text -
        selects a future date (tomorrow by default) instead of leaving
        it on today. Confirmed live (2026-09-08, stage): unlike
        MPLegacyReservationFormPage's own version of this field (a real
        <input role="textbox">), this consolidated form renders it as
        a plain <span id="reservationDate" aria-label="move in date">
        - not a form control at all, so get_by_role("textbox", ...)
        never matches it. #reservationDate is otherwise the same
        field/calendar-picker interaction (same #calendar_modal, same
        day-cell labeling) as the Legacy version - see its own
        docstring. Doesn't handle the target date falling in a
        different calendar month than the one the picker opens to (not
        needed for a same-month offset like "tomorrow")."""
        with allure.step(f"Select move-in date: {days_from_today} day(s) from today"):
            move_in_date = self.page.locator("#reservationDate")
            move_in_date.click(force=True)

            target_date = date.today() + timedelta(days=days_from_today)
            target_label = (
                target_date.strftime("%A, %B ") + str(target_date.day) + ","
            )
            target_cell = self.page.get_by_label(target_label, exact=False).last
            expect(target_cell).to_be_visible(timeout=self.timeout)
            target_cell.click()
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
            self._dismiss_banners()
            expect(
                self.page.get_by_role("textbox", name="Email *")
            ).to_be_visible(timeout=self.timeout)
            self._dismiss_banners()

        self.select_move_in_date()

        if renting_as_business:
            with allure.step(f"Fill business information: {business_name}"):
                # On a phone a sticky .storage-info bar intercepts the plain
                # click (2026-09-15, uat_storoutlet/Chula Vista).
                tick_checkbox(
                    self.page,
                    self.timeout,
                    self.page.get_by_role("checkbox", name="I am renting as a business"),
                    self.page.locator('label[for="rent-as-business"]').first,
                )
                self.page.get_by_role("textbox", name="Business Name").fill(
                    business_name or f"{first_name} {last_name} Business"
                )
                self.page.get_by_role("textbox", name="Business Phone").fill(mobile)
                self.page.get_by_role("textbox", name="Business Email").fill(email)

        with allure.step("Fill and submit the reservation form"):
            self._dismiss_banners()

            # Confirmed live (2026-09-08, stage): checking "I am renting
            # as a business" swaps the form to Business Email/Business
            # Phone/Business Name only - the personal fields below stop
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
            # Confirmed live (2026-09-08, stage): this form offers both
            # "Rent Now" (immediate paid move-in) and "Reserve Now" (the
            # no-payment hold this method creates) side by side - "Rent
            # Now" is never clicked here. "Select a Move-in Date" comes
            # pre-filled with today's date and wasn't touched - not
            # required for a reservation to succeed. Which flow's form
            # renders here at all is decided upstream, before this page
            # object is ever used - see MPUnitSearchPage.wait_for_reservation_flow.
            reserve_button = self.page.get_by_role(
                "button", name="Reserve Now", exact=True
            )
            expect(reserve_button).to_be_visible(timeout=self.timeout)
            confirmed_heading = self.page.get_by_text(
                "Your reservation is confirmed", exact=False
            ).first
            # Same server-side failure page as MPLegacyReservationFormPage
            # (thank-you/?hold=true "Please contact the facility to confirm
            # the availability of your space", no code) - waited on too so
            # it fails fast below instead of refilling a form that's gone.
            contact_facility = self.page.get_by_text(
                re.compile(r"contact the facility to confirm the availability", re.IGNORECASE)
            ).first
            submitted = confirmed_heading.or_(contact_facility).first

            def fill_required_fields() -> None:
                for field_name, field_value in required_fields.items():
                    field = self.page.get_by_role("textbox", name=field_name)
                    if field_name != "Mobile *":
                        field.fill(field_value)
                        continue
                    # Same async phone check as MPLegacyReservationFormPage
                    # (GET .../validate-phone/, invalid while pending - a
                    # click before it answers is silently dropped).
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

            # Same "Holding Space For MM:SS" countdown re-render risk as
            # MPLegacyReservationFormPage.reserve_unit - refilling and re-clicking
            # a few times self-heals against a submit silently landing
            # mid-re-render.
            max_attempts = 3
            for attempt in range(max_attempts):
                self._dismiss_banners()
                fill_required_fields()
                reserve_button.click()
                try:
                    expect(submitted).to_be_visible(
                        timeout=self.timeout / max_attempts
                    )
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

    @log_method_exceptions
    def get_reservation_code(self) -> str:
        """Confirmed live (2026-09-08, stage): unlike
        MPLegacyReservationFormPage's confirmation page (label and code as two
        separate sibling paragraphs), this one renders "Reservation
        Code: XYZ123" (no "Your", unlike Legacy's "Your reservation
        code:") inline within one larger block of confirmation text -
        there's no separate element boundary between label and code to
        select across. Extracted with a regex against that whole
        block's text instead."""
        with allure.step("Read reservation code"):
            pattern = re.compile(r"Reservation Code:\s*([A-Z0-9]+)", re.IGNORECASE)
            container = self.page.get_by_text(pattern).first
            expect(container).to_be_visible(timeout=self.timeout)
            match = pattern.search(container.text_content() or "")
            if not match:
                raise AssertionError(
                    "Reservation code pattern not found in confirmation text"
                )
            value = match.group(1)
            allure.attach(
                value, name="reservation code", attachment_type=allure.attachment_type.TEXT
            )
            return value

    @staticmethod
    def _money(text: str) -> float:
        value = float(re.sub(r"[^\d.]", "", text) or 0)
        return -value if "-" in text else value

    _SIDEBAR_SUMMARY = """box => ({
        text: box.innerText,
        space: (box.querySelector('.unit-size') || {}).innerText || '',
        charges: [...box.querySelectorAll('.payment-row')]
            .filter(row => row.querySelector('.price'))
            .map(row => [row.innerText, row.querySelector('.price').innerText]),
        total: (box.querySelector('.total .cost') || {}).innerText || '',
    })"""
    _MOVE_IN_TOTAL = "Total Cost to Move-in:"
    _CHARGE = re.compile(r"([^$\n][^$]*?)\s*(-\s*\$\s*[\d,]+(?:\.\d+)?|\$\s*[\d,]+(?:\.\d+)?)")

    def _phone_summary_label(self):
        return self.page.get_by_text(self._MOVE_IN_TOTAL).locator("visible=true").first

    def _wait_for_phone_summary(self) -> None:
        """Waits for the phone layout's visible summary, opening its drawer
        once if it doesn't show."""
        label = self._phone_summary_label()
        try:
            expect(label).to_be_visible(timeout=self.timeout / 4)
        except AssertionError:
            drawer = self.page.get_by_role("button", name="Click here to expand or collapse the drawer")
            if drawer.count():
                first_visible(drawer).click()
            expect(label).to_be_visible(timeout=self.timeout)

    def _phone_summary_snapshot(self) -> dict:
        """The phone layout's visible summary block, read from its text into
        the shape of the sidebar's snapshot (see read_lease_summary)."""
        text = self._phone_summary_label().locator(
            "xpath=ancestor-or-self::*[contains(., 'Monthly Rent')][1]"
        ).inner_text()
        space = re.search(r"#\S+\s*\|", text)
        if space:
            space_text = space.group(0)
        else:
            candidates = self.page.get_by_text(re.compile(r"^#\w+$"))
            space_text = first_visible(candidates).inner_text() if candidates.count() else ""
        rows = re.split(r"monthly rent", text, maxsplit=1, flags=re.I)[-1]
        rows = re.split(r"\btotal:", rows, maxsplit=1, flags=re.I)[0]
        total = re.search(r"total cost to move-in:\s*(-?\s*\$\s*[\d,]+(?:\.\d+)?)", text, re.I)
        return {
            "text": text,
            "space": space_text,
            "charges": [(f"{label} {amount}", amount) for label, amount in self._CHARGE.findall(rows)],
            "total": total.group(1) if total else "",
        }

    @log_method_exceptions
    def read_lease_summary(self) -> dict:
        """The rental form's "Lease Summary" sidebar (.unit-sidebarwrapper -
        the same container the old Robot suite read for 8900). Confirmed
        live (2026-09-13, uat_storoutlet/Chula Vista, resumed from the
        reservation email's "Rent Now"): "#<space> | <size>" (.unit-size),
        IN-STORE / WEB RATE rows (.web_rt: .row1 label, .row2 amount),
        charge rows (.payment-row: label + .price - prorated rent, the
        promotion as "- $x", security deposit, protection plan, tax) and
        "Total Cost to Move-in:" (.total .cost), which the "Pay Now $x"
        button repeats. Read-only - Pay Now is never clicked.

        Also confirmed live: the sidebar renders twice - first with stale
        figures (rent from yesterday, total $117.53), then blanks and
        re-renders about two seconds later with the real ones ($112.40) -
        so the total is read only once it has held for 3 s; the summary box
        sits inside an outer .unit-sidebarwrapper (innermost one used, the
        outer repeats every row); one .payment-row is an empty spacer with
        no .price (skipped); and WEB RATE isn't a .web_rt row in the inner
        box, so both rates come from its text. Rows are read in a single
        evaluate so a late re-render can't leave half-stale locators.

        Phone layout (2026-09-15, uat_storoutlet/Chula Vista, iPhone 13): the
        sidebar box is in the page but hidden, with stale figures (total
        $50.00 while the page showed $52.00); the summary the guest sees sits
        at the top of the form above a "Click here to expand or collapse the
        drawer" button - "#OP10 | 10' x 10' Space", "IN-STORE $60 Web Rate
        $50", "Monthly Rent Rent (Prorated) (09/15/2026 - 09/30/2026) $26.67
        Security Deposit $ 20.00 Apex-Optima Protection Plan P1 $ 5.33 Total
        Tax $ 0.00 Total: $52.00 Total Cost to Move-in: $52.00". Only its aria
        snapshot was captured, not its markup, so on a phone that block is
        read from its visible text."""
        with allure.step("Read Lease Summary"):
            if (self.page.viewport_size or {}).get("width", 1920) < 768:
                self._wait_for_phone_summary()
                read_summary = self._phone_summary_snapshot
            else:
                summary = first_visible(
                    self.page.locator(".unit-sidebarwrapper:not(:has(.unit-sidebarwrapper))")
                )
                expect(summary.locator(".total .cost").first).to_be_visible(timeout=self.timeout)

                def read_summary() -> dict:
                    return summary.evaluate(self._SIDEBAR_SUMMARY)

            readings: list[str | None] = []
            for _ in range(int(self.timeout / 500)):
                readings.append(read_summary()["total"].strip() or None)
                if readings[-1] and len(readings) >= 6 and len(set(readings[-6:])) == 1:
                    break
                self.page.wait_for_timeout(500)
            else:
                raise AssertionError(f"Lease Summary total never settled: {readings[-8:]}")

            snapshot = read_summary()
            space = re.search(r"#([^\s|]+)", snapshot["space"])
            rates = {
                label: self._money(match.group(1))
                for label in ("IN-STORE", "WEB RATE")
                if (match := re.search(rf"{label}\s*(\$\s*[\d,]+(?:\.\d+)?)", snapshot["text"], re.I))
            }
            charges = {}
            for row_text, amount_text in snapshot["charges"]:
                row_text = re.sub(r"\s+", " ", row_text).strip()
                amount_text = re.sub(r"\s+", " ", amount_text).strip()
                charges[row_text.replace(amount_text, "").strip()] = self._money(amount_text)
            # Confirmed live (2026-09-13, stage/Rutland): a property that signs
            # the lease before payment ends the form with "Sign Agreements"
            # instead, with no amount on it - pay_now is None there.
            action_text = first_visible(
                self.page.get_by_role("button", name=re.compile(r"Pay Now|Sign Agreements"))
            ).inner_text()
            lease_summary = {
                "space_number": space.group(1) if space else None,
                "rates": rates,
                "charges": charges,
                "total": self._money(snapshot["total"]),
                "pay_now": self._money(action_text) if "Pay Now" in action_text else None,
            }
            allure.attach(
                repr(lease_summary), name="storefront lease summary",
                attachment_type=allure.attachment_type.TEXT,
            )
            return lease_summary

    @log_method_exceptions
    def pay_rental_by_card(
        self,
        card_number: str,
        card_expiry: str,
        card_cvc: str,
        name_on_card: str,
        zip_code: str,
        enroll_autopay: bool = True,
    ) -> None:
        """The resumed rental page's Payment Method section. Confirmed live
        (2026-09-13, uat_storoutlet/Chula Vista): "Autopay Enrollment"
        (#auto-debit) and the rental agreement box (#clickwrap) are
        custom-styled checkboxes ticked through their labels; card number,
        expiry and CVV are Global Payments hosted fields - one iframe each
        (name="card-number" / "card-expiration" / "card-cvv") whose inputs
        take typed keystrokes (the expiry reformats "1234" to "12 / 2034");
        Name on Card (#name) and ZIP (#billingZip) are plain inputs.

        Also confirmed live (2026-09-13, stage/Rutland): no payment method
        is pre-selected (Apple Pay / Google Pay / Credit Card / ACH radios)
        and the card fields only render once Credit Card is chosen; they're
        plain inputs there (#creditCardNumber, #expiry "MM/YY", #cvv), with
        no ZIP field; and a Termly cookie banner can sit over the form."""
        with allure.step(
            "Pay the rental by credit card" + (" with autopay" if enroll_autopay else "")
        ):
            self._dismiss_cookie_banner()
            autopay = self.page.locator("#auto-debit")
            if autopay.is_checked() != enroll_autopay:
                self.page.locator('label[for="auto-debit"]').first.click()
            expect(autopay).to_be_checked(checked=enroll_autopay, timeout=self.timeout)
            card_method = self.page.locator('input[type="radio"][value="card"]')
            if card_method.count() > 0 and not card_method.first.is_checked():
                self.page.locator('label:has(input[type="radio"][value="card"])').first.click()
                expect(card_method.first).to_be_checked(timeout=self.timeout)
            hosted_number = self.page.locator('iframe[name="card-number"]')
            plain_number = self.page.locator("#creditCardNumber")
            expect(hosted_number.or_(plain_number).first).to_be_visible(timeout=self.timeout)
            expiry_digits = re.sub(r"\D", "", card_expiry)
            if hosted_number.count() > 0:
                card_fields = [
                    self.page.frame_locator(f'iframe[name="{frame_name}"]').locator("input").first
                    for frame_name in ("card-number", "card-expiration", "card-cvv")
                ]
            else:
                card_fields = [plain_number, self.page.locator("#expiry"), self.page.locator("#cvv")]
            card_values = list(zip(card_fields, (card_number, expiry_digits, card_cvc)))
            for card_field, value in card_values:
                self._type_card_field(card_field, value)
            self.page.locator("#name").fill(name_on_card)
            billing_zip = self.page.locator("#billingZip")
            if billing_zip.count() > 0:
                billing_zip.fill(zip_code)
            tick_agreement(self.page, self.timeout)
            # Card with autopay as a business (2026-09-15, Chula Vista): Pay
            # Now met "Invalid Card Number" with the number field empty - the
            # hosted fields were redrawn after typing - so they're re-checked
            # right before paying.
            for card_field, value in card_values:
                if not self._card_field_holds(card_field, value):
                    self._type_card_field(card_field, value)
            self._watch_rental_response()
            self.page.get_by_role("button", name=re.compile(r"^Pay Now")).first.click()

    @log_method_exceptions
    def fill_business_representative(self, guest: dict, rental_data: dict) -> None:
        """Renting as a business: the Two-Step rental form also carries an
        empty, required "Business Representative Information" block (Email,
        Mobile, First/Last Name - confirmed 2026-09-15), which blocks Pay Now
        until filled. See mp_rental_payment_form.fill_business_representative."""
        fill_business_representative(self.page, self.timeout, guest, rental_data)

    @log_method_exceptions
    def pay_rental_by_ach(
        self,
        name_on_account: str,
        routing_number: str,
        account_number: str,
        billing_address: dict,
        enroll_autopay: bool = True,
    ) -> None:
        """pay_rental_by_card's ACH / E-Check counterpart. The fields are
        taken to be the same component as the Legacy form's (confirmed live
        2026-09-14, uat_storoutlet/Bellflower - see mp_rental_payment_form);
        ACH on uat_storoutlet's Two-Step form hasn't been seen yet."""
        with allure.step("Pay the rental by ACH" + (" with autopay" if enroll_autopay else "")):
            self._dismiss_cookie_banner()
            ensure_payment_method_offered(
                self.page,
                self.timeout,
                "ach",
                self.page.get_by_role("button", name=re.compile(r"^Pay Now|^Sign Agreements")).first,
            )
            set_autopay(self.page, self.timeout, enroll_autopay)
            select_payment_method(self.page, self.timeout, "ach")
            enter_ach(self.page, self.timeout, name_on_account, routing_number, account_number)
            fill_billing_address(self.page, self.timeout, billing_address)
            tick_agreement(self.page, self.timeout)
            self._watch_rental_response()
            self.page.get_by_role("button", name=re.compile(r"^Pay Now")).first.click()

    @log_method_exceptions
    def _dismiss_cookie_banner(self) -> None:
        """Confirmed live (2026-09-13, stage): a Termly "Cookie Consent
        Manager" banner (Preferences / Decline / Accept) can sit over the
        middle of the form - declined when it shows."""
        banner = self.page.get_by_text("Cookie Consent Manager", exact=False).first
        if banner.count() > 0 and banner.is_visible():
            self.page.get_by_role("button", name="Decline", exact=True).first.click()
            expect(banner).to_be_hidden(timeout=self.timeout)

    @staticmethod
    def _card_field_holds(card_field, value: str) -> bool:
        """A masked field ("•••• 1111") counts as filled; the expiry is
        reformatted ("1234" -> "12 / 2034"), so it holds its value when its
        digits keep the month and end with the year's last two."""
        try:
            text = card_field.input_value(timeout=5000)
        except Exception:
            return False
        if re.search(r"[•*●]", text):
            return True
        digits, expected = re.sub(r"\D", "", text), re.sub(r"\D", "", value)
        return digits == expected or (
            len(expected) == 4 and digits[:2] == expected[:2] and digits.endswith(expected[2:])
        )

    def _type_card_field(self, card_field, value: str) -> None:
        """Types a card field, retyping (3 tries) until it holds the value -
        the value itself is never reported."""
        for _ in range(3):
            card_field.click()
            card_field.fill("")
            card_field.press_sequentially(value, delay=40)
            if self._card_field_holds(card_field, value):
                return
        raise AssertionError("A card field didn't keep the typed value after 3 tries")

    def _watch_rental_response(self) -> None:
        """Records the storefront's POST .../rentals after Pay Now - its
        status, and for an error its message fields only: a successful body
        carries a session token and signed document links, never kept."""
        self._rental_responses: list[dict] = []

        def record(response) -> None:
            if response.request.method != "POST" or not re.search(r"/rentals/?(\?|$)", response.url):
                return
            entry: dict = {"status": response.status}
            if response.status >= 400:
                try:
                    body = response.json()
                except Exception:
                    body = {}
                if isinstance(body, dict):
                    entry.update(
                        {key: str(body[key])[:300] for key in ("message", "error", "errorMessage", "code", "detail") if key in body}
                    )
            self._rental_responses.append(entry)

        self.page.on("response", record)

    @log_method_exceptions
    def assert_rental_complete(self, space_number: str) -> None:
        """Confirmed live (2026-09-13): Pay Now goes to .../finalise/ ("We are
        processing your lease!") for a minute or two, then to
        .../v1/thank-you/?type=rental&unit_number=<space> - "You've got your
        space! Finish up below for access".

        Also seen (2026-09-15, Chula Vista, card with autopay as a business,
        twice): the storefront ends on "Oops... your rental did not go
        through" instead - that fails at once, with the rentals response
        recorded by _watch_rental_response."""
        with allure.step(f"Rental confirmed for space {space_number}"):
            confirmed = self.page.get_by_text("You've got your space!", exact=False).first
            not_through = self.page.get_by_text("your rental did not go through", exact=False).first
            # Or Pay Now is refused on the form itself (2026-09-15).
            invalid_card = self.page.get_by_text("Invalid Card Number", exact=False).locator("visible=true").first
            expect(confirmed.or_(not_through).or_(invalid_card).first).to_be_visible(timeout=self.timeout * 4)
            if invalid_card.is_visible():
                raise AssertionError('Pay Now was refused: the card form shows "Invalid Card Number"')
            if not confirmed.is_visible():
                raise AssertionError(
                    'The storefront answered Pay Now with "Oops... your rental did not go through" '
                    f"(URL {self.page.url}); its POST .../rentals responses: "
                    f"{getattr(self, '_rental_responses', None)}"
                )
            expect(self.page).to_have_url(
                re.compile(rf"type=rental.*unit_number={re.escape(space_number)}")
            )

    @log_method_exceptions
    def verify_id_later_and_get_access(self, rental_data: dict) -> None:
        """Confirmed live (2026-09-13): after the rental, "Renter Identity
        Verification" offers Verify ID Now (photo ID + selfie) or Verify ID
        Later; Later ("you may not receive your gate code immediately")
        opens a Mailing Address form. Typing in its free-text Address box
        reveals the structured address fields, which stay empty unless an
        autocomplete suggestion is picked - so they're filled directly -
        and the licence expiry input sits under its floating label, so it's
        filled rather than clicked. "Get Access" saves it all and then
        disappears; no gate code is shown when ID is verified later."""
        with allure.step("Verify ID later and submit mailing address and licence"):
            self.page.get_by_role("button", name=re.compile(r"Verify ID Later")).click()
            mailing_address = self.page.get_by_role("heading", name="Mailing Address")
            expect(mailing_address).to_be_visible(timeout=self.timeout)
            mailing_address.locator("xpath=following::input[@type='text'][1]").fill(
                f"{rental_data['address1']}, {rental_data['address2']}, "
                f"{rental_data['city']}, {rental_data['state_code']} {rental_data['zip']}"
            )
            self.page.keyboard.press("Escape")
            address1 = self.page.locator("#idtenant_contactaddress1")
            expect(address1).to_be_visible(timeout=self.timeout)
            address1.fill(rental_data["address1"])
            self.page.locator("#idtenant_contactaddress2").fill(rental_data["address2"])
            self.page.locator("#idtenant_contactzip").fill(rental_data["zip"])
            self.page.locator("#idtenant_contactcity").fill(rental_data["city"])
            self.page.locator("#idtenant_contactstate").select_option(label=rental_data["state"])
            self.page.locator("#iddrivers_licensedrivers_license_number").fill(
                rental_data["drivers_license_number"]
            )
            self.page.locator("#iddrivers_licensedrivers_license_state").select_option(
                label=rental_data["drivers_license_state"]
            )
            self.page.locator("#iddrivers_licensedrivers_license_expiration_date").fill(
                rental_data["drivers_license_expiration"]
            )
            get_access = self.page.get_by_role("button", name="Get Access")
            get_access.click()
            expect(get_access).to_be_hidden(timeout=self.timeout)
