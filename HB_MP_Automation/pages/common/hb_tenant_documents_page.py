import re

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

from common_utils.wrapper_methods import log_method_exceptions
from common_utils.waits import waits


class HBTenantDocumentsPage:
    """Tenant details "Documents" panel: upload a file against a
    tenant's record. Ported from the old Robot Framework smoke suite's
    "For tenants upload files" scenario - confirmed live (2026-09-10,
    stage) that uploading no longer requires picking which of the
    tenant's spaces to attach the file to (a dropdown with scrolling-
    list search the old suite's Upload File keyword had to handle) - a
    single upload now applies straight to the tenant."""

    @log_method_exceptions
    def __init__(self, page: Page, timeout: float) -> None:
        self.page = page
        self.timeout = timeout

    @log_method_exceptions
    def _close_live_agent_notification(self) -> None:
        live_agent_notification = self.page.get_by_text(
            "Need to talk to a live agent?", exact=True
        )
        # Scoped to the banner's own tooltip: an unscoped ".mdi-close" .first
        # can be an open drawer's or dialog's own close X (confirmed live
        # 2026-09-13 - it closed the move-out drawer, see HBMoveOutPage).
        close_notification = (
            self.page.locator(".v-tooltip__content.custom-tooltip-popup")
            .filter(has_text="Need to talk to a live agent?")
            .locator(".mdi-close")
        )
        if live_agent_notification.count() > 0 and live_agent_notification.first.is_visible():
            if close_notification.count() > 0 and close_notification.first.is_visible():
                try:
                    close_notification.first.click(timeout=waits().short)
                except PlaywrightTimeoutError:
                    pass

    @log_method_exceptions
    def open_tenants(self, property_name: str) -> None:
        with allure.step(f"Open tenants for {property_name}"):
            self._close_live_agent_notification()
            search_box = self.page.locator("#search-box")
            expect(search_box).to_be_visible(timeout=self.timeout)
            search_box.click()
            # Same picker widget as HBMoveOutPage.open_tenants/
            # HBLeadManagementPage.open_leads - the target property
            # isn't guaranteed to already be on top, so type the name to
            # filter down to it explicitly instead of hoping.
            search_input = search_box.locator("input")
            property_cell = self.page.get_by_role(
                "cell", name=property_name, exact=True
            )
            try:
                expect(property_cell).to_be_visible(timeout=waits().short)
            except AssertionError:
                search_input.fill(property_name)
                expect(property_cell).to_be_visible(timeout=self.timeout)
            property_cell.click()
            # Same multi-property picker quirk as HBLeadManagementPage.
            # open_leads: only a click on the row selects it there.
            try:
                expect(property_cell).to_be_hidden(timeout=waits().short)
            except AssertionError:
                property_cell.locator("xpath=ancestor::tr[1]").dispatch_event(
                    "click"
                )
            # Wait until the dashboard header names the property - see
            # HBTenantSpacesPage.open_tenants (a run went on company-wide).
            expect(
                self.page.get_by_role("textbox", name=property_name)
            ).to_be_visible(timeout=self.timeout)
            tenants_link = self.page.get_by_role("complementary").get_by_text(
                "Tenants", exact=True
            )
            expect(tenants_link).to_be_visible(timeout=self.timeout)
            tenants_link.locator(
                "xpath=ancestor::*[@role='listitem'][1]"
            ).dispatch_event("click")
            self._close_live_agent_notification()

    @log_method_exceptions
    def open_tenant_details(self, first_name: str, last_name: str) -> None:
        full_name = f"{first_name} {last_name}"
        with allure.step(f"Open tenant details for {full_name}"):
            search_tenants = self.page.get_by_role(
                "textbox", name="Search Tenants", exact=True
            )
            expect(search_tenants).to_be_visible(timeout=self.timeout)
            search_tenants.fill(full_name)
            self.page.keyboard.press("Enter")

            # Unlike the Leads grid (see HBLeadManagementPage), this
            # Tenants grid's rows do expose their cell text as their own
            # accessible name - confirmed live (2026-09-10, stage) - so
            # the tenant name cell can be matched directly.
            tenant_cell = self.page.get_by_role(
                "gridcell", name=full_name, exact=True
            )
            expect(tenant_cell).to_be_visible(timeout=self.timeout)
            tenant_cell.click()
            expect(
                self.page.get_by_text(full_name, exact=True).first
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def open_documents_menu(self) -> None:
        with allure.step("Open documents in the tenant sidebar"):
            # Prefer direct URL (same pattern as Gate Access). Sidebar
            # "Documents" often goes unstable/not-visible after tenant
            # validation scroll (stage 2026-09-19) while the href is already
            # /contacts/<id>/files.
            contact = re.search(r"/contacts/([^/?#]+)", self.page.url)
            if contact:
                origin = re.match(r"https?://[^/]+", self.page.url).group(0)
                self.page.goto(
                    f"{origin}/contacts/{contact.group(1)}/files",
                    wait_until="domcontentloaded",
                )
            else:
                sidebar_toggle = self.page.locator(
                    'button[name="QA-HbHeader-HbIcon-mdi-table-actions-custom-1"]'
                )
                expect(sidebar_toggle).to_be_visible(timeout=self.timeout)
                sidebar_toggle.click()
                documents_link = self.page.locator(
                    "a[href*='/files']"
                ).filter(has_text=re.compile(r"^\s*Documents\s*$"))
                expect(documents_link.first).to_be_visible(timeout=self.timeout)
                documents_link.first.click(force=True)
            expect(
                self.page.get_by_role("button", name="Upload File", exact=True)
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def upload_file(self, file_path: str) -> None:
        with allure.step(f"Upload file: {file_path}"):
            self.page.get_by_role(
                "button", name="Upload File", exact=True
            ).click()

            # Confirmed live: the attach icon's accessible name is
            # "prepend icon" (a Vuetify slot name leaking through as the
            # aria-label) rather than anything describing its purpose -
            # its rendered "attach_file" text is icon-ligature content,
            # not the accessible name.
            with self.page.expect_file_chooser() as file_chooser_info:
                self.page.get_by_role(
                    "button", name="prepend icon", exact=True
                ).click()
            file_chooser_info.value.set_files(file_path)

            upload_confirm_button = self.page.get_by_role(
                "button", name="Upload", exact=True
            )
            expect(upload_confirm_button).to_be_enabled(timeout=self.timeout)
            upload_confirm_button.click()

    @log_method_exceptions
    def assert_file_uploaded(self, file_name: str) -> None:
        with allure.step(f"Verify uploaded file appears: {file_name}"):
            file_row = self.page.get_by_role(
                "row", name=re.compile(re.escape(file_name))
            )
            expect(file_row.first).to_be_visible(timeout=self.timeout)
            expect(
                file_row.first.get_by_text("Uploaded", exact=True)
            ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def assert_documents_listed(self, document_names: list[str]) -> None:
        """Generated rental documents appear in the tenant Documents panel
        (name substring match). Walked live 2026-09-16 stage/Garden Grove:
        Lease Agreement, Autopay Enrollment Document, Military Waiver,
        Vehicle Addendum (when vehicle storing was ticked)."""
        with allure.step(f"Verify documents listed: {document_names}"):
            expect(
                self.page.get_by_role("button", name="Upload File", exact=True)
            ).to_be_visible(timeout=self.timeout)
            for name in document_names:
                row = self.page.get_by_role(
                    "row", name=re.compile(re.escape(name), re.I)
                )
                expect(row.first).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def document_row(self, document_name: str):
        """Tenant Documents grid row whose File Name contains document_name."""
        return self.page.get_by_role(
            "row", name=re.compile(re.escape(document_name), re.I)
        ).first

    @log_method_exceptions
    def open_document_pdf_text(
        self, document_name: str, space_number: str | None = None
    ) -> str:
        """Row kebab -> View/Print opens a CloudFront PDF in a new tab
        (walked live 2026-09-16 stage). Captures PDF bytes (network / browser
        fetch / retried API get), attaches to Allure, returns pypdf text.

        ``space_number`` scopes the lease space-card screenshot to that unit.
        """
        from io import BytesIO
        from pathlib import Path

        from pypdf import PdfReader

        from common_utils.wrapper_methods import confirmation_dir_for_current_test

        def _looks_like_pdf_response(response) -> bool:
            try:
                if response.status != 200:
                    return False
                ctype = (response.headers.get("content-type") or "").lower()
                if "application/pdf" in ctype:
                    return True
                url = (response.url or "").lower()
                return any(
                    token in url
                    for token in ("cloudfront.net", "pandadoc", "superlease", ".pdf")
                )
            except Exception:
                return False

        def _bytes_from_response(response) -> bytes | None:
            try:
                raw = response.body()
            except Exception:
                return None
            return raw if raw and raw[:4] == b"%PDF" else None

        def _fetch_via_browser(page, url: str) -> bytes | None:
            try:
                data = page.evaluate(
                    """async (url) => {
                        const r = await fetch(url, { credentials: 'include' });
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        return Array.from(new Uint8Array(await r.arrayBuffer()));
                    }""",
                    url,
                )
                raw = bytes(data)
                return raw if raw[:4] == b"%PDF" else None
            except Exception as exc:
                allure.attach(
                    f"{type(exc).__name__}: {exc}"[:800],
                    name=f"{document_name} browser fetch failed",
                    attachment_type=allure.attachment_type.TEXT,
                )
                return None

        def _fetch_via_api(url: str) -> bytes | None:
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    response = self.page.context.request.get(url, timeout=60_000)
                    if response.status != 200:
                        last_error = AssertionError(f"HTTP {response.status}")
                        continue
                    raw = response.body()
                    if raw[:4] == b"%PDF":
                        return raw
                    last_error = AssertionError(f"not a PDF ({raw[:20]!r})")
                except Exception as exc:
                    last_error = exc
                    self.page.wait_for_timeout(waits().short)
            if last_error is not None:
                allure.attach(
                    f"{type(last_error).__name__}: {last_error}"[:800],
                    name=f"{document_name} API fetch failed",
                    attachment_type=allure.attachment_type.TEXT,
                )
            return None

        with allure.step(f"View or print document PDF: {document_name}"):
            row = self.document_row(document_name)
            expect(row).to_be_visible(timeout=self.timeout)
            row.locator(".mdi-dots-vertical").first.click()
            view = self.page.get_by_role("menuitem", name="View/Print", exact=True)
            expect(view).to_be_visible(timeout=self.timeout)

            captured: list[bytes] = []

            def _on_response(response) -> None:
                if not _looks_like_pdf_response(response):
                    return
                raw = _bytes_from_response(response)
                if raw is not None:
                    captured.append(raw)

            self.page.context.on("response", _on_response)
            pdf_page = None
            try:
                with self.page.context.expect_page() as new_page_info:
                    view.click()
                pdf_page = new_page_info.value
                pdf_page.wait_for_load_state("domcontentloaded")
                deadline = self.timeout
                waited = 0
                while waited < deadline and not (
                    pdf_page.url.startswith("http://")
                    or pdf_page.url.startswith("https://")
                ):
                    pdf_page.wait_for_timeout(500)
                    waited += 500
                if not (
                    pdf_page.url.startswith("http://")
                    or pdf_page.url.startswith("https://")
                ):
                    raise AssertionError(
                        f"PDF tab for {document_name!r} never reached an "
                        f"http(s) URL (got {pdf_page.url!r})"
                    )

                # Let late CloudFront responses settle into the listener.
                for _ in range(10):
                    if captured:
                        break
                    pdf_page.wait_for_timeout(300)

                body = captured[-1] if captured else None
                if body is None:
                    body = _fetch_via_browser(pdf_page, pdf_page.url)
                if body is None:
                    body = _fetch_via_api(pdf_page.url)
                if body is None:
                    raise AssertionError(
                        f"Could not download PDF bytes for {document_name!r} "
                        f"from {pdf_page.url!r} (network capture, browser "
                        f"fetch, and API get all failed)"
                    )

                safe = re.sub(r"[^\w.-]+", "_", document_name).strip("_") or "lease"
                reports_dir = Path(__file__).resolve().parents[2] / "reports"
                pdf_path = (
                    confirmation_dir_for_current_test(reports_dir) / f"{safe}.pdf"
                )
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(body)
                allure.attach(
                    body,
                    name=f"{document_name} lease agreement",
                    attachment_type=allure.attachment_type.PDF,
                    extension="pdf",
                )
                from common_utils.mp_payment_report import (
                    attach_payment_screenshots_from_pdf,
                )

                attach_payment_screenshots_from_pdf(
                    body,
                    document_name=document_name,
                    space_number=space_number,
                )
                text = "".join(
                    (pdf_pg.extract_text() or "")
                    for pdf_pg in PdfReader(BytesIO(body)).pages
                )
                return text
            finally:
                try:
                    self.page.context.remove_listener("response", _on_response)
                except Exception:
                    pass
                if pdf_page is not None:
                    try:
                        pdf_page.close()
                    except Exception:
                        pass

    @log_method_exceptions
    def assert_document_pdf_contains(
        self,
        document_name: str,
        expected_snippets: list[str],
        space_number: str | None = None,
    ) -> str:
        """Open the named document and assert each snippet appears in its PDF text."""
        text = self.open_document_pdf_text(
            document_name, space_number=space_number
        )
        lowered = text.lower()
        missing = [
            snippet
            for snippet in expected_snippets
            if snippet and snippet.lower() not in lowered
        ]
        if missing:
            raise AssertionError(
                f"{document_name!r} PDF missing {missing!r}. "
                f"Sample: {text[:500]!r}"
            )
        return text

