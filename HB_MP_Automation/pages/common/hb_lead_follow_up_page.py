import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import first_visible, log_method_exceptions
from common_utils.waits import waits


class HBLeadFollowUpPage:
    """HB's Lead Follow-Up panel - the same panel whether opened from a
    lead's own "Manage Reservation" (HBLeadManagementPage.
    open_reservation_follow_up) or a Task Center lead task's "First Follow
    Up" (HBTaskCenterPage.open_lead_follow_up). Read-only: nothing is
    logged or saved here."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout
        self.move_in_cost = page.get_by_text(re.compile(r"Move-In Cost:")).first

    @log_method_exceptions
    def _parse_lease_details(self) -> dict:
        """Confirmed live (2026-09-13): the open Follow-Up's Lease Details
        are plain text, one value per line - "Base Rent*\\n 53\\nSecurity
        Deposit\\n 20\\n...\\nPromotion\\n<name>\\narrow_drop_down" (or
        "Promotion\\n+ Add Promotion" with none) "...Move-In Cost:\\n$50.03
        \\nMonthly Rent:\\n$53.00"."""
        body = self.page.locator("body").inner_text()
        start = body.find("Lease Details")
        end = body.find("Monthly Rent:", start)
        text = body[start:end + 40] if start >= 0 and end >= 0 else ""

        def amount(pattern: str) -> float | None:
            match = re.search(pattern, text)
            return float(match.group(1).replace(",", "")) if match else None

        promotion = re.search(r"Promotion\s*\n\s*([^\n]+?)\s*\n\s*arrow_drop_down", text)
        return {
            "base_rent": amount(r"Base Rent\*?\s*\$?([\d,]+(?:\.\d+)?)"),
            "security_deposit": amount(r"Security Deposit\s*\$?([\d,]+(?:\.\d+)?)"),
            "promotion": promotion.group(1).strip() if promotion else None,
            "move_in_cost": amount(r"Move-In Cost:\s*\$([\d,]+(?:\.\d+)?)"),
            "monthly_rent": amount(r"Monthly Rent:\s*\$([\d,]+(?:\.\d+)?)"),
        }

    @log_method_exceptions
    def read_lease_details(self) -> dict:
        """Waits for the figures to settle before returning them: confirmed
        live (2026-09-13), the panel first shows "Move-In Cost:" with
        interim values and no Base Rent/Security Deposit (a run read $31.80
        that settled to $50.03 a few seconds later) - so it's re-read until
        Base Rent and Monthly Rent are both present and nothing has changed
        for 3 s."""
        with allure.step("Read Lead Follow-Up lease details"):
            readings: list[dict] = []
            for _ in range(int(self.timeout / 500)):
                details = self._parse_lease_details()
                readings.append(details)
                if (
                    details["base_rent"] is not None
                    and details["monthly_rent"] is not None
                    and len(readings) >= 6
                    and all(reading == details for reading in readings[-6:])
                ):
                    break
                self.page.wait_for_timeout(waits().poll_interval)
            else:
                raise AssertionError(
                    f"Lead Follow-Up lease details never settled: {readings[-1]}"
                )
            allure.attach(
                repr(details), name="HB lease details", attachment_type=allure.attachment_type.TEXT
            )
            return details

    @log_method_exceptions
    def close(self) -> None:
        """Closes Follow-Up (and whatever opened it) via their close icons -
        no interaction is logged and nothing is saved."""
        with allure.step("Close Lead Follow-Up without saving"):
            for _ in range(2):
                if not self.move_in_cost.is_visible():
                    break
                first_visible(self.page.locator('[name="QA-v-card-HbIcon-mdi-close"]')).click()
                try:
                    expect(self.move_in_cost).to_be_hidden(timeout=waits().short)
                except AssertionError:
                    continue
            expect(self.move_in_cost).to_be_hidden(timeout=self.timeout)
