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
from common_utils.waits import waits

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


def set_autopay(page: Page, timeout: float, enroll: bool, when: str = "payment section") -> None:
    """Sets "Autopay Enrollment" (#auto-debit) to the case's autopay setting
    (RentalCase.autopay, passed on as enroll_autopay). The storefront can
    show it already ticked (both 2Step walks on stage, 2026-09-15): an
    autopay case leaves a ticked box alone, a non-autopay case unticks it,
    and an unticked box is ticked only for an autopay case. What was found
    and done goes in the report, labelled with `when`."""
    autopay = page.locator("#auto-debit")
    if autopay.count() == 0:
        if enroll:
            raise AssertionError("The rental form has no Autopay Enrollment checkbox")
        return
    was_checked = autopay.is_checked()
    wanted = "ticked" if enroll else "unticked"
    if was_checked == enroll:
        action = f"already {wanted} - left as is"
    else:
        tick_checkbox(page, timeout, autopay, page.locator('label[for="auto-debit"]').first, checked=enroll)
        action = f"was {'ticked' if was_checked else 'unticked'} - now {wanted}"
    allure.attach(
        f"{'Autopay' if enroll else 'Non-autopay'} case: Autopay Enrollment {action}",
        name=f"autopay ({when})",
        attachment_type=allure.attachment_type.TEXT,
    )


