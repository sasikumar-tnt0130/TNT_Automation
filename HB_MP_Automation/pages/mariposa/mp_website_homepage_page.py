from dataclasses import dataclass

import allure
from playwright.sync_api import Locator, Page, expect
from common_utils.wrapper_methods import log_method_exceptions
from pages.common.hb_settings_navigation import HBSettingsNavigation


@dataclass(frozen=True)
class HomepageDescription:
    label: str
    locator: Locator


class MPWebsiteHomepagePage:
    """Website Homepage settings, configured under HB Settings' Website (Mariposa) app."""

    DESCRIPTION_LABELS = (
        "Company Logo Alt Text",
        "Mobile Logo Alt Text",
        "Company Logo Title",
        "Mobile Logo Title",
        "Homepage Title",
        "Primary Value Statement",
        "Secondary Value Statement",
        "Property Widget Heading",
        "Social Media Widget Heading",
        "Blog Heading",
        "Size Guide Heading",
        "Testimonial Heading",
        "Testimonial Description",
        "Preferred Social Media Review",
        "Meta Title",
        "Meta Description",
        "Local SEO content",
    )
    OPTIONAL_DESCRIPTION_LABELS = {
        "Company Logo Alt Text",
        "Local SEO content",
        "Meta Description",
        "Mobile Logo Alt Text",
        "Secondary Value Statement",
        "Social Media Widget Heading",
        "Preferred Social Media Review",
    }

    @log_method_exceptions
    def __init__(
        self, page: Page, timeout: float, nav: HBSettingsNavigation
    ) -> None:
        self.page = page
        self.timeout = timeout
        self.nav = nav

    @log_method_exceptions
    def open_homepage_settings(self) -> None:
        self.nav.open_settings_panel()
        self.nav.switch_app_filter_to_website()
        homepage_link = self.page.get_by_text("Website Homepage", exact=True)
        with allure.step("Open Website Homepage settings"):
            expect(homepage_link).to_be_visible(timeout=self.timeout)
            homepage_link.click()
        for section in (
            "Company Logo (280 X 130",
            "Mobile Logo Image (280 X 130",
            "Company Logo Alt Text",
            "Mobile Logo Alt Text",
            "Company Logo Title",
            "Mobile Logo Title",
            "Homepage Title",
            "Primary Value Statement",
            "Secondary Value Statement",
            "Property Widget Heading",
            "Social Media Widget Heading",
            "Blog Heading",
            "Size Guide Heading",
            "Testimonial Heading",
            "Testimonial Description",
            "Preferred Social Media Review",
            "General Settings",
            "Homepage Meta Content",
            "Featured Blogs or Company",
            "Featured Blogs",
            "Company Pages",
            "Local SEO content",
        ):
            with allure.step(f"Expand homepage section: {section}"):
                self.page.get_by_text(section, exact=False).last.click()

    @log_method_exceptions
    def locate_field(self, label: str) -> Locator:
        label_locator = self.page.get_by_text(label, exact=True).last
        return label_locator.locator(
            "xpath=following::*[(self::input or self::textarea or @contenteditable='true')][1]"
        )

    @log_method_exceptions
    def collect_description_fields(self) -> list[HomepageDescription]:
        return [
            HomepageDescription(label, self.locate_field(label))
            for label in self.DESCRIPTION_LABELS
        ]

    @log_method_exceptions
    def get_field_value(self, label: str) -> str:
        field = self.locate_field(label).first
        with allure.step(f"Read homepage field: {label}"):
            if field.evaluate("element => element.matches('input, textarea')"):
                return field.input_value()
            return (field.text_content() or "").strip()

    @log_method_exceptions
    def set_field_value(self, label: str, value: str) -> None:
        field = self.locate_field(label).first
        with allure.step(f"Set homepage field '{label}' to: {value}"):
            if field.evaluate("element => element.matches('input, textarea')"):
                field.fill(value)
            else:
                field.click()
                self.page.keyboard.press("Control+A")
                self.page.keyboard.type(value)

    @log_method_exceptions
    def locate_image_input(self, label_prefix: str) -> Locator:
        heading = self.page.get_by_text(label_prefix, exact=False).first
        return heading.locator("xpath=following::input[@type='file'][1]")

    @log_method_exceptions
    def upload_image(self, label_prefix: str, file_path: str) -> None:
        with allure.step(f"Upload image for '{label_prefix}': {file_path}"):
            self.locate_image_input(label_prefix).set_input_files(file_path)

    @log_method_exceptions
    def remove_image(self, label_prefix: str) -> None:
        with allure.step(f"Remove image for '{label_prefix}'"):
            heading = self.page.get_by_text(label_prefix, exact=False).first
            remove_button = heading.locator("xpath=following::button[1]")
            if remove_button.count() > 0 and remove_button.is_visible():
                remove_button.click()

    @log_method_exceptions
    def save(self) -> None:
        with allure.step("Save Website Homepage settings"):
            self.page.get_by_role("button", name="Save", exact=True).click()
            # Callers flush once via nav.clear_cache after all Saves.

    @log_method_exceptions
    def assert_descriptions_are_populated(self) -> None:
        missing: list[str] = []
        for description in self.collect_description_fields():
            with allure.step(f"Validate homepage description: {description.label}"):
                control_count = description.locator.count()
                is_optional = description.label in self.OPTIONAL_DESCRIPTION_LABELS
                if control_count == 0:
                    allure.attach(
                        "Control found: no\n"
                        f"Required field: {not is_optional}\n"
                        "Result: failed - control not found",
                        name=f"{description.label} validation log",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    missing.append(f"{description.label} (control not found)")
                    continue

                control = description.locator.first
                expect(control).to_be_visible()
                value = control.input_value() if control.evaluate(
                    "element => element.matches('input, textarea')"
                ) else control.text_content()
                value_state = "populated" if value and value.strip() else "empty"
                allure.attach(
                    "Control found: yes\n"
                    "Control visible: yes\n"
                    f"Required field: {not is_optional}\n"
                    f"Value state: {value_state}\n"
                    f"Value: {(value or '<empty>').strip()}",
                    name=f"{description.label} validation log",
                    attachment_type=allure.attachment_type.TEXT,
                )
                allure.attach(
                    (value or "<empty>").strip(),
                    name=f"{description.label} value",
                    attachment_type=allure.attachment_type.TEXT,
                )
                if (
                    not is_optional
                    and (not value or not value.strip())
                ):
                    missing.append(description.label)

        assert not missing, "Homepage descriptions are missing or empty: " + ", ".join(
            missing
        )
