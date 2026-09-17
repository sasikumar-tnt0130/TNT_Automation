import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# User's rental scenarios (2026-09-14): "Legacy Flow-Traditional Signing" as
# an individual (the RAB cases are in test_legacy_traditional_signing_rab.py),
# on the Tenant Payments gateway. One explicit test per scenario, its markers
# on the test (user, 2026-09-15). Each is one real rental, checked on the
# storefront, in the guest's inbox and in HB - found by its space number -
# then moved out (common_utils/mp_rental_cases.py). Traditional signing =
# Clickwrap off and Super Lease off (user, 2026-09-14), set once for the
# module (tests/mp/rentals/conftest.py).


@allure.feature("MP Rentals")
@allure.story("Legacy Flow: Traditional Signing - Individual")
@pytest.mark.mp_rental
@pytest.mark.tenant_payments_gateway
@pytest.mark.legacy_traditional
@pytest.mark.usefixtures("legacy_traditional_signing")
class TestTraditionalSigningIndividual:
    @allure.title("Legacy Flow-Traditional Signing-Credit Card-DesktopView-Individual")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_credit_card_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH-DesktopView-Individual")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_ach_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="desktop", rab=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-Credit Card with Autopay-DesktopView-Individual")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_credit_card_with_autopay_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH with Autopay-DesktopView-Individual")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_ach_with_autopay_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="desktop", rab=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-Credit Card-MobileView-Individual")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_credit_card_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="mobile", rab=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH-MobileView-Individual")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_ach_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="mobile", rab=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-Credit Card with Autopay-MobileView-Individual")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_credit_card_with_autopay_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH with Autopay-MobileView-Individual")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_traditional_signing_ach_with_autopay_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="mobile", rab=False)
        )
