import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# User's rental scenarios (2026-09-15): "Legacy Flow-Clickwrap Signing" as an
# individual - the RAB cases are in test_non_tenant_legacy_clickwrap_rab.py -
# on the non-Tenant-Payments gateway: cards go through Authorize.Net, set on
# both rental properties from environments.ini once per session (this folder's
# conftest.py gateway_profile = non_tenant_payments,
# tests/mp/rentals/conftest.py payment_gateways). Card only: that profile has
# no ACH gateway. One explicit test per scenario, its markers on the test.
# Each is one real rental, checked on the storefront, in the guest's inbox and
# in HB - found by its space number - then moved out
# (common_utils/mp_rental_cases.py); Clickwrap signing = Clickwrap on and
# Super Lease off, set once for the module (tests/mp/rentals/conftest.py).


@allure.feature("MP Rentals")
@allure.story("Legacy Flow: Clickwrap Signing - Individual (Non-Tenant Payments Gateway)")
@pytest.mark.mp_rental
@pytest.mark.non_tenant_payments_gateway
@pytest.mark.legacy_clickwrap
@pytest.mark.usefixtures("legacy_clickwrap_signing")
class TestNonTenantClickwrapIndividual:
    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card-DesktopView-Individual")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_clickwrap_signing_credit_card_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card with Autopay-DesktopView-Individual")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_clickwrap_signing_credit_card_with_autopay_desktop_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=False)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card-MobileView-Individual")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_clickwrap_signing_credit_card_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="mobile", rab=False)
        )

    @allure.title("Legacy Flow-Clickwrap Signing-Credit Card with Autopay-MobileView-Individual")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.individual
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    def test_legacy_flow_clickwrap_signing_credit_card_with_autopay_mobile_view_individual(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=False)
        )
