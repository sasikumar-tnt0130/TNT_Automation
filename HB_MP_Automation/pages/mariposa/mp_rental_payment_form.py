"""The storefront rental application's Payment Method section and billing
address - one component on both rental forms (MPLegacyReservationFormPage,
MPTwoStepReservationFormPage). Confirmed live 2026-09-14 on
uat_storoutlet/Bellflower's Legacy form:

- "Autopay Enrollment" (#auto-debit) is a single custom-styled checkbox for
  every payment method, ticked through its label.
- Credit Card / ACH / E-Check are radios (value "card" / "ach"), neither
  pre-selected; each method's fields render only once it's chosen.
- Credit Card: Global Payments hosted fields - one iframe each
  (card-number / card-expiration / card-cvv) taking typed keystrokes - and
  "Name on Card" (#name). Stage's Two-Step form showed plain inputs instead
  (#creditCardNumber, #expiry, #cvv - 2026-09-13).
- ACH / E-Check: Name on Account, Routing Number, Account Number and Confirm
  Account Number, whose ids literally carry quotes ("'routingNumber'-1") -
  matched by prefix.
- Billing address: a free-text "Billing Address" box; typing in it reveals
  #billingAddress1/2, #billingZip, #billingState and #billingCity, which stay
  empty unless filled directly (like the mailing address)."""
import re

import allure
from playwright.sync_api import Locator, Page, Response, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ACH_FIELD_IDS = ("'nameOnAccount'", "'routingNumber'", "'accountNumber'", "'confirmAccountNumber'")
# The form's gateway settings request, e.g. GET .../companies/<co>/properties/
# <property>/gateway (seen in the 2026-09-14 walk's network log).
GATEWAY_SETTINGS = re.compile(r"/properties/[^/?#]+/gateway")


def select_state(select: Locator, state: str, state_code: str) -> None:
    """Picks a state by its name, or by its code where the options are codes."""
    labels = [label.strip() for label in select.locator("option").all_inner_texts()]
    if state in labels:
        select.select_option(label=state)
    else:
        select.select_option(value=state_code)


def set_autopay(page: Page, timeout: float, enroll: bool) -> None:
    autopay = page.locator("#auto-debit")
    if autopay.count() == 0:
        if enroll:
            raise AssertionError("The rental form has no Autopay Enrollment checkbox")
        return
    if autopay.is_checked() != enroll:
        page.locator('label[for="auto-debit"]').first.click()
    expect(autopay).to_be_checked(checked=enroll, timeout=timeout)


def _attach_payment_section(page: Page) -> None:
    text = page.locator("body").inner_text()
    start = text.find("Payment Method")
    allure.attach(
        text[start:start + 800] if start >= 0 else text[:800],
        name="payment section", attachment_type=allure.attachment_type.TEXT,
    )
    allure.attach(
        page.screenshot(full_page=True), name="rental form", attachment_type=allure.attachment_type.PNG
    )


def payment_method_offered(page: Page, timeout: float, method: str) -> bool:
    """Whether the Payment Method section offers `method` ("card" or "ach"),
    once it has rendered. ACH gets 15 s more than the section itself, in
    case its radio follows the card's."""
    method_radios = page.locator('input[type="radio"][value="card"], input[type="radio"][value="ach"]')
    card_fields = page.locator('iframe[name="card-number"], #creditCardNumber')
    try:
        expect(method_radios.or_(card_fields).first).to_be_attached(timeout=timeout)
    except AssertionError:
        return False
    radio = page.locator(f'input[type="radio"][value="{method}"]')
    if method == "card":
        return radio.count() > 0 or page.locator('input[type="radio"][value="ach"]').count() == 0
    try:
        expect(radio.first).to_be_attached(timeout=15000)
        return True
    except AssertionError:
        return False


def _gateway_summary(response: Response) -> dict:
    """The gateway settings response's status and its true/false ACH/check
    flags only - never keys, IDs or other values."""
    summary: dict = {"status": response.status}
    try:
        data = response.json()
    except Exception:
        return summary
    flags: dict = {}

    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value[:20]):
                walk(child, f"{path}[{index}]")
        elif re.search(r"ach|check", path, re.IGNORECASE) and (isinstance(value, bool) or value is None):
            flags[path] = value

    walk(data, "")
    summary["ach/check flags"] = flags
    return summary


