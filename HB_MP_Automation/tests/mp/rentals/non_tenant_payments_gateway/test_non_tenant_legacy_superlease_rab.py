import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# User's rental scenarios (2026-09-15): "Legacy Flow-Superlease Signing" as a
# business (RAB) - the individual cases are in
# test_non_tenant_legacy_superlease_individual.py - on the non-Tenant-Payments
# gateway: cards go through Authorize.Net, set on both rental properties from
# environments.ini once per session (this folder's conftest.py gateway_profile
# = non_tenant_payments, tests/mp/rentals/conftest.py payment_gateways). Card
# only: that profile has no ACH gateway. One explicit test per scenario, its
# markers on the test. Each is one real rental, checked on the storefront, in
# the guest's inbox and in HB - found by its space number - then moved out
# (common_utils/mp_rental_cases.py); Super Lease signing = Clickwrap on and
# Super Lease on, set once for the module (tests/mp/rentals/conftest.py).


@allure.feature("MP Rentals")
@allure.story("Legacy Flow: Super Lease Signing - RAB (Non-Tenant Payments Gateway)")
@pytest.mark.mp_rental
@pytest.mark.non_tenant_payments_gateway
@pytest.mark.legacy_superlease
@pytest.mark.usefixtures("legacy_superlease_signing")
class TestNonTenantSuperleaseRab:
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

    @allure.title("Legacy Flow-Superlease Signing-Credit Card with Autopay-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    @pytest.mark.testrail("C65004")
    def test_legacy_flow_superlease_signing_credit_card_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=True)
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

    @allure.title("Legacy Flow-Superlease Signing-Credit Card with Autopay-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    @pytest.mark.testrail("C65004")
    def test_legacy_flow_superlease_signing_credit_card_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=True)
        )
