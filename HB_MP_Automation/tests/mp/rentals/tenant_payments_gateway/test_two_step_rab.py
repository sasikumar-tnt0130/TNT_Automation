import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# The RAB (renting as a business) half of the user's "2Step Flow-Superlease
# Signing" scenarios (2026-09-14: RAB on every case) - see
# test_two_step_individual.py. HB lists a business renter as "<name>
# Business". Module fixture ``two_step_superlease_checked`` enables
# Two-Step + Super Lease + Clickwrap and flushes website cache.


@allure.feature("MP Rentals")
@allure.story("2Step Flow: Super Lease Signing - RAB")
@pytest.mark.mp_rental
@pytest.mark.tenant_payments_gateway
@pytest.mark.two_step_superlease
@pytest.mark.usefixtures("two_step_superlease_checked")
class TestTwoStepSuperleaseRab:
    @allure.title("2Step Flow-Superlease Signing-Credit Card-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_credit_card_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=True), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_ach_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="desktop", rab=True), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-Credit Card with Autopay-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_credit_card_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=True), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH with Autopay-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_ach_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="desktop", rab=True), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-Credit Card-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_credit_card_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="mobile", rab=True), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_ach_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="mobile", rab=True), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-Credit Card with Autopay-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_credit_card_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=True), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH with Autopay-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    @pytest.mark.testrail("C20849")
    def test_2step_flow_superlease_signing_ach_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="mobile", rab=True), two_step=True
        )
