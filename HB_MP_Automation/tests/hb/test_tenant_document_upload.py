from pathlib import Path

import allure

from common_utils.hb_quick_launch_lease_setup import create_lease_through_quick_action
from pages.common.hb_tenant_documents_page import HBTenantDocumentsPage

UPLOAD_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "test_data" / "test_upload.txt"
)


@allure.title('A document can be uploaded for a tenant')
@allure.feature("HB Smoke Test")
@allure.story("For tenants upload files")
def test_upload_file_for_tenant(
    hb_login_page, app_config, environment_config, test_data, hb_lead_guest
) -> None:
    hb_login_page.open_login_page()
    hb_login_page.submit_login_credentials()
    hb_login_page.assert_login_successful()

    lease_data = test_data("quick_launch_lease")
    create_lease_through_quick_action(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
        environment_config,
        lease_data,
        hb_lead_guest,
    )

    tenant_documents = HBTenantDocumentsPage(
        hb_login_page.page,
        app_config.getint("browser", "timeout"),
    )
    tenant_documents.open_tenants(lease_data["property_name"])
    tenant_documents.open_tenant_details(
        hb_lead_guest["first_name"], hb_lead_guest["last_name"]
    )
    tenant_documents.open_documents_menu()
    tenant_documents.upload_file(str(UPLOAD_FIXTURE_PATH))
    tenant_documents.assert_file_uploaded(UPLOAD_FIXTURE_PATH.name)
