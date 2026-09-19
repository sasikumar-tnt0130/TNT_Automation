import allure
import pytest

from common_utils.mp_rental_cases import RentalCase

# User's rental scenarios (2026-09-15): "2Step Flow-Superlease Signing" as a
# business (RAB) - the individual cases are in
# test_non_tenant_two_step_individual.py - on the non-Tenant-Payments gateway:
# cards go through Authorize.Net, set on both rental properties from
# environments.ini once per session (this folder's conftest.py gateway_profile
# = non_tenant_payments, tests/mp/rentals/conftest.py payment_gateways). Card
# only: that profile has no ACH gateway. One explicit test per scenario, its
# markers on the test. Each is one real rental, checked on the storefront, in
# the guest's inbox and in HB - found by its space number - then moved out
# (common_utils/mp_rental_cases.py). Module fixture ``two_step_superlease_checked``
# enables Two-Step + Super Lease + Clickwrap and flushes website cache.


@allure.feature("MP Rentals")
@allure.story("2Step Flow: Super Lease Signing - RAB (Non-Tenant Payments Gateway)")
@pytest.mark.mp_rental
@pytest.mark.non_tenant_payments_gateway
@pytest.mark.two_step_superlease
@pytest.mark.usefixtures("two_step_superlease_checked")
class TestNonTenantTwoStepSuperleaseRab:
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
