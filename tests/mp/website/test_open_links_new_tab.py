import allure
import pytest

from pages.mariposa.mp_new_tab_links_page import MPNewTabLinksPage

# Old Robot Mariposa/Open_links_newTab. Read-only on the storefront.
# Not migrated (user choice 2026-09-14): 13679 (published company pages open
# in a new tab) and 13680 (blogs from the landing page open in a new tab) -
# the uat_storoutlet storefront lists no company pages and Bellflower's
# landing page has no blog section; to revisit once the CompanyBlog / company
# page suites create their own content.


def _storefront(page, environment_config, app_config) -> MPNewTabLinksPage:
    return MPNewTabLinksPage(page, environment_config.mp_base_url, app_config.getint("browser", "timeout"))


@allure.title("The storefront's footer pages open in a new tab")
@allure.feature("MP Website")
@allure.story("Open links in new tab")
def test_footer_pages_open_in_new_tab(page, environment_config, app_config, mp_property_url) -> None:
    # 14242: Sitemap, Privacy Policy & Terms and Contact us, on the home page
    # and a property landing page (user choice 2026-09-14).
    if not mp_property_url:
        pytest.skip("No storefront property (mp_city/mp_state) configured for this environment")
    storefront = _storefront(page, environment_config, app_config)
    with allure.step("On the home page"):
        storefront.open_storefront()
        storefront.assert_footer_pages_open_in_new_tab()
    with allure.step("On the property landing page"):
        storefront.open_property_page(mp_property_url)
        storefront.assert_footer_pages_open_in_new_tab()


@allure.title("Each social link opens its own network in a new tab")
@allure.feature("MP Website")
@allure.story("Open links in new tab")
def test_social_links_open_their_network(page, environment_config, app_config, mp_property_url) -> None:
    # 13676, on a property landing page (the home page has no social links).
    # Each link must open the network its title names - Bellflower's "Twitter"
    # link pointed to facebook.com/tenantinc (2026-09-14), a storefront
    # content issue this test reports (user choice).
    if not mp_property_url:
        pytest.skip("No storefront property (mp_city/mp_state) configured for this environment")
    storefront = _storefront(page, environment_config, app_config)
    storefront.open_property_page(mp_property_url)
    problems = storefront.social_link_problems()
    assert not problems, "Social links not opening their own network: " + "; ".join(problems)