def ensure_payment_method_offered(page: Page, timeout: float, method: str, form_ready: Locator) -> None:
    """Bellflower's rental form offered ACH / E-Check only sometimes - missing
    in 2 of 6 forms on 2026-09-14 for the same space - so when `method`
    isn't offered the form is reloaded once (user choice 2026-09-14), and the
    case fails, with evidence, only when it's still missing. A reload that
    helped is recorded too, so the flakiness stays visible."""
    label = "ACH / E-Check" if method == "ach" else "Credit Card"
    if payment_method_offered(page, timeout, method):
        return
    with allure.step(f"{label} not offered - reload the rental form once"):
        gateway: dict = {"gateway settings request": "not seen after the reload"}
        try:
            with page.expect_response(lambda response: bool(GATEWAY_SETTINGS.search(response.url)), timeout=timeout) as info:
                page.reload(wait_until="domcontentloaded")
            gateway = _gateway_summary(info.value)
        except PlaywrightTimeoutError:
            pass
        allure.attach(repr(gateway), name="gateway settings after reload", attachment_type=allure.attachment_type.TEXT)
        expect(form_ready).to_be_visible(timeout=timeout * 2)
        if payment_method_offered(page, timeout, method):
            allure.attach(
                f"{label} was missing, and offered after one reload", name="payment method retry",
                attachment_type=allure.attachment_type.TEXT,
            )
            return
    _attach_payment_section(page)
    raise AssertionError(
        f"The rental form offers no {label}, also after reloading it once - gateway settings: {gateway}"
    )


def fill_business_representative(page: Page, timeout: float, guest: dict, rental_data: dict) -> None:
    """Renting as a business only: the reservation collects just Business
    Name/Phone/Email, so the rental form's "Business Representative
    Information" - Email, Mobile, First/Last Name (+ an address on the Legacy
    form) - comes up empty and required, and the form refuses to go on until
    it's filled (Legacy on 2026-09-14, Two-Step on 2026-09-15). Its labels
    repeat other blocks' (alternate contact, address), so each field is the
    first empty, visible one of its name. The representative is the renter -
    the guest's Mailinator email and fictional (714) 555-01xx mobile. No-op
    when the block isn't shown."""
    heading = page.get_by_role("heading", name="Business Representative Information")
    if heading.count() == 0 or not heading.first.is_visible():
        return

    def first_empty(role: str, name: str):
        fields = page.get_by_role(role, name=name, exact=True)
        for index in range(fields.count()):
            field = fields.nth(index)
            if field.is_visible() and not field.input_value():
                return field
        return None

    def fill(name: str, value: str, required: bool = True) -> None:
        field = first_empty("textbox", name)
        if field is None:
            if required:
                raise AssertionError(f"No empty '{name}' field for the business representative")
            return
        field.fill(value)

    with allure.step(f"Business representative: {guest['first_name']} {guest['last_name']}"):
        fill("Email *", guest["email"])
        mobile = first_empty("textbox", "Mobile *")
        if mobile is None:
            raise AssertionError("No empty 'Mobile *' field for the business representative")
        digits = re.sub(r"\D", "", guest["mobile"])
        # The same async phone check as the reservation form's Mobile field.
        try:
            with page.expect_response(
                lambda response: "/validate-phone/" in response.url
                and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                timeout=10000,
            ):
                mobile.fill(guest["mobile"])
        except PlaywrightTimeoutError:
            pass
        fill("First Name *", guest["first_name"])
        fill("Last Name *", guest["last_name"])
        # The address fields are the Legacy block's; filled where present.
        fill("Address1 *", rental_data["address1"], required=False)
        fill("Address2", rental_data["address2"], required=False)
        fill("ZIP/Postal code *", rental_data["zip"], required=False)
        state = first_empty("combobox", "State/Province *")
        if state is not None:
            select_state(state, rental_data["state"], rental_data["state_code"])
        fill("City *", rental_data["city"], required=False)


