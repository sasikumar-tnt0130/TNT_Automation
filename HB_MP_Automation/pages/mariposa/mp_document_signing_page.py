import allure
from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from common_utils.wrapper_methods import log_method_exceptions


class MPDocumentSigningPage:
    """The storefront rental's "Sign Documents" step (.../rent/<space
    type>/documents/). Confirmed live 2026-09-14 (uat_storoutlet/Bellflower,
    Traditional signing): the lease's documents (Lease Agreement, Autopay
    Enrollment Document, Insurance / Protection Enrollment Document and the
    property's other addenda) beside the same document-signing widget HB's
    "Sign on This Device" opens - "Start Signing", click-to-sign
    img.replaced-text fields (an adopt-signature box on some) and "Finalize
    Document" per document. Signed with the same loop as
    HBQuickLaunchPage._sign_documents_in_widget. After the last document the
    storefront creates the rental itself (POST .../rentals) and leaves this
    page - 7 documents and 11 fields took about a minute."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    def _frame(self):
        return self.page.frame_locator('iframe[src*="document-signing"]')

    def _on_documents_page(self) -> bool:
        return "/documents/" in self.page.url

    @log_method_exceptions
    def _click_within(self, locator: Locator, timeout: float = 5000) -> bool:
        # Same as HBQuickLaunchPage._click_within: a document just finalized
        # can leave the next one non-interactable for a while.
        try:
            locator.click(timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False

    @log_method_exceptions
    def _sign_next_field(self, initials: str) -> bool:
        # See HBQuickLaunchPage._sign_next_field: a signed field only gains
        # "signed", and only a field clickable right now is taken.
        frame = self._frame()
        unsigned_field = frame.locator("img.replaced-text:not(.signed)")
        if unsigned_field.count() == 0:
            return False
        try:
            unsigned_field.first.click(trial=True, timeout=2000)
        except PlaywrightTimeoutError:
            return False
        field_id = unsigned_field.first.get_attribute("data-id")
        signed_field = frame.locator(f'img.replaced-text.signed[data-id="{field_id}"]')
        if not self._click_within(frame.locator(f'img.replaced-text[data-id="{field_id}"]')):
            return False

        signature_input = frame.locator("input.signature-input")
        accept_button = frame.get_by_role("button", name="Accept and sign", exact=True)
        for _ in range(40):
            if signed_field.count() > 0:
                return True
            if signature_input.count() > 0 and signature_input.first.is_visible():
                if not signature_input.first.input_value():
                    signature_input.first.fill(initials)
                for attempt in range(5):
                    self._click_within(accept_button)
                    try:
                        expect(signature_input).to_be_hidden(timeout=4000)
                        break
                    except AssertionError:
                        if attempt == 4:
                            raise
                expect(signed_field).to_have_count(1, timeout=self.timeout)
                return True
            self.page.wait_for_timeout(250)
        return False

    @log_method_exceptions
    def sign_all(self, initials: str = "AT") -> int:
        """Signs every document; returns how many fields were signed."""
        with allure.step("Sign every document"):
            frame = self._frame()
            expect(
                frame.get_by_role("button", name="Start Signing", exact=True)
                .or_(frame.locator("img.replaced-text"))
                .first
            ).to_be_visible(timeout=self.timeout)
            # Only tried when no field is signable right now, in this order -
            # "Start Signing" last, as it stays on screen until the document's
            # first field is signed.
            navigation_buttons = [
                frame.get_by_role("button", name="Next", exact=True),
                frame.get_by_role("button", name="Finalize Document"),
                frame.get_by_role("button", name="Continue", exact=True),
                frame.get_by_role("button", name="Start Signing", exact=True),
            ]
            signed = 0
            idle_checks = 0
            for _ in range(300):
                if not self._on_documents_page():
                    break
                if self._sign_next_field(initials):
                    signed += 1
                    idle_checks = 0
                    continue
                if any(
                    button.count() > 0 and button.first.is_visible() and self._click_within(button.first)
                    for button in navigation_buttons
                ):
                    idle_checks = 0
                    self.page.wait_for_timeout(1000)
                    continue
                # Nothing actionable: the next document is still loading, or
                # the storefront is creating the rental after the last one.
                idle_checks += 1
                if idle_checks >= 60:
                    break
                self.page.wait_for_timeout(1000)
            if self._on_documents_page():
                raise AssertionError(
                    f"Still on Sign Documents after signing {signed} field(s) - "
                    "the signing widget stopped with documents left"
                )
            allure.attach(
                f"{signed} signature field(s) signed", name="documents signed",
                attachment_type=allure.attachment_type.TEXT,
            )
            return signed
