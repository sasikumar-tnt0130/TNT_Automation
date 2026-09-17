import allure
import pytest
from playwright.sync_api import expect

from pages.common.hb_settings_navigation import HBSettingsNavigation
from pages.mariposa.mp_name_and_address_info_page import MPNameAndAddressInfoPage

# Old Robot Mariposa/SyncReviewThroughCMS. Read-only (user choice 2026-09-14):
# nothing is typed, saved or synced.
# Not migrated: C16922 / C16925 (sync, then the reviews on the landing page),
# C16926 / C16927 ("Syncing" -> "Reviews synced successfully"), C16937 (the
# reviews in every landing layout), C16969 / C16970 (only a Google / only a
# Yelp ID), C16979 / C16980 (the last-sync date) and C17112 (removing the IDs)
# - each needs a sync (review data fetched and a sync date written) or a
# change to a property's IDs or landing layout. On uat_storoutlet no property
# has ever been synced: Irvine, the only one with review IDs, shows no
# last-sync date and its landing page says "No Reviews" (2026-09-14).


@allure.title("Name and Address Info offers Sync Reviews, enabled only for a property with a review ID")
@allure.feature("MP Website")
@allure.story("Sync reviews through CMS")
def test_sync_reviews_button_state(hb_login_page, app_config, environment_config, test_data) -> None:
    # C16921 (the button is there) and C16924's button state: enabled with a
    # review ID, disabled with none - read on two properties instead of
    # editing the IDs.
    data = test_data("sync_reviews")
    if not (data.get("property_with_review_ids") and data.get("property_without_review_ids")):
        pytest.skip("No Sync Reviews properties configured for this environment")
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()
    timeout = app_config.getint("browser", "timeout")
    page = hb_login_page.page
    info = MPNameAndAddressInfoPage(
        page, timeout, HBSettingsNavigation(page, timeout), environment_config.hb_base_url
    )

    with allure.step(f"C16921/C16924: {data['property_with_review_ids']} has an ID and Sync Reviews is enabled"):
        info.open(data["property_with_review_ids"])
        # The form's values load after it shows - wait for one before trusting the rest.
        assert info.get_phone(), "The property's saved values never loaded"
        ids = {"Google Place ID": info.get_google_place_id(), "Yelp Business ID": info.get_yelp_business_id()}
        allure.attach(str(ids), name="Review IDs", attachment_type=allure.attachment_type.TEXT)
        assert any(ids.values()), f"Expected a review ID on {data['property_with_review_ids']}: {ids}"
        expect(info.sync_reviews_button()).to_be_visible(timeout=timeout)
        expect(info.sync_reviews_button()).to_be_enabled()

    with allure.step(f"C16924: {data['property_without_review_ids']} has no ID and Sync Reviews is disabled"):
        info.open(data["property_without_review_ids"])
        assert info.get_phone(), "The property's saved values never loaded"
        ids = {"Google Place ID": info.get_google_place_id(), "Yelp Business ID": info.get_yelp_business_id()}
        assert not any(ids.values()), f"Expected no review IDs on {data['property_without_review_ids']}: {ids}"
        expect(info.sync_reviews_button()).to_be_visible(timeout=timeout)
        expect(info.sync_reviews_button()).to_be_disabled()
