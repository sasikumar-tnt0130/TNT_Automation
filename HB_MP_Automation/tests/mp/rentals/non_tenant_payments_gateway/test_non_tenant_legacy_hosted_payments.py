"""Hosted card formats — Non-Tenant Payments / Legacy.

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
@allure.story("Hosted card payments — Non-Tenant Payments / Legacy")
@allure.link(
    "https://storagefront.atlassian.net/browse/MRECOM-323",
    name="MRECOM-323",
)
@pytest.mark.mp_rental
@pytest.mark.non_tenant_payments_gateway
@pytest.mark.legacy_traditional
@pytest.mark.usefixtures("legacy_traditional_signing")
class TestNonTenantLegacyHostedPayments:
    @allure.title("Legacy-Non-Tenant Payments-16-digit card-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_legacy_16_digit_card_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            card=card_for_pan_16(environment_config),
        )

    @allure.title("Legacy-Non-Tenant Payments-19-digit card-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_legacy_19_digit_card_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            card=card_for_pan_19(environment_config),
        )

    @allure.title("Legacy-Non-Tenant Payments-Expiry MMYY-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_legacy_expiry_mmyy_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            card=card_for_expiry_yy(environment_config),
        )

    @allure.title("Legacy-Non-Tenant Payments-Expiry MMYYYY-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_legacy_expiry_mmyyyy_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            card=card_for_expiry_yyyy(environment_config),
        )

    @allure.title("Legacy-Non-Tenant Payments-CVV 3 digits-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_legacy_cvv_3_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            card=card_for_cvv_3(environment_config),
        )

    @allure.title("Legacy-Non-Tenant Payments-CVV 4 digits (Amex)-rental confirmation")
    @pytest.mark.card
    @pytest.mark.no_autopay
    @pytest.mark.desktop
    @pytest.mark.individual
    def test_legacy_cvv_4_amex_rental_confirmation(
        self, rental_case_runner, environment_config
    ) -> None:
        rental_case_runner(
            RentalCase(payment="card", autopay=False, view="desktop", rab=False),
            card=card_for_cvv_4(environment_config),
        )
