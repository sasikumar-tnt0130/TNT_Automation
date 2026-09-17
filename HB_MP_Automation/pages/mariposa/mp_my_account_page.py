import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


class MPMyAccountPage:
    """Storefront My Account (online bill pay).

    Confirmed live (2026-09-13, uat_storoutlet/Chula Vista): /account
    redirects to /login/?next=/account/ - "Login to Continue" with State /
    City / Facility selects, then a one-time code by phone or email, email +
    password, or "Create Account". A tenant rented on the storefront has no
    online account until "Create Account" (email + password, then a 6-digit
    code emailed as "<company> OTP Notification"); the rented space then
    shows by itself - no "Link a space" step. Per space, BILL PAY shows
    either "Enrolled in Autopay" + "Cancel Autopay", or "Enroll in Autopay"
    + "Rent prepay selection" + "Make Payment"; payment and enrolment share
    one card form of plain inputs (not payment-provider iframes).
    """

    @log_method_exceptions
    def __init__(self, page: Page, base_url: str, timeout: float) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout = timeout

    @log_method_exceptions
    def _read_amount(self, pattern: str) -> float:
        """Polls the page text for pattern's first group (a $ amount) -
        figures on this page render a moment after the section itself."""
        for _ in range(int(self.timeout / 500)):
            match = re.search(pattern, self.page.locator("body").inner_text())
            if match:
                return float(match.group(1).replace(",", ""))
            self.page.wait_for_timeout(waits().poll_interval)
        raise AssertionError(f"No amount matching {pattern!r} on My Account")

    @log_method_exceptions
    def open_login(self, state: str, city: str) -> None:
        with allure.step(f"Open My Account login for {city}, {state}"):
            self.page.goto(f"{self.base_url}/login/?next=%2Faccount%2F", wait_until="domcontentloaded")
            expect(self.page.get_by_text("Login to Continue").first).to_be_visible(timeout=self.timeout)
            self.page.locator("select#facility-state").select_option(label=state)
            city_select = self.page.locator("select#facility-city")
            expect(city_select.locator("option").filter(has_text=city)).to_have_count(
                1, timeout=self.timeout
            )
            city_select.select_option(label=city)
            # Each city lists its facilities by street address (Chula Vista ->
            # "1160 3rd Ave"); a single-facility city auto-selects it.
            facility = self.page.locator("select#facility-names")
            expect(facility.locator("option").first).to_be_attached(timeout=self.timeout)
            if not facility.evaluate("select => select.value"):
                facility.select_option(index=0)
            expect(self.page.locator("#emailNumber")).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def create_account(self, email: str, password: str) -> None:
        """Password rules shown live: at least 8 characters, 1 uppercase and
        1 special character. Mobile number is optional and left empty."""
        with allure.step(f"Create an online account for {email}"):
            self.page.get_by_role("button", name="Create Account", exact=True).first.click()
            expect(self.page.get_by_role("heading", name="Create an Account")).to_be_visible(
                timeout=self.timeout
            )
            self.page.locator("#create_login_email").fill(email)
            self.page.locator("#login_password").fill(password)
            self.page.locator("#login_password_confirm").fill(password)
            self.page.get_by_role("button", name="Create my account").click()
            expect(self.page.get_by_role("heading", name="Verify Email Address")).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def verify_email_code(self, code: str) -> None:
        with allure.step("Enter the emailed verification code"):
            self.page.locator("#otp").fill(code)
            self.page.get_by_role("button", name="Create Account", exact=True).last.click()
            expect(self.page).to_have_url(re.compile(r"/account/"), timeout=self.timeout)
            expect(self.page.get_by_role("heading", name="My Account")).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def assert_space_listed(self, space_number: str) -> None:
        with allure.step(f"My Account lists space {space_number}"):
            expect(
                self.page.get_by_text(re.compile(rf"Space\s+{re.escape(space_number)}")).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def cancel_autopay(self) -> None:
        """Old Robot suite's 8862. Confirmed live: no confirmation dialog -
        the button sends DELETE .../autopay and the space card switches to
        "Enroll in Autopay"."""
        with allure.step("Cancel Autopay"):
            expect(self.page.get_by_text("Enrolled in Autopay").first).to_be_visible(
                timeout=self.timeout
            )
            cancel = self.page.get_by_role("button", name="Cancel Autopay")
            cancel.first.click()
            expect(cancel).to_have_count(0, timeout=self.timeout)
            expect(self.page.get_by_text("Enroll in Autopay").first).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def _fill_billing_address(self, billing_address: dict) -> None:
        """Confirmed live (2026-09-13): "My billing address is the same as my
        mailing address" (#billingAdress-undefined) starts ticked, but on a
        freshly created account the form can reset it after it's been
        ticked - one run reached Make Payment with it unticked and the
        billing fields empty ("... is required"). So the billing block is
        always opened (a label click unticks it) and filled explicitly, as
        the old Robot suite did: #paymentAddress1-0, #paymentAddress2-0,
        #paymentZip-0, state select (aria-label "payment form state
        selection", values are state codes; its id is a literal
        "paymentState-{index}") and #paymentCity-0."""
        address1 = self.page.locator("#paymentAddress1-0")
        for _ in range(3):
            if address1.is_visible():
                break
            self.page.locator('label[for="billingAdress-undefined"]').first.click()
            try:
                expect(address1).to_be_visible(timeout=waits().tiny)
            except AssertionError:
                continue
        expect(address1).to_be_visible(timeout=self.timeout)
        address1.fill(billing_address["address1"])
        self.page.locator("#paymentAddress2-0").fill(billing_address.get("address2", ""))
        self.page.locator("#paymentZip-0").fill(billing_address["zip"])
        self.page.locator('select[aria-label="payment form state selection"]').select_option(
            billing_address["state_code"]
        )
        self.page.locator("#paymentCity-0").fill(billing_address["city"])

    @log_method_exceptions
    def _fill_card(
        self,
        card_number: str,
        card_expiry: str,
        card_cvc: str,
        name_on_card: str,
        billing_address: dict,
    ) -> None:
        """Shared card form: billing address (see _fill_billing_address),
        card number #paymentCreditCard-0, name #paymentName-0, expiry
        selects #month-0 / #year-0 (no <label> - their first option reads
        "MM *" / "YYYY *"), CVV #cvv-0."""
        self._fill_billing_address(billing_address)
        month, year = (part.strip() for part in card_expiry.split("/"))
        self.page.locator("#paymentCreditCard-0").fill(card_number)
        self.page.locator("#paymentName-0").fill(name_on_card)
        self.page.locator("#month-0").select_option(month.zfill(2))
        self.page.locator("#year-0").select_option(year if len(year) == 4 else f"20{year}")
        self.page.locator("#cvv-0").fill(card_cvc)

    @log_method_exceptions
    def pay_bill(
        self,
        card_number: str,
        card_expiry: str,
        card_cvc: str,
        name_on_card: str,
        billing_address: dict,
        months: int = 1,
    ) -> dict:
        """Old Robot suite's 8860 "Complete Pay Bill". Confirmed live: with
        autopay off, "Rent prepay selection" (values 1-12) drives "Pay
        Through <date> $X / Total To Be Charged $X"; Make Payment ->
        "Thank you for your payment! Website Payment Confirmation" listing
        the charges, "Amount paid: $X" and "Credit card: XXXX XXXX XXXX
        <last4>"."""
        with allure.step(f"Pay the bill {months} month(s) ahead"):
            prepay = self.page.locator('[aria-label="Rent prepay selection"]').first
            expect(prepay).to_be_visible(timeout=self.timeout)
            prepay.select_option(str(months))
            total_to_be_charged = self._read_amount(r"Total To Be Charged\s*\$\s*([\d,]+\.\d{2})")
            self._fill_card(card_number, card_expiry, card_cvc, name_on_card, billing_address)
            self.page.get_by_role("button", name="Make Payment").first.click()
            expect(self.page.get_by_text("Website Payment Confirmation").first).to_be_visible(
                timeout=self.timeout * 4
            )
            amount_paid = self._read_amount(r"Amount paid:\s*\$\s*([\d,]+\.\d{2})")
            card = re.search(r"Credit card:\s*(X[X\s]*\d{4})", self.page.locator("body").inner_text())
            payment = {
                "total_to_be_charged": total_to_be_charged,
                "amount_paid": amount_paid,
                "card": card.group(1).strip() if card else None,
            }
            allure.attach(repr(payment), name="my account payment", attachment_type=allure.attachment_type.TEXT)
            return payment

    @log_method_exceptions
    def enroll_autopay(
        self,
        card_number: str,
        card_expiry: str,
        card_cvc: str,
        name_on_card: str,
        billing_address: dict,
    ) -> dict:
        """Old Robot suite's 8861. Confirmed live: the space card's "Enroll in
        Autopay" checkbox (.auto-debit-checkbox) opens the same card form;
        of the two "Enroll Now" buttons (a promo banner and the form) the
        form's is the last; there are no documents to sign here -> "Thank
        you for enrolling in autopay! Website Enrollment Confirmation" with
        "Payment schedule: 1st of each month"."""
        with allure.step("Enroll in Autopay"):
            if self.page.get_by_text(re.compile(r"Website (Payment|Enrollment) Confirmation")).count():
                self.page.goto(f"{self.base_url}/account/?tab=1", wait_until="domcontentloaded")
            enroll = (
                self.page.locator(".auto-debit-checkbox")
                .filter(has_text=re.compile(r"Enroll in Autopay"))
                .locator("input[type=checkbox]")
                .first
            )
            expect(enroll).to_be_attached(timeout=self.timeout)
            if not enroll.is_checked():
                enroll.locator("xpath=ancestor::label[1]").click()
            self._fill_card(card_number, card_expiry, card_cvc, name_on_card, billing_address)
            self.page.get_by_role("button", name=re.compile(r"^Enroll Now$")).last.click()
            expect(self.page.get_by_text("Website Enrollment Confirmation").first).to_be_visible(
                timeout=self.timeout * 3
            )
            schedule = re.search(r"Payment schedule:\s*([^\n]+)", self.page.locator("body").inner_text())
            return {"payment_schedule": schedule.group(1).strip() if schedule else None}

    @log_method_exceptions
    def open_link_space_form(self) -> None:
        """Old Robot suite's 8907 entry point, moved: "Link a space to this
        account" now sits in the header My Account icon's hover pop-over
        (Account Information / Document Center / Account Settings / Link a
        space to this account / Logout) - confirmed live 2026-09-13."""
        with allure.step("Open 'Link a space to this account'"):
            if not re.search(r"/account/", self.page.url):
                self.page.goto(f"{self.base_url}/account/?tab=1", wait_until="domcontentloaded")
            self.page.get_by_role(
                "link", name=re.compile(r"access My Account", re.IGNORECASE)
            ).first.hover()
            link_button = self.page.get_by_role("button", name="Link a space to this account").first
            expect(link_button).to_be_visible(timeout=self.timeout)
            link_button.click()
            expect(self.page.get_by_role("heading", name="Link a space")).to_be_visible(
                timeout=self.timeout
            )

    def _link_space_form(self):
        return self.page.get_by_role("heading", name="Link a space").locator(
            'xpath=ancestor::*[.//button[normalize-space()="Link a space to my account"]][1]'
        )

    @log_method_exceptions
    def submit_link_space(self, state: str, city: str, unit_number: str, access_code: str) -> None:
        """Confirmed live: the form ("I'd like to link the following rental
        to my online account") has the login page's State / City /
        Facility selects plus inputs titled "Unit number" and "Access
        code"; a failed attempt resets City and Facility, so they're
        re-selected on every submit. The storefront checks the pair with
        GET .../tenant-access?spaceNumber=..&accessCode=.. (a wrong code
        -> 400 GateCodeInvalid)."""
        with allure.step(f"Submit 'Link a space' for {unit_number}"):
            form = self._link_space_form()
            form.locator("select#facility-state").select_option(label=state)
            city_select = form.locator("select#facility-city")
            expect(city_select.locator("option").filter(has_text=city)).to_have_count(
                1, timeout=self.timeout
            )
            city_select.select_option(label=city)
            facility = form.locator("select#facility-names")
            expect(facility.locator("option").first).to_be_attached(timeout=self.timeout)
            if not facility.evaluate("select => select.value"):
                facility.select_option(index=0)
            form.locator('input[title="Unit number"]').fill(unit_number)
            form.locator('input[title="Access code"]').fill(access_code)
            form.get_by_role("button", name="Link a space to my account").click()

    @log_method_exceptions
    def assert_link_refused(self, space_number: str) -> None:
        with allure.step(f"Linking {space_number} with a wrong access code is refused"):
            expect(self._link_space_form()).to_contain_text(
                "There was an error linking your space", timeout=self.timeout
            )
            expect(
                self.page.locator(".card-header").filter(has_text=f"Space {space_number}")
            ).to_have_count(0)

    @log_method_exceptions
    def assert_space_linked(self, space_number: str) -> str:
        """Confirmed live: the form closes and, after a reload, the account
        lists the linked space as its own card ("Space <space> <size>,
        <address> Autopay On") next to the account's own space - the
        cards render one after another, so the linked one is waited for
        by name. Returns that card's text."""
        with allure.step(f"Space {space_number} is linked to the account"):
            expect(self.page.get_by_role("heading", name="Link a space")).to_be_hidden(
                timeout=self.timeout
            )
            self.page.goto(f"{self.base_url}/account/?tab=1", wait_until="domcontentloaded")
            card = self.page.locator(".card-header").filter(has_text=f"Space {space_number}").first
            expect(card).to_be_visible(timeout=self.timeout)
            return re.sub(r"\s+", " ", card.inner_text()).strip()

    @log_method_exceptions
    def open_account_home(self) -> None:
        """Open /account/?tab=1. After a Legacy rental that set Account
        Password, the storefront session is already authenticated and this
        lands on My Account directly (walked 2026-09-16 stage/Garden Grove)."""
        with allure.step("Open My Account"):
            self.page.goto(
                f"{self.base_url.rstrip('/')}/account/?tab=1",
                wait_until="domcontentloaded",
            )
            expect(self.page.get_by_role("heading", name="My Account")).to_be_visible(
                timeout=self.timeout
            )

    @log_method_exceptions
    def open_account_info_tab(self) -> None:
        """ACCOUNT INFO (?tab=3): primary / alternate contact, facility info,
        space-related documents. Walked live 2026-09-16 stage/Garden Grove."""
        with allure.step("Open ACCOUNT INFO"):
            if "tab=3" not in self.page.url:
                self.page.goto(
                    f"{self.base_url.rstrip('/')}/account/?tab=3",
                    wait_until="domcontentloaded",
                )
            expect(
                self.page.get_by_text("Tenant Primary Contact Information", exact=True)
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def change_primary_mailing_address(self, new_address: dict) -> None:
        """Edit Tenant Primary Contact Information → Save → sign the
        \"Change of address - Old and New Tokens\" document.

        Walked live 2026-09-16 stage/Garden Grove (Legacy rental, PMS):
        fields account_address1 / account_address2 / account-holder-zipcode /
        account-holder-state / account-holder-city; Save opens the storefront
        document-signing widget for Change of Address."""
        with allure.step(
            f"Change primary mailing address to {new_address['address1']}, "
            f"{new_address['city']}"
        ):
            self.open_account_info_tab()
            primary = self.page.get_by_text(
                "Tenant Primary Contact Information", exact=True
            )
            expect(primary).to_be_visible(timeout=self.timeout)
            primary.locator(
                "xpath=following::button[normalize-space()='Edit'][1]"
            ).click()
            address1 = self.page.locator("#account_address1")
            expect(address1).to_be_visible(timeout=self.timeout)
            address1.fill(new_address["address1"])
            self.page.locator("#account_address2").fill(
                new_address.get("address2", "")
            )
            self.page.locator("#account-holder-zipcode").fill(new_address["zip"])
            self.page.locator("#account-holder-state").select_option(
                new_address.get("state_code") or new_address["state"]
            )
            self.page.locator("#account-holder-city").fill(new_address["city"])
            self.page.get_by_role("button", name="Save", exact=True).click()
            # Save opens the Sign Document modal with the Change of Address
            # widget (doc-title may be aria-hidden; heading + iframe are the
            # reliable signals - walked 2026-09-16).
            expect(
                self.page.get_by_role("heading", name="Sign Document")
            ).to_be_visible(timeout=self.timeout)
            expect(
                self.page.get_by_text(
                    re.compile(r"Change of address\s*-\s*Old and New", re.I)
                ).first
            ).to_be_attached(timeout=self.timeout)
            expect(
                self.page.locator('iframe[src*="document-signing"]').first
            ).to_be_attached(timeout=self.timeout)
            self._sign_change_of_address_widget()
            expect(
                self.page.get_by_role("heading", name="My Account")
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_change_of_address_in_document_center(self, space_number: str) -> None:
        """After a Change of Address save: primary contact shows the new
        mailing street, and Document Center / ACCOUNT INFO mentions Change
        of Address when the signed copy has landed."""
        with allure.step(f"Account reflects Change of Address for {space_number}"):
            self.page.goto(
                f"{self.base_url.rstrip('/')}/account/?tab=3",
                wait_until="domcontentloaded",
            )
            expect(self.page.get_by_role("heading", name="My Account")).to_be_visible(
                timeout=self.timeout
            )
            # Space-related docs / Document Center may list the COA after sign.
            coa = self.page.get_by_text(re.compile(r"Change of address", re.I))
            if coa.count() == 0:
                self.page.goto(
                    f"{self.base_url.rstrip('/')}/account/?tab=2",
                    wait_until="domcontentloaded",
                )
                coa = self.page.get_by_text(re.compile(r"Change of address", re.I))
            expect(coa.first).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def _hide_chatbot_overlays(self) -> None:
        # Walked 2026-09-16: chatbot iframes sit over the adopt-signature
        # "Accept and sign" control; force-clicks still land on the chatbot
        # and the field never gains .signed. Hiding them lets a normal click
        # complete signing.
        self.page.evaluate(
            """() => {
              for (const sel of [
                'iframe[src*="chatbot"]',
                '#alita-chatbot',
                'iframe[title="Chatbot"]',
                'iframe[title="Chatbot Launcher"]',
              ]) {
                document.querySelectorAll(sel).forEach(el => {
                  el.style.setProperty('display', 'none', 'important');
                  el.style.setProperty('pointer-events', 'none', 'important');
                  el.style.setProperty('visibility', 'hidden', 'important');
                });
              }
            }"""
        )

    @log_method_exceptions
    def _sign_change_of_address_widget(self, initials: str = "AT") -> None:
        """Sign the Change of Address widget and Finalize.

        Address changes only persist after Finalize completes and the Sign
        Document modal closes (walked 2026-09-16). Do not navigate away while
        the post-Finalize spinner is still up."""
        self._hide_chatbot_overlays()
        frame = self.page.frame_locator('iframe[src*="document-signing"]')
        sign_heading = self.page.get_by_role("heading", name="Sign Document")
        start = frame.get_by_role("button", name="Start Signing", exact=True)
        if start.count() and start.first.is_visible():
            start.first.click()
            self.page.wait_for_timeout(1000)
        finalized = False
        for _ in range(40):
            if sign_heading.count() == 0 or not sign_heading.first.is_visible():
                finalized = True
                break
            finalize = frame.get_by_role("button", name="Finalize Document")
            if (
                finalize.count()
                and finalize.first.is_visible()
                and finalize.first.is_enabled()
            ):
                finalize.first.click()
                # Iframe detaches immediately; parent modal may spin until
                # the storefront applies the address and closes the dialog.
                try:
                    expect(sign_heading).to_be_hidden(timeout=self.timeout)
                except AssertionError:
                    expect(
                        self.page.get_by_role("heading", name="My Account")
                    ).to_be_visible(timeout=self.timeout)
                finalized = True
                break
            unsigned = frame.locator("img.replaced-text:not(.signed)")
            if unsigned.count() == 0:
                next_btn = frame.get_by_role("button", name="Next", exact=True)
                if next_btn.count() and next_btn.first.is_enabled():
                    next_btn.first.click()
                    self.page.wait_for_timeout(800)
                    continue
                self.page.wait_for_timeout(500)
                continue
            field = unsigned.first
            field_id = field.get_attribute("data-id")
            field.click()
            self.page.wait_for_timeout(500)
            signed = frame.locator(
                f'img.replaced-text.signed[data-id="{field_id}"]'
            )
            if signed.count():
                continue
            signature = frame.locator("input.signature-input")
            if signature.count() and signature.first.is_visible():
                # Keep the widget's autofilled tenant name when present;
                # otherwise type initials into the adopt box.
                if not signature.first.input_value().strip():
                    signature.first.fill(initials)
                signature.first.blur()
                accept = frame.get_by_role(
                    "button", name="Accept and sign", exact=True
                )
                for _attempt in range(10):
                    if signed.count():
                        break
                    self._hide_chatbot_overlays()
                    if accept.count() and accept.first.is_visible():
                        accept.first.click()
                    self.page.wait_for_timeout(600)
                if not signed.count():
                    raise AssertionError(
                        "Change of Address Accept and sign did not mark the "
                        "signature field as signed"
                    )
            next_btn = frame.get_by_role("button", name="Next", exact=True)
            if (
                next_btn.count()
                and next_btn.first.is_visible()
                and next_btn.first.is_enabled()
            ):
                next_btn.first.click()
                self.page.wait_for_timeout(800)
        if not finalized:
            raise AssertionError(
                "Change of Address signing did not Finalize / close the "
                "Sign Document modal"
            )

    @log_method_exceptions
    def open_account_info_for_space(self, space_number: str) -> str:
        """Confirmed live: ACCOUNT INFO (?tab=3) keeps its own space
        selection - a .unit-dropdown (a.ddropbtn) listing every linked
        space plus "Link a space" - independent of BILL PAY's cards.
        Returns the page text with that space selected (its tenant's
        contact details, documents and "Remove space <space> from this
        account")."""
        with allure.step(f"ACCOUNT INFO for space {space_number}"):
            self.page.get_by_text("ACCOUNT INFO", exact=True).first.click()
            dropdown = self.page.locator(".unit-dropdown a.ddropbtn").first
            expect(dropdown).to_be_visible(timeout=self.timeout)
            dropdown.click()
            self.page.locator(".unit-dropdown .unit-header").filter(
                has_text=f"Space {space_number}"
            ).first.click()
            expect(
                self.page.get_by_text(
                    re.compile(rf"Remove space {re.escape(space_number)} from this account")
                ).first
            ).to_be_visible(timeout=self.timeout)
            return re.sub(r"\s+", " ", self.page.locator("body").inner_text())

    @log_method_exceptions
    def remove_space(self, space_number: str) -> None:
        """Confirmed live: "Remove space <space> from this account" asks
        "Remove space from My Account? This will only remove <space> from
        your online account. It will not end your lease, move you out or
        change your rental agreement..." [Confirm / Cancel]; Confirm sends
        DELETE .../items/<tenant> and the space's card disappears."""
        with allure.step(f"Remove space {space_number} from the account"):
            self.open_account_info_for_space(space_number)
            self.page.get_by_text(
                re.compile(rf"Remove space {re.escape(space_number)} from this account")
            ).first.click()
            dialog = self.page.get_by_role("dialog").filter(
                has_text=re.compile(rf"will only remove {re.escape(space_number)}")
            )
            expect(dialog).to_be_visible(timeout=self.timeout)
            dialog.get_by_role("button", name="Confirm").click()
            expect(dialog).to_be_hidden(timeout=self.timeout)
            self.page.goto(f"{self.base_url}/account/?tab=1", wait_until="domcontentloaded")
            expect(self.page.get_by_role("heading", name="My Account")).to_be_visible(
                timeout=self.timeout
            )
