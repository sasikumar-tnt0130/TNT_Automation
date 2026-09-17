import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# The RAB (renting as a business) half of the user's "Legacy Flow-Superlease
# Signing" scenarios (2026-09-14: RAB on every case) - see
# test_legacy_superlease_individual.py. HB lists a business renter as "<name>
# Business".


@allure.feature("MP Rentals")
@allure.story("Legacy Flow: Super Lease Signing - RAB")
@pytest.mark.mp_rental
@pytest.mark.tenant_payments_gateway
@pytest.mark.legacy_superlease
@pytest.mark.usefixtures("legacy_superlease_signing")
class TestSuperleaseRab:
    @allure.title("Legacy Flow-Superlease Signing-Credit Card-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_superlease_signing_credit_card_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Superlease Signing-ACH-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_superlease_signing_ach_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Superlease Signing-Credit Card with Autopay-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    @pytest.mark.testrail("C64998")
    def test_legacy_flow_superlease_signing_credit_card_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Superlease Signing-ACH with Autopay-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_superlease_signing_ach_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="desktop", rab=True)
        )

    @allure.title("Legacy Flow-Superlease Signing-Credit Card-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_superlease_signing_credit_card_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="mobile", rab=True)
        )

    @allure.title("Legacy Flow-Superlease Signing-ACH-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_superlease_signing_ach_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="mobile", rab=True)
        )

    @allure.title("Legacy Flow-Superlease Signing-Credit Card with Autopay-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    @pytest.mark.testrail("C64998")
    def test_legacy_flow_superlease_signing_credit_card_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=True)
        )

    @allure.title("Legacy Flow-Superlease Signing-ACH with Autopay-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_superlease_signing_ach_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="mobile", rab=True)
        )