def _attach_payment_section(page: Page) -> None:
    text = page.locator("body").inner_text()
    start = text.find("Payment Method")
    allure.attach(
        text[start:start + 800] if start >= 0 else text[:800],
        name="payment section", attachment_type=allure.attachment_type.TEXT,
    )
    # Viewport only — full-page PNG bloated Allure on long rental forms.
    allure.attach(
        page.screenshot(full_page=False),
        name="rental form",
        attachment_type=allure.attachment_type.PNG,
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
        expect(radio.first).to_be_attached(timeout=waits().long)
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
    the guest's Gmail address and fictional (714) 555-01xx mobile. No-op
    when the block isn't shown. Fields already filled are left alone.
    """
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

    def any_visible_filled(role: str, name: str) -> bool:
        fields = page.get_by_role(role, name=name, exact=True)
        for index in range(fields.count()):
            field = fields.nth(index)
            if field.is_visible() and (field.input_value() or "").strip():
                return True
        return False

    def fill(name: str, value: str, required: bool = True) -> None:
        field = first_empty("textbox", name)
        if field is None:
            if required and not any_visible_filled("textbox", name):
                raise AssertionError(
                    f"No empty '{name}' field for the business representative"
                )
            return
        field.fill(value)

    with allure.step(f"Business representative: {guest['first_name']} {guest['last_name']}"):
        fill("Email *", guest["email"])
        mobile = first_empty("textbox", "Mobile *")
        if mobile is None:
            if not any_visible_filled("textbox", "Mobile *"):
                raise AssertionError(
                    "No empty 'Mobile *' field for the business representative"
                )
        else:
            digits = re.sub(r"\D", "", guest["mobile"])
            # The same async phone check as the reservation form's Mobile field.
            try:
                with page.expect_response(
                    lambda response: "/validate-phone/" in response.url
                    and digits in re.sub(r"%[0-9A-Fa-f]{2}|\D", "", response.url),
                    timeout=waits().medium,
                ):
                    mobile.fill(guest["mobile"])
            except PlaywrightTimeoutError:
                mobile.fill(guest["mobile"])
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


def tick_checkbox(
    page: Page, timeout: float, checkbox: Locator, label: Locator, checked: bool = True
) -> None:
    """Ticks a custom-styled checkbox (or, with checked=False, unticks it): a
    label click, then a click event dispatched on the box, then one on its
    label - each after re-checking the box (so a late earlier click is never
    undone) and followed by a short check. No forced check: that clicks at
    the box's position, so whatever covers the box gets the click - on the
    phone RAB reservation form a sticky .storage-info bar covers "I am
    renting as a business", and a run with a forced check ended on the
    storefront's home page (2026-09-15)."""
    for click in (
        lambda: label.click(timeout=waits().short),
        lambda: checkbox.dispatch_event("click"),
        lambda: label.dispatch_event("click"),
    ):
        if checkbox.is_checked() == checked:
            return
        try:
            click()
            expect(checkbox).to_be_checked(checked=checked, timeout=waits().short)
            return
        except Exception:
            continue
    expect(checkbox).to_be_checked(checked=checked, timeout=timeout)


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


def card_pan_digits(card_number: str) -> str:
    return re.sub(r"\D", "", card_number or "")


def card_brand(card_number: str) -> str:
    """Rough brand from PAN prefix — drives CVV length (Amex=4, else 3)."""
    digits = card_pan_digits(card_number)
    if digits.startswith(("34", "37")):
        return "amex"
    if digits.startswith("4"):
        return "visa"
    if digits.startswith(("51", "52", "53", "54", "55")) or (
        len(digits) >= 4 and 2221 <= int(digits[:4]) <= 2720
    ):
        return "mastercard"
    if digits.startswith(("6011", "65")):
        return "discover"
    if digits.startswith(("62", "81")):
        return "unionpay"
    return "unknown"


def expected_cvv_length(card_number: str) -> int:
    """Hosted CVV length follows the card: Amex 4, others 3 (MRECOM hosted fields)."""
    return 4 if card_brand(card_number) == "amex" else 3


def normalize_expiry_digits(card_expiry: str) -> str:
    """Hosted expiry accepts MMYY (2-digit year) or MMYYYY (full year).

    Previously only the last two year digits were typed; the field now also
    accepts a four-digit year. Returns digits only for press_sequentially.
    """
    digits = re.sub(r"\D", "", card_expiry or "")
    if len(digits) in (4, 6):
        return digits
    raise ValueError(
        f"card_expiry must be MM/YY, MM/YYYY, MMYY, or MMYYYY; got {card_expiry!r}"
    )


def hosted_card_input(page: Page, frame_name: str):
    """Input inside a Global Payments hosted iframe (card-number / expiration / cvv)."""
    return page.frame_locator(f'iframe[name="{frame_name}"]').locator("input").first


def card_ui_input(page: Page, field: str):
    """Hosted iframe input when present, else native Mariposa/Authorize.Net field.

    ``field`` is card-number | card-expiration | card-cvv.
    """
    hosted = page.locator(f'iframe[name="{field}"]')
    if hosted.count() > 0 and hosted.first.is_visible():
        return hosted_card_input(page, field)
    plain = {
        "card-number": page.locator("#creditCardNumber"),
        "card-expiration": page.locator("#expiry"),
        "card-cvv": page.locator("#cvv"),
    }[field]
    return plain.first


def enter_card(
    page: Page, timeout: float, card_number: str, card_expiry: str, card_cvc: str, name_on_card: str
) -> None:
    """Fill card fields. Hosted iframes accept PAN up to 19 digits, expiry as
    MMYY or MMYYYY, and CVV of 3 or 4 digits based on the card brand."""
    pan = card_pan_digits(card_number)
    if not (13 <= len(pan) <= 19):
        raise ValueError(
            f"card_number must be 13–19 digits for hosted payments; got {len(pan)}"
        )
    expiry_digits = normalize_expiry_digits(card_expiry)
    cvv = re.sub(r"\D", "", card_cvc or "")
    want_cvv = expected_cvv_length(pan)
    if len(cvv) != want_cvv:
        raise ValueError(
            f"CVV for {card_brand(pan)} must be {want_cvv} digits; got {len(cvv)} ({cvv!r})"
        )

    hosted_number = page.locator('iframe[name="card-number"]')
    plain_number = page.locator("#creditCardNumber")
    expect(hosted_number.or_(plain_number).first).to_be_visible(timeout=timeout)
    if hosted_number.count() > 0:
        card_fields = [
            hosted_card_input(page, frame_name)
            for frame_name in ("card-number", "card-expiration", "card-cvv")
        ]
    else:
        card_fields = [plain_number, page.locator("#expiry"), page.locator("#cvv")]
    # Expiry: MMYY ("1234" → "12 / 2034") or MMYYYY full year ("122034").
    for card_field, value in zip(card_fields, (pan, expiry_digits, cvv)):
        card_field.click()
        card_field.fill("")
        card_field.press_sequentially(value, delay=40)
    page.locator("#name").fill(name_on_card)


def assert_card_fields_ready(page: Page, timeout: float) -> None:
    """Credit Card section shows card number / expiry / CVV (hosted or plain)."""
    with allure.step("Assert card entry fields are on the rental form"):
        select_payment_method(page, timeout, "card")
        for field in ("card-number", "card-expiration", "card-cvv"):
            expect(card_ui_input(page, field)).to_be_visible(timeout=timeout)


# Back-compat name used by older callers.
assert_card_fields_are_hosted = assert_card_fields_ready


def assert_card_ui_field_accepts_digits(
    page: Page, timeout: float, field: str, digits: str
) -> None:
    """Type digits into the card UI field and assert they are kept (UI only)."""
    control = card_ui_input(page, field)
    expect(control).to_be_visible(timeout=timeout)
    control.click()
    control.fill("")
    control.press_sequentially(digits, delay=30)
    value = control.input_value()
    got = re.sub(r"\D", "", value or "")
    assert len(got) >= len(digits), (
        f"Card UI {field} truncated input: typed {len(digits)} digits "
        f"({digits!r}), field shows {value!r} ({len(got)} digits)"
    )
    allure.attach(
        f"typed={digits!r} value={value!r} digits={got!r}",
        name=f"card-ui-{field}",
        attachment_type=allure.attachment_type.TEXT,
    )


def enter_ach(
    page: Page, timeout: float, name_on_account: str, routing_number: str, account_number: str
) -> None:
    values = (name_on_account, routing_number, account_number, account_number)
    for field_id, value in zip(ACH_FIELD_IDS, values):
        field = page.locator(f'input[id^="{field_id}"]').first
        expect(field).to_be_visible(timeout=timeout)
        field.fill(value)


BILLING_ADDRESS_KEYS = ("address1", "city", "state", "state_code", "zip")


def missing_billing_values(address: dict) -> list[str]:
    """The billing address values the test data lacks (address2 may be empty)."""
    return [key for key in BILLING_ADDRESS_KEYS if not str(address.get(key) or "").strip()]


def fill_billing_address(page: Page, timeout: float, address: dict) -> None:
    """Fills the billing address when the form shows one (it did for ACH).
    When address["billing_address_required"] is set - a gateway marked
    `billing_address = required` in environments.ini, e.g. Authorize.Net for
    cards (user, 2026-09-15) - a missing value in the test data, or a form
    with no "Billing Address" box, raises instead of being skipped."""
    required = bool(address.get("billing_address_required"))
    if required and (missing := missing_billing_values(address)):
        raise AssertionError(
            f"This gateway needs a billing address, but the rental test data lacks {missing} "
            "(config/test_data/mp_rental.json)"
        )
    free_text = page.locator('input[placeholder="Billing Address"]').filter(visible=True)
    # The box can render a moment after the payment method is picked, so a
    # required one gets up to 10 s.
    for _ in range(20 if required else 1):
        if free_text.count() > 0:
            break
        if required:
            page.wait_for_timeout(waits().poll_interval)
    if free_text.count() == 0:
        if required:
            raise AssertionError(
                "This gateway needs a billing address (environments.ini: billing_address = required), "
                "but the rental form shows no Billing Address box"
            )
        return
    with allure.step("Billing address"):
        free_text.first.fill(
            f"{address['address1']}, {address.get('address2', '')}, "
            f"{address['city']}, {address['state_code']} {address['zip']}"
        )
        address1 = page.locator("#billingAddress1")
        expect(address1).to_be_visible(timeout=timeout)
        address1.fill(address["address1"])
        page.locator("#billingAddress2").fill(address.get("address2", ""))
        page.locator("#billingZip").fill(address["zip"])
        page.locator("#billingCity").fill(address["city"])
        select_state(page.locator("#billingState"), address["state"], address["state_code"])
