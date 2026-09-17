import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# The RAB (renting as a business) half of the user's "Legacy Flow-Clickwrap
# Signing" scenarios (2026-09-14: RAB on every case) - see
# test_legacy_clickwrap_individual.py. HB lists a business renter as "<name>
# Business".


@allure.feature("MP Rentals")
@allure.story("Legacy Flow: Clickwrap Signing - RAB")
@pytest.mark.mp_rental
@pytest.mark.tenant_payments_gateway
@pytest.mark.legacy_clickwrap
@pytest.mark.usefixtures("legacy_clickwrap_signing")
class TestClickwrapRab:
    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_credit_card_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-ACH-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_ach_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card with Autopay-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_credit_card_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-ACH with Autopay-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_ach_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_credit_card_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="mobile", rab=True)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-ACH-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_ach_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="mobile", rab=True)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card with Autopay-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_credit_card_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=True)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-ACH with Autopay-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    def test_legacy_flow_clickwrap_signing_ach_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="mobile", rab=True)
        )
