import allure
from playwright.sync_api import Locator, Page, expect


def fill_ach_details(
    page: Page,
    scope: Page | Locator,
    timeout: float,
    first_name: str,
    last_name: str,
    account_type: str,
    routing_number: str,
    account_number: str,
) -> None:
    """The ACH/E-Check account form HB shows both in Take a Payment and in a
    tenant's Add New Payment Method dialog - the same fields in both,
    confirmed live (2026-09-13, uat_storoutlet/Bellflower): First/Last
    Name, an "Account Type*" select (Checking / Savings), "Enter Routing
    Number*", "Enter Account Number*", and a billing address that the
    "Default Address" box fills from the tenant's own record.

    Also confirmed live: each field's id and name sit on a wrapper div as
    well as the input (so "#account-number" matches two elements - inputs
    are targeted by name); the Account Type input is readonly and only
    opens from its enclosing v-select slot; and HB rejects some test
    routing numbers outright (110000000 stays red; 011401533 is accepted).

    Timing matters (reproduced 2026-09-13): pressing Tab straight after a
    fill makes HB validate before it has taken the typed value - every
    field turns red and HB warns "There are errors in your form ... field
    is required" although the inputs show the values, and they stay red.
    Waiting ~0.7 s before and after the Tab leaves them valid, so each field
    gets that pause, and any field still flagged gets one more slow pass."""
    with allure.step("Enter ACH account details"):
        account_type_input = scope.get_by_role("textbox", name="Account Type*", exact=True)
        # A tenant who already has a saved bank account gets "Account On
        # File" / "New Bank Account" here instead of the form (seen live
        # 2026-09-13); choosing "New Bank Account" hasn't been walked.
        if (
            scope.get_by_text("Account On File", exact=True).count() > 0
            and not account_type_input.is_visible()
        ):
            raise AssertionError(
                "This tenant already has a saved bank account ('Account On File'); "
                "entering a new one via 'New Bank Account' isn't supported yet"
            )
        account_type_slot = account_type_input.locator(
            "xpath=ancestor::*[contains(@class,'v-select__slot')][1]"
        )
        expect(account_type_slot).to_be_visible(timeout=timeout)
        account_type_slot.click()
        option = page.get_by_role("option", name=account_type, exact=True)
        expect(option).to_be_visible(timeout=timeout)
        option.click()

        default_address = scope.get_by_role("checkbox", name="Default Address", exact=True)
        if not default_address.is_checked():
            scope.locator('label:text-is("Default Address")').click()
        expect(default_address).to_be_checked(timeout=timeout)
        expect(scope.locator('input[name="ach-billing-address"]')).not_to_have_value(
            "", timeout=timeout
        )

        fields = {
            "account-first-name": first_name,
            "account-last-name": last_name,
            "account-routing-number": routing_number,
            "account-number": account_number,
        }

        def enter(field_name: str) -> None:
            field = scope.locator(f'input[name="{field_name}"]')
            expect(field).to_be_visible(timeout=timeout)
            field.fill(fields[field_name])
            page.wait_for_timeout(700)
            page.keyboard.press("Tab")
            page.wait_for_timeout(700)

        def flagged_fields() -> list[str]:
            return scope.locator(".v-input.error--text input").evaluate_all(
                "inputs => inputs.map(i => i.name || i.id)"
            )

        for field_name in fields:
            enter(field_name)
        for field_name in [name for name in flagged_fields() if name in fields]:
            enter(field_name)

        still_flagged = flagged_fields()
        if still_flagged:
            raise AssertionError(
                f"HB still flags these ACH fields as invalid: {still_flagged} - check the "
                f"[payment] ach_* values in environments.ini"
            )
