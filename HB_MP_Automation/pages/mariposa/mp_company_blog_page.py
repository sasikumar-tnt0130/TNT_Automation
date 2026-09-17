import re

import allure
from playwright.sync_api import Page, expect

from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation
from common_utils.waits import waits


class MPCompanyBlogPage:
    """Company Blogs CMS, configured under HB Settings' Website (Mariposa) app.

    Status has four values (unlike Company Pages' three):
    - Published: publish date is today, immediately live.
    - Publish Later: publish date picker only allows tomorrow or later.
    - Draft: no publish date; not live.
    - Publish Early: publish date picker only allows yesterday-or-earlier
      (today and future disabled) - this is how a blog gets a backdated
      publish date. It is a one-shot action, not a stored state: saving
      converts the blog to Status=Published with that past date.
    """

    STATUSES = ("Published", "Publish Later", "Draft", "Publish Early")

    @log_method_exceptions
    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation, hb_base_url: str
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav
        self.hb_dashboard_url = hb_base_url.rstrip("/").removesuffix("/login") + "/dashboard"
        self.created_titles: list[str] = []
        self._pending_new_blog = False

    @log_method_exceptions
    def open_company_blogs(self) -> None:
        # Tests routinely bounce over to Mariposa (a different domain) to
        # verify a blog, then come back here to edit it - always
        # re-navigate to the HB dashboard first so this works regardless
        # of where the page currently is, rather than assuming we're
        # already on an HB page.
        if not self.page.url.startswith(self.hb_dashboard_url.rsplit("/dashboard", 1)[0]):
            self.page.goto(self.hb_dashboard_url, wait_until="commit")
        self.nav.open_settings_panel()
        with allure.step("Open Company Blogs settings"):
            link = self.page.get_by_role("listitem").filter(
                has_text=re.compile(r"^Company Blogs$")
            )
            # The app filter switch has been observed to occasionally not
            # stick on repeat calls within the same test (still showing
            # the "hummingbird" app's menu afterward) - retry rather than
            # trusting one call to have switched it.
            for _ in range(3):
                self.nav.switch_app_filter_to_website()
                try:
                    expect(link).to_be_visible(timeout=waits().long)
                    break
                except AssertionError:
                    continue
            else:
                expect(link).to_be_visible(timeout=self.timeout)
            link.click()

    @log_method_exceptions
    def _ensure_on_list(self) -> None:
        """save() ends by clearing cache, which navigates away from the
        Company Blogs list - every method below that needs the list (the
        search box, "+ Add New Company Blog") calls this first so callers
        don't have to remember to re-navigate after every save()."""
        search_box = self.page.get_by_role(
            "textbox", name="Search By Title or Slug"
        )
        if search_box.count() == 0 or not search_box.is_visible():
            self.open_company_blogs()

    @log_method_exceptions
    def add_new_company_blog(self) -> None:
        with allure.step("Add new Company Blog"):
            self._ensure_on_list()
            self.page.get_by_text("+ Add New Company Blog", exact=True).click()
            # Marks the next fill_title() call as the one that names a
            # brand-new blog, so it can be recorded for cleanup - see
            # created_titles / delete_company_blog.
            self._pending_new_blog = True

    @log_method_exceptions
    def delete_company_blog(self, title: str, *, timeout: float | None = None) -> None:
        """Deletes a Company Blog by title via its row's "..." menu ->
        Delete -> Continue (confirmed live - the confirmation dialog is
        titled "Delete Entry" and its confirm button reads "Continue",
        not "Delete" or "Yes"). `timeout` overrides self.timeout for the
        row-visibility checks - see cleanup_created_blogs, which passes a
        short one so a title that was tracked but never actually saved
        (e.g. a rejected-upload test that never calls save()) fails fast
        instead of waiting the full timeout for a row that will never
        appear."""
        wait = self.timeout if timeout is None else timeout
        with allure.step(f"Delete Company Blog: {title}"):
            self.search(title)
            row = self.page.get_by_role("row", name=re.compile(re.escape(title)))
            expect(row).to_be_visible(timeout=wait)
            row.locator(".mdi-dots-vertical").click()
            self.page.get_by_role("button", name="Delete", exact=True).click()
            continue_button = self.page.get_by_role(
                "button", name="Continue", exact=True
            )
            expect(continue_button).to_be_visible(timeout=wait)
            continue_button.click()
            expect(row).not_to_be_visible(timeout=wait)

    @log_method_exceptions
    def cleanup_created_blogs(self) -> None:
        """Deletes every blog created via add_new_company_blog() +
        fill_title() during this page object's lifetime - intended for
        test teardown so QA automation runs don't leave test data behind
        in shared environments. Not every tracked title was necessarily
        saved (a rejected-image-upload test may never call save()), so
        each delete uses a short timeout rather than self.timeout -
        otherwise every never-saved title would burn a full timeout in
        teardown for a row that will never exist."""
        for title in self.created_titles:
            try:
                self.delete_company_blog(title, timeout=waits().short)
            except Exception:
                pass
        self.created_titles = []

    @log_method_exceptions
    def search(self, query: str) -> None:
        with allure.step(f"Search Company Blogs for: {query}"):
            self._ensure_on_list()
            search_box = self.page.get_by_role(
                "textbox", name="Search By Title or Slug"
            )
            search_box.click()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.type(query)
            search_box.press("Enter")

    @log_method_exceptions
    def open_company_blog(self, title: str) -> None:
        with allure.step(f"Open Company Blog: {title}"):
            self.search(title)
            row = self.page.get_by_role("row", name=re.compile(re.escape(title)))
            expect(row).to_be_visible(timeout=self.timeout)
            row.click()

    @log_method_exceptions
    def get_list_status_and_date(self, title: str) -> tuple[str, str]:
        """Read the Status and Publish Date cell text for `title`'s row on
        the Company Blogs list (searches first, same as open_company_blog,
        but reads the row instead of clicking it)."""
        with allure.step(f"Read Company Blogs list row for: {title}"):
            self.search(title)
            row = self.page.get_by_role("row", name=re.compile(re.escape(title)))
            expect(row).to_be_visible(timeout=self.timeout)
            cells = row.get_by_role("cell")
            status = (cells.nth(2).text_content() or "").strip()
            publish_date = (cells.nth(3).text_content() or "").strip()
            return status, publish_date

    @log_method_exceptions
    def open_content_tab(self) -> None:
        self.page.get_by_role("tab", name="Content", exact=True).click()

    @log_method_exceptions
    def open_settings_tab(self) -> None:
        self.page.get_by_role("tab", name="Settings", exact=True).click()

    @log_method_exceptions
    def fill_title(self, title: str) -> None:
        with allure.step(f"Set Company Blog title: {title}"):
            self.open_content_tab()
            self.page.get_by_role("textbox", name="Enter Blog Title").fill(title)
            if self._pending_new_blog:
                self.created_titles.append(title)
                self._pending_new_blog = False

    @log_method_exceptions
    def get_slug(self) -> str:
        """Reads the auto-generated Slug field. Confirmed live
        (2026-09-07): the title-to-slug watcher doesn't fire from
        filling the Title field alone - the Slug field stays empty (or
        keeps a stale value from whatever title was entered before it)
        indefinitely, no matter how long you wait, until the Slug field
        itself receives a click/focus event. This was previously chalked
        up entirely to an intermittent website-h1-tags API 400 (see
        project_slug_generation_bug memory) - that's still a real,
        separate failure mode, but clicking the field first is what
        actually resolves the far more common "just never triggered"
        case. The wait after the click is for the watcher's own async
        completion, not a click-vs-not race anymore."""
        field = self.page.get_by_role(
            "textbox", name="Enter Title to generate Slug"
        )
        field.click()
        expect(field).not_to_have_value("", timeout=self.timeout)
        return field.input_value()

    @log_method_exceptions
    def select_category(self, category: str | None = None) -> str:
        """Select `category` if given, otherwise whichever category is
        first in the dropdown - callers that don't care which category is
        used shouldn't have to hardcode a name that may not exist in
        every environment/property. Returns the category name selected."""
        with allure.step(f"Select Company Blog category: {category or '(first available)'}"):
            # Playwright's coordinate-based click on this trigger keeps
            # getting intercepted by the fixed Settings header toolbar
            # (its computed scroll-into-view position sits right under
            # it), even with force=True - which still dispatches at
            # screen coordinates the browser then hit-tests, so it can
            # land on the toolbar instead. A JS .click() on the element
            # itself sidesteps that entirely.
            trigger = self.page.get_by_role(
                "textbox", name="Select Company Blog Category"
            )
            trigger.evaluate("el => el.click()")
            # See select_author for why this is scoped to the listbox
            # following THIS trigger rather than a page-wide :visible
            # lookup.
            listbox = trigger.locator(
                "xpath=following::*[@role='listbox'][1]"
            )
            expect(listbox).to_be_visible(timeout=self.timeout)
            option = (
                listbox.get_by_role("option", name=category, exact=True)
                if category
                else listbox.get_by_role("option").first
            )
            selected_text = option.text_content() or ""
            option.evaluate("el => el.click()")
            return selected_text.strip()

    @log_method_exceptions
    def select_related_property(self, property_name: str | None = None) -> str:
        """Select `property_name` if given (matched by substring, e.g.
        "Bellflower"), otherwise the first real property (skipping the
        default "Not Specified" option). Single-select, same trigger
        pattern as select_category. Returns the selected option text."""
        with allure.step(
            f"Select Company Blog related property: {property_name or '(first available)'}"
        ):
            trigger = self.page.get_by_role(
                "textbox", name="Select Related Property"
            )
            trigger.evaluate("el => el.click()")
            listbox = trigger.locator("xpath=following::*[@role='listbox'][1]")
            expect(listbox).to_be_visible(timeout=self.timeout)
            option = (
                listbox.get_by_role("option", name=property_name, exact=False)
                if property_name
                else listbox.get_by_role("option").nth(1)
            )
            selected_text = option.text_content() or ""
            option.evaluate("el => el.click()")
            return selected_text.strip()

    def _author_listbox(self):
        """Clicks the Author trigger and returns a Locator scoped to its
        own listbox via the trigger's aria-owns id - confirmed live that
        neither Escape nor "xpath=following::*[@role='listbox'][1]"
        reliably works here: Escape does NOT close this multi-select
        dropdown (confirmed live: 2 listboxes stayed visible after
        Escape following a prior open), so a later open's "first
        following listbox" can resolve to a stale one left over from an
        earlier call in the same test (e.g. get_author_options() then
        select_authors() in sequence) - this caused real pytest timeouts
        hunting for a specific option name inside the wrong listbox. The
        trigger's aria-owns id is stable across repeated opens (same
        Vuetify component instance), so scoping by it sidesteps staleness
        entirely rather than depending on any close step actually
        working - the same fix pattern already proven for Phase 5's
        Featured Blogs slot dropdowns."""
        trigger = self.page.get_by_role("button", name="Select an author")
        trigger.evaluate("el => el.click()")
        listbox_id = trigger.evaluate("el => el.getAttribute('aria-owns')")
        listbox = self.page.locator(f"#{listbox_id}")
        expect(listbox).to_be_visible(timeout=self.timeout)
        return listbox

    @log_method_exceptions
    def select_author(self, author: str | None = None) -> str:
        """Select `author` if given, otherwise whichever author is first
        in the dropdown. Returns the author name selected."""
        with allure.step(f"Select Company Blog author: {author or '(first available)'}"):
            listbox = self._author_listbox()
            option = (
                listbox.get_by_role("option", name=author, exact=True)
                if author
                else listbox.get_by_role("option").first
            )
            selected_text = option.text_content() or ""
            option.evaluate("el => el.click()")
            return selected_text.strip()

    @log_method_exceptions
    def select_authors(self, authors: list[str]) -> list[str]:
        """Selects multiple authors in one dropdown session (Author is a
        multi-select checkbox dropdown - see select_author)."""
        with allure.step(f"Select Company Blog authors: {authors}"):
            listbox = self._author_listbox()
            selected_texts = []
            for author in authors:
                option = listbox.get_by_role("option", name=author, exact=True)
                selected_texts.append((option.text_content() or "").strip())
                option.evaluate("el => el.click()")
            return selected_texts

    @log_method_exceptions
    def select_all_authors(self) -> list[str]:
        """Clicks the Author dropdown's "Select All" menu item (confirmed
        live: it exists above the option list and selects every currently
        available author in one action) and returns the resulting
        selected author names."""
        with allure.step("Select all Company Blog authors"):
            listbox = self._author_listbox()
            listbox.get_by_role("menuitem", name="Select All", exact=True).evaluate(
                "el => el.click()"
            )
            selected = listbox.locator(
                '[role="option"][aria-selected="true"]'
            ).all_text_contents()
            return [s.strip() for s in selected]

    @log_method_exceptions
    def get_author_options(self) -> list[str]:
        """Opens the Author dropdown (without selecting anything) and
        returns all available option texts. Deliberately leaves the
        dropdown open afterward rather than trying to close it - Escape
        doesn't reliably close this multi-select dropdown (confirmed
        live), and every other author-slot lookup is scoped by
        aria-owns id (see _author_listbox), not by visibility, so a
        lingering open dropdown here is harmless."""
        with allure.step("Read Company Blog author options"):
            listbox = self._author_listbox()
            options = listbox.get_by_role("option").all_text_contents()
            return [o.strip() for o in options]

    SOCIAL_MEDIA_FIELDS = {
        "Facebook": "Enter Facebook URL",
        "Twitter": "Enter Twitter URL",
        "Pinterest": "Enter Pinterest URL",
        "Google My Business": "Enter Google My Business URL",
        "Linkedin": "Add Linkedin URL",
        "YouTube": "Enter Youtube URL",
        "Instagram": "Enter Instagram URL",
    }

    @log_method_exceptions
    def open_add_edit_author(self) -> None:
        with allure.step("Open Add/Edit Author modal"):
            self.page.get_by_role(
                "button", name="+ Add/Edit Author"
            ).evaluate("el => el.click()")

    def _active_author_modal(self):
        """Scopes to the topmost visible ".hb-modal-wrapper" - clicking
        "Edit" on an author row opens a SECOND, separate modal titled
        "Edit Author" stacked on top of the original "Add/Edit Author"
        one (confirmed live: both stay in the DOM simultaneously, each
        with their own full set of Name/Email/Designation/Description
        fields), rather than replacing it. An unscoped field lookup
        matches the first (empty, "Add") one; every form-interaction
        method below must go through this to reliably target whichever
        modal is actually active."""
        return self.page.locator(".hb-modal-wrapper:visible").last

    @log_method_exceptions
    def fill_author_form(
        self,
        *,
        name: str | None = None,
        email: str | None = None,
        designation: str | None = None,
        description: str | None = None,
        social: dict[str, str] | None = None,
    ) -> None:
        with allure.step("Fill Add/Edit Author form"):
            modal = self._active_author_modal()
            if name is not None:
                modal.get_by_role("textbox", name="Enter Author Name").fill(name)
            if email is not None:
                modal.get_by_role("textbox", name="Enter Author Email").fill(email)
            if designation is not None:
                modal.get_by_role(
                    "textbox", name="Enter Author Designation"
                ).fill(designation)
            if description is not None:
                modal.get_by_role(
                    "textbox", name="Enter Author Description"
                ).fill(description)
            for platform, url in (social or {}).items():
                field_name = self.SOCIAL_MEDIA_FIELDS[platform]
                modal.get_by_role("textbox", name=field_name).fill(url)

    @log_method_exceptions
    def save_author(self, expected_name: str | None = None) -> None:
        """Saves the active Add/Edit Author form (see _active_author_modal
        for why this must be scoped). If `expected_name` is given, waits
        for that name to appear in the Authors list table before
        returning - the table doesn't update instantly, and callers that
        read it right after save() can otherwise catch it before the new/
        edited row lands."""
        with allure.step("Save author"):
            self._active_author_modal().get_by_role(
                "button", name="Save", exact=True
            ).evaluate("el => el.click()")
            if expected_name:
                expect(
                    self.page.get_by_role("row", name=expected_name, exact=False)
                ).to_be_visible(timeout=self.timeout)

    @log_method_exceptions
    def get_author_field_errors(self) -> list[str]:
        errors = self._active_author_modal().locator(
            ".v-messages__message"
        ).all_text_contents()
        # Vuetify renders the same message 3x (once per validation trigger
        # source) - confirmed live - dedupe while preserving order.
        seen: list[str] = []
        for error in errors:
            text = error.strip()
            if text and text not in seen:
                seen.append(text)
        return seen

    @log_method_exceptions
    def get_authors_list(self) -> list[str]:
        with allure.step("Read authors list"):
            return [
                t.strip()
                for t in self.page.locator("table tbody tr").all_text_contents()
            ]

    @log_method_exceptions
    def edit_author(self, name: str) -> None:
        with allure.step(f"Edit author: {name}"):
            row = self.page.get_by_role("row", name=name, exact=False)
            row.locator('[aria-hidden]').first.evaluate("el => el.click()")
            # The row's action menu (Edit/Delete) renders a moment after
            # the kebab icon click - clicking "Edit" immediately can land
            # before it's actually visible/interactive (confirmed live:
            # this silently no-ops, leaving the "Add" form's fields empty
            # instead of opening the "Edit Author" modal).
            edit_item = self.page.get_by_text("Edit", exact=True)
            expect(edit_item).to_be_visible(timeout=self.timeout)
            edit_item.evaluate("el => el.click()")

    @log_method_exceptions
    def delete_author(self, name: str) -> None:
        with allure.step(f"Delete author: {name}"):
            row = self.page.get_by_role("row", name=name, exact=False)
            row.locator('[aria-hidden]').first.evaluate("el => el.click()")
            delete_item = self.page.get_by_text("Delete", exact=True)
            expect(delete_item).to_be_visible(timeout=self.timeout)
            delete_item.evaluate("el => el.click()")
            self.page.get_by_role(
                "button", name="Continue", exact=True
            ).evaluate("el => el.click()")

    @log_method_exceptions
    def close_author_modal(self) -> None:
        """Closes the topmost visible author modal via its title-bar "x"
        icon (name="QA-v-card-HbIcon-mdi-close", confirmed live) rather
        than either Cancel button - the modal has two identically-labeled
        "Cancel" buttons (its own, and the underlying "Add Company Blog"
        form's own), and earlier live testing chasing what looked like a
        "clicking Cancel loses the whole form" bug turned out to be a
        false alarm from checking survival with a raw `button` tag query
        (document.querySelectorAll('button')) against a trigger that's
        actually a <div role="button"> - a real, working Cancel click was
        being misdiagnosed as broken. The "x" icon is still preferred
        here since it's unambiguous, sidestepping the need to
        disambiguate between the two Cancel buttons at all. Scoped to the
        topmost modal so closing an "Edit Author" overlay doesn't
        accidentally target the "Add/Edit Author" one underneath it."""
        with allure.step("Close Add/Edit Author modal"):
            self._active_author_modal().locator(
                'button[name="QA-v-card-HbIcon-mdi-close"]'
            ).evaluate("el => el.click()")

    @log_method_exceptions
    def fill_contents(self, contents: str) -> None:
        with allure.step("Set Company Blog contents"):
            editor = self.page.get_by_text("Contents*", exact=True).locator(
                "xpath=following::*[@contenteditable='true'][1]"
            )
            editor.click()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.type(contents)

    @log_method_exceptions
    def _image_upload_card(self):
        """Scopes to the "Header File" card's image half via its stable
        "header-media" class (confirmed live in the DOM) - avoids the
        fragile alternative of walking a fixed number of ancestor divs
        up from the "Image (16:9 Aspect Ratio)" label."""
        return self.page.get_by_text(
            "Image (16:9 Aspect Ratio)", exact=True
        ).locator("xpath=ancestor::*[contains(@class,'header-media')]")

    @log_method_exceptions
    def upload_image(self, file_path: str) -> None:
        """Uploads a file to the Header File image dropzone. Aspect
        ratio (16:9, with a confirmed-live tolerance band of roughly
        1.6-1.8) and the 5MB max size are both validated client-side on
        file selection, before any network call - a rejected file never
        reaches the server, it's just rejected with a "Warning: ..."
        toast (see get_image_upload_error) and the dropzone stays empty.
        Confirmed live: the dropzone's own text/description elements sit
        on top of the real <input type="file"> and intercept clicks
        aimed at the input directly, so the click has to target the
        visible dropzone text instead."""
        with allure.step(f"Upload Company Blog header image: {file_path}"):
            self.open_content_tab()
            dropzone_text = self._image_upload_card().get_by_text(
                "Drag and drop images into this area", exact=False
            )
            with self.page.expect_file_chooser() as chooser_info:
                dropzone_text.first.click()
            chooser_info.value.set_files(file_path)
            # Client-side validation (aspect ratio / size) and the
            # resulting DOM update (dropzone -> preview, or a "Warning:
            # ..." toast) aren't instant - wait for whichever of those
            # two terminal states arrives (a single JS poll rather than
            # two sequential Playwright waits, so a rejected upload
            # doesn't have to burn the full accept-path timeout first).
            # The dropzone check is scoped to the "header-media" card's
            # own textContent, not document-wide - confirmed live that a
            # hidden, unrelated <script> tag elsewhere on the page
            # happens to contain this same dropzone copy verbatim (an
            # inlined component template in the bundled JS), which a
            # document-wide textContent search falsely matches forever.
            self.page.wait_for_function(
                """() => {
                    const card = [...document.querySelectorAll('.header-media')].find(
                        c => c.textContent.includes('Image (16:9 Aspect Ratio)')
                    );
                    const dropzone = !!card
                        && card.textContent.includes('Drag and drop images into this area');
                    const warning = [...document.querySelectorAll('*')].some(
                        e => e.children.length === 0
                            && e.offsetParent !== null
                            && e.textContent.trim().startsWith('Warning:')
                    );
                    return !dropzone || warning;
                }""",
                timeout=self.timeout,
            )

    @log_method_exceptions
    def get_image_upload_error(self) -> str:
        """Reads the "Warning: ..." toast shown after a rejected image
        upload. Empty string if no such warning is currently showing.
        Scoped to the ".hb-notification-warning" container rather than
        matched by "Warning:" text directly - confirmed live that the
        "Warning:" prefix renders in its own bold <span> nested inside
        the full-message <span>, so a text-based match lands on the
        inner element and returns just "Warning:" with the rest of the
        sentence cut off."""
        warning = self.page.locator(".hb-notification-warning")
        if warning.count() == 0 or not warning.first.is_visible():
            return ""
        return " ".join((warning.first.text_content() or "").split())

    @log_method_exceptions
    def is_image_uploaded(self) -> bool:
        """Whether the Header File dropzone currently shows an accepted
        image (the dropzone prompt is replaced by a preview + remove
        button once a file is accepted - confirmed live)."""
        return self._image_upload_card().get_by_text(
            "Drag and drop images into this area", exact=False
        ).count() == 0

    @log_method_exceptions
    def remove_image(self) -> None:
        with allure.step("Remove Company Blog header image"):
            self.open_content_tab()
            self._image_upload_card().locator("button").first.click()

    @log_method_exceptions
    def fill_image_alt_text(self, alt_text: str) -> None:
        with allure.step(f"Set header image alt text: {alt_text}"):
            self.open_content_tab()
            self.page.get_by_role(
                "textbox", name="Enter Alt Text"
            ).fill(alt_text)

    @log_method_exceptions
    def set_status(self, status: str) -> None:
        with allure.step(f"Set Company Blog status: {status}"):
            self.open_settings_tab()
            # See select_category for why this is a JS click rather than
            # a coordinate-based one.
            self.page.get_by_role(
                "button", name=re.compile(r"^Status\*")
            ).evaluate("el => el.click()")
            option = self.page.get_by_role("option", name=status, exact=True)
            expect(option).to_be_visible(timeout=self.timeout)
            option.evaluate("el => el.click()")

    @log_method_exceptions
    def set_publish_date_day(self, day: int, *, months_back: int = 0) -> None:
        """Open the Publish Date calendar (only shown for Publish Later /
        Publish Early) and click the given day number. Publish Later only
        enables tomorrow-or-later; Publish Early only enables
        yesterday-or-earlier - pick a day consistent with whichever status
        is active. `months_back` clicks the calendar's previous-month
        arrow that many times first, for picking a date in an earlier
        month than the one shown by default."""
        with allure.step(f"Set publish date day: {day} (months_back={months_back})"):
            self.open_settings_tab()
            self.page.get_by_role("button", name="Publish Date").evaluate(
                "el => el.click()"
            )
            for _ in range(months_back):
                self.page.get_by_role(
                    "button", name="Previous month"
                ).evaluate("el => el.click()")
            # Scope to the open calendar menu - an unscoped page-wide
            # button search for a bare day number like "4" can match
            # unrelated UI (e.g. a notification badge showing "4"), not
            # just the calendar grid.
            calendar = self.page.get_by_role("menu")
            # The calendar grid can also show the same day number twice
            # within itself (e.g. a trailing/leading day from an adjacent
            # month at the same grid position) - one enabled, one
            # disabled/greyed - so excluding disabled buttons is required
            # too, not just cosmetic.
            day_button = calendar.locator(
                'button:not([disabled])'
            ).filter(has_text=re.compile(rf"^{day}$"))
            expect(day_button).to_have_count(1, timeout=self.timeout)
            day_button.evaluate("el => el.click()")
            self.page.keyboard.press("Escape")

    @log_method_exceptions
    def get_publish_date(self) -> str:
        with allure.step("Read Company Blog publish date"):
            self.open_settings_tab()
            button = self.page.get_by_role("button", name="Publish Date")
            if button.count() == 0:
                return ""
            return button.text_content() or ""

    @log_method_exceptions
    def save(self) -> None:
        with allure.step("Save Company Blog"):
            self.page.get_by_role(
                "button", name="Save Blog", exact=True
            ).evaluate("el => el.click()")
            success = self.page.get_by_text(
                "Company Blog details successfully updated", exact=True
            )
            caution_label = self.page.get_by_text("Caution:", exact=False)
            outcome = success.or_(caution_label)
            expect(outcome).to_be_visible(timeout=self.timeout)
            if caution_label.is_visible():
                caution_banner = caution_label.locator("xpath=ancestor::div[2]")
                raise AssertionError(
                    f"Save Company Blog was rejected: {caution_banner.text_content()}"
                )
            self.nav.mark_website_cache_clear_pending()
            self.nav.clear_cache()