def tick_checkbox(page: Page, timeout: float, checkbox: Locator, label: Locator) -> None:
    """Ticks a custom-styled checkbox: a label click, then a click event
    dispatched on the box, then one on its label - each after re-checking
    the box (so a late earlier click is never undone) and followed by a
    short check. No forced check: that clicks at the box's position, so
    whatever covers the box gets the click - on the phone RAB reservation
    form a sticky .storage-info bar covers "I am renting as a business", and
    a run with a forced check ended on the storefront's home page
    (2026-09-15)."""
    for tick in (
        lambda: label.click(timeout=5000),
        lambda: checkbox.dispatch_event("click"),
        lambda: label.dispatch_event("click"),
    ):
        if checkbox.is_checked():
            return
        try:
            tick()
            expect(checkbox).to_be_checked(timeout=5000)
            return
        except Exception:
            continue
    expect(checkbox).to_be_checked(timeout=timeout)


def tick_agreement(page: Page, timeout: float) -> None:
    """The rental agreement box (#clickwrap), ticked through its label. One
    label click left it unticked on a 2Step run (2026-09-15; it worked in the
    other runs) - likely while the agreement was still being generated - so
    tick_checkbox's more direct clicks follow."""
    tick_checkbox(page, timeout, page.locator("#clickwrap"), page.locator('label[for="clickwrap"]').first)


def select_payment_method(page: Page, timeout: float, method: str) -> None:
    """method is "card" or "ach". A form with no method radios at all offers
    the card only (uat_storoutlet's Two-Step form, 2026-09-13). The section
    is waited for, not counted once: a 2026-09-14 run found no method radios
    right after filling the form, while a live replay of the same steps on
    Bellflower showed Credit Card and ACH at every step."""
    method_radios = page.locator('input[type="radio"][value="card"], input[type="radio"][value="ach"]')
    card_fields = page.locator('iframe[name="card-number"], #creditCardNumber')
    try:
        expect(method_radios.or_(card_fields).first).to_be_attached(timeout=timeout)
    except AssertionError:
        _attach_payment_section(page)
        raise AssertionError(
            "The rental form shows no payment method - no Credit Card / ACH choice and no card fields"
        )
    radio = page.locator(f'input[type="radio"][value="{method}"]')
    if radio.count() == 0:
        if method != "card":
            _attach_payment_section(page)
            raise AssertionError("The rental form offers no ACH / E-Check payment")
        return
    if not radio.first.is_checked():
        page.locator(f'label:has(input[type="radio"][value="{method}"])').first.click()
    expect(radio.first).to_be_checked(timeout=timeout)


def enter_card(
    page: Page, timeout: float, card_number: str, card_expiry: str, card_cvc: str, name_on_card: str
) -> None:
    hosted_number = page.locator('iframe[name="card-number"]')
    plain_number = page.locator("#creditCardNumber")
    expect(hosted_number.or_(plain_number).first).to_be_visible(timeout=timeout)
    if hosted_number.count() > 0:
        card_fields = [
            page.frame_locator(f'iframe[name="{frame_name}"]').locator("input").first
            for frame_name in ("card-number", "card-expiration", "card-cvv")
        ]
    else:
        card_fields = [plain_number, page.locator("#expiry"), page.locator("#cvv")]
    # The hosted expiry reformats typed digits ("1234" becomes "12 / 2034").
    for card_field, value in zip(card_fields, (card_number, re.sub(r"\D", "", card_expiry), card_cvc)):
        card_field.click()
        card_field.press_sequentially(value, delay=40)
    page.locator("#name").fill(name_on_card)


def enter_ach(
    page: Page, timeout: float, name_on_account: str, routing_number: str, account_number: str
) -> None:
    values = (name_on_account, routing_number, account_number, account_number)
    for field_id, value in zip(ACH_FIELD_IDS, values):
        field = page.locator(f'input[id^="{field_id}"]').first
        expect(field).to_be_visible(timeout=timeout)
        field.fill(value)


def fill_billing_address(page: Page, timeout: float, address: dict) -> None:
    """Only when the form shows a billing address (it did for ACH)."""
    free_text = page.locator('input[placeholder="Billing Address"]').filter(visible=True)
    if free_text.count() == 0:
        return
    with allure.step("Billing address"):
        free_text.first.fill(
            f"{address['address1']}, {address['address2']}, "
            f"{address['city']}, {address['state_code']} {address['zip']}"
        )
        address1 = page.locator("#billingAddress1")
        expect(address1).to_be_visible(timeout=timeout)
        address1.fill(address["address1"])
        page.locator("#billingAddress2").fill(address["address2"])
        page.locator("#billingZip").fill(address["zip"])
        page.locator("#billingCity").fill(address["city"])
        select_state(page.locator("#billingState"), address["state"], address["state_code"])
