"""Hosted card formats — Tenant Payments / Two-Step.

Valid card data (PAN 16/19, expiry YY/YYYY, CVV 3/4) must complete the rental
and pass rental confirmation (storefront + emails + HB).
"""

from __future__ import annotations

import allure
import pytest

from common_utils.mp_rental_cases import RentalCase
from tests.mp.rentals._hosted_card_ui import (
    card_for_cvv_3,
    card_for_cvv_4,
    card_for_expiry_yy,
    card_for_expiry_yyyy,
    card_for_pan_16,
    card_for_pan_19,
)


@allure.feature("MP Rentals")
@allure.story("Hosted card payments — Tenant Payments / Two-Step")
@allure.link(
    "https://storagefront.atlassian.net/browse/MRECOM-323",
    name="MRECOM-323",
)
@pytest.mark.mp_rental
@pytest.mark.tenant_payments_gateway
@pytest.mark.two_step_superlease
@pytest.mark.usefixtures("two_step_superlease_checked")
class TestTenantTwoStepHostedPayments:
    @allure.title("2Step-Tenant Payments-16-digit card-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_two_step_16_digit_card_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            two_step=True,
            card=card_for_pan_16(environment_config),
        )

    @allure.title("2Step-Tenant Payments-19-digit card-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_two_step_19_digit_card_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            two_step=True,
            card=card_for_pan_19(environment_config),
        )

    @allure.title("2Step-Tenant Payments-Expiry MMYY-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_two_step_expiry_mmyy_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            two_step=True,
            card=card_for_expiry_yy(environment_config),
        )

    @allure.title("2Step-Tenant Payments-Expiry MMYYYY-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_two_step_expiry_mmyyyy_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            two_step=True,
            card=card_for_expiry_yyyy(environment_config),
        )

    @allure.title("2Step-Tenant Payments-CVV 3 digits-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_two_step_cvv_3_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            two_step=True,
            card=card_for_cvv_3(environment_config),
        )

    @allure.title("2Step-Tenant Payments-CVV 4 digits (Amex)-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_two_step_cvv_4_amex_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            two_step=True,
            card=card_for_cvv_4(environment_config),
        )
