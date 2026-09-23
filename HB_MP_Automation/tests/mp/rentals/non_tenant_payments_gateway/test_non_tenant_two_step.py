import allure
import pytest

from common_utils.mp_rental_cases import RentalCase
from tests.mp.rentals._helpers import (
    ensure_module_payment_gateways,
    ensure_two_step_superlease,
)

# 2Step Flow-Superlease Signing (individual + RAB) on Non-Tenant Payments.

pytestmark = [
    pytest.mark.mp_rental,
    pytest.mark.non_tenant_payments_gateway,
]


@pytest.fixture(scope="module", autouse=True)
def precondition(
    hb_admin_session,
    environment,
    environment_config,
    app_config,
    two_step_property,
    payment_gateways,
    gateway_profile,
    module_payment_gateways_ready,
):
    """Once for this file: Two-Step signing + payment gateways."""
    ensure_two_step_superlease(
        hb_admin_session, environment_config, app_config, two_step_property
    )
    ensure_module_payment_gateways(
        hb_admin_session,
        environment,
        environment_config,
        app_config,
        payment_gateways,
        gateway_profile,
        two_step=True,
        ready=module_payment_gateways_ready,
    )

@allure.feature("MP Rentals")
@allure.story("2Step Flow: Super Lease Signing - Individual (Non-Tenant Payments Gateway)")
class TestNonTenantTwoStepSuperleaseIndividual:
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
            RentalCase(payment="card", autopay=False, view="desktop", rab=False, reserve=False), two_step=True
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
            RentalCase(payment="card", autopay=True, view="desktop", rab=False, reserve=False), two_step=True
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
            RentalCase(payment="card", autopay=False, view="mobile", rab=False, reserve=False), two_step=True
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
            RentalCase(payment="card", autopay=True, view="mobile", rab=False, reserve=False), two_step=True
        )

@allure.feature("MP Rentals")
@allure.story("2Step Flow: Super Lease Signing - RAB (Non-Tenant Payments Gateway)")
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
            RentalCase(payment="card", autopay=False, view="desktop", rab=True, reserve=False), two_step=True
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
            RentalCase(payment="card", autopay=True, view="desktop", rab=True, reserve=False), two_step=True
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
            RentalCase(payment="card", autopay=False, view="mobile", rab=True, reserve=False), two_step=True
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
            RentalCase(payment="card", autopay=True, view="mobile", rab=True, reserve=False), two_step=True
        )


