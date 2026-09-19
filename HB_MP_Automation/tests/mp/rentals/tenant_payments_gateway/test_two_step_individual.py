import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# User's rental scenarios (2026-09-14): "2Step Flow-Superlease Signing" as an
# individual (the RAB cases are in test_two_step_rab.py), on the Tenant
# Payments gateway. One explicit test per scenario, its markers on the test
# (user, 2026-09-15). Each is one real rental, checked on the storefront, in
# the guest's inbox and in HB - found by its space number - then moved out
# (common_utils/mp_rental_cases.py). It runs on the environment's Two-Step
# property (environments.ini `two_step_property`). Module fixture
# ``two_step_superlease_checked`` enables Two-Step + Super Lease + Clickwrap
# and flushes website cache. ACH cases need ACH on that property's gateway.


@allure.feature("MP Rentals")
@allure.story("2Step Flow: Super Lease Signing - Individual")
@pytest.mark.mp_rental
@pytest.mark.tenant_payments_gateway
@pytest.mark.two_step_superlease
@pytest.mark.usefixtures("two_step_superlease_checked")
class TestTwoStepSuperleaseIndividual:
    @allure.title("2Step Flow-Superlease Signing-Credit Card-DesktopView-Individual")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_credit_card_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH-DesktopView-Individual")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_ach_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="desktop", rab=False), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-Credit Card with Autopay-DesktopView-Individual")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_credit_card_with_autopay_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=False), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH with Autopay-DesktopView-Individual")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_ach_with_autopay_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="desktop", rab=False), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-Credit Card-MobileView-Individual")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_credit_card_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="mobile", rab=False), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH-MobileView-Individual")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_ach_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="mobile", rab=False), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-Credit Card with Autopay-MobileView-Individual")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_credit_card_with_autopay_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=False), two_step=True
        )

    @allure.title("2Step Flow-Superlease Signing-ACH with Autopay-MobileView-Individual")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C683630")
    def test_2step_flow_superlease_signing_ach_with_autopay_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="mobile", rab=False), two_step=True
        )
