import allure
import pytest

from common_utils.mp_rental_cases import RentalCase
from tests.mp.rentals._helpers import (
    ensure_legacy_traditional,
    ensure_module_payment_gateways,
)

# Legacy Flow-Traditional Signing (individual + RAB) on Tenant Payments.

pytestmark = [
    pytest.mark.mp_rental,
    pytest.mark.tenant_payments_gateway,
]


@pytest.fixture(scope="module", autouse=True)
def precondition(
    hb_admin_session,
    environment,
    environment_config,
    app_config,
    payment_gateways,
    gateway_profile,
    module_payment_gateways_ready,
):
    """Once for this file: Traditional signing + payment gateways."""
    ensure_legacy_traditional(hb_admin_session, environment_config, app_config)
    ensure_module_payment_gateways(
        hb_admin_session,
        environment,
        environment_config,
        app_config,
        payment_gateways,
        gateway_profile,
        ready=module_payment_gateways_ready,
    )
    pass

@allure.feature("MP Rentals")
@allure.story("Legacy Flow: Traditional Signing - Individual")
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
            RentalCase(payment="card", autopay=False, view="desktop", rab=False, reserve=False)
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
            RentalCase(payment="ach", autopay=False, view="desktop", rab=False, reserve=False)
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
            RentalCase(payment="card", autopay=True, view="desktop", rab=False, reserve=False)
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
            RentalCase(payment="ach", autopay=True, view="desktop", rab=False, reserve=False)
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
            RentalCase(payment="card", autopay=False, view="mobile", rab=False, reserve=False)
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
            RentalCase(payment="ach", autopay=False, view="mobile", rab=False, reserve=False)
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
            RentalCase(payment="card", autopay=True, view="mobile", rab=False, reserve=False)
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
            RentalCase(payment="ach", autopay=True, view="mobile", rab=False, reserve=False)
        )
@allure.feature("MP Rentals")
@allure.story("Legacy Flow: Traditional Signing - RAB")
class TestTraditionalSigningRab:
    @allure.title("Legacy Flow-Traditional Signing-Credit Card-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_credit_card_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=True, reserve=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_ach_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="desktop", rab=True, reserve=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-Credit Card with Autopay-DesktopView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_credit_card_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="desktop", rab=True, reserve=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH with Autopay-DesktopView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.desktop
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_ach_with_autopay_desktop_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="desktop", rab=True, reserve=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-Credit Card-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_credit_card_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="mobile", rab=True, reserve=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.no_autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_ach_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=False, view="mobile", rab=True, reserve=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-Credit Card with Autopay-MobileView-RAB")
    @pytest.mark.card
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_credit_card_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=True, view="mobile", rab=True, reserve=False)
        )

    @allure.title("Legacy Flow-Traditional Signing-ACH with Autopay-MobileView-RAB")
    @pytest.mark.ach
    @pytest.mark.autopay
    @pytest.mark.mobile
    @pytest.mark.rab
    @pytest.mark.smoke
    @pytest.mark.testrail("C10478")
    @pytest.mark.testrail("C20849")
    def test_legacy_flow_traditional_signing_ach_with_autopay_mobile_view_rab(
        self, rental_case_runner
    ) -> None:
        rental_case_runner(
            RentalCase(payment="ach", autopay=True, view="mobile", rab=True, reserve=False)
        )


