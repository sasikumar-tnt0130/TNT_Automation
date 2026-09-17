from collections.abc import Callable
from datetime import datetime
from functools import wraps
import logging
import os
from pathlib import Path
import re
from typing import ParamSpec, TypeVar

import allure
from playwright.sync_api import BrowserContext, Locator, Page


Parameters = ParamSpec("Parameters")
ReturnValue = TypeVar("ReturnValue")


# Set by conftest's pytest_runtest_setup from request.node.name so
# reservation setups (and any other mid-test caller) get a stable
# folder name even when PYTEST_CURRENT_TEST is missing.
CURRENT_TEST_ENV = "HB_MP_CURRENT_TEST"


def confirmation_dir_for_current_test(
    reports_dir: Path, test_name: str | None = None
) -> Path:
    """reports/confirmations/<test name>-<timestamp>/ for whichever
    pytest test is currently running.

    Prefer an explicit `test_name` (e.g. request.node.name). Otherwise
    use HB_MP_CURRENT_TEST (set by conftest from the pytest item name),
    then PYTEST_CURRENT_TEST. Only falls back to \"unknown\" outside a
    pytest run (e.g. a walk script). Callers compute this once (e.g.
    in __init__) and reuse it - calling again mid-test would mint a
    new timestamp and split screenshots across two folders."""
    if not test_name:
        test_name = os.environ.get(CURRENT_TEST_ENV, "").strip()
    if not test_name:
        current_test = os.environ.get("PYTEST_CURRENT_TEST", "")
        # PYTEST_CURRENT_TEST looks like
        # "path/to/test.py::Class::test_name[param] (call)".
        test_name = (
            current_test.split("::")[-1].split(" ")[0] if current_test else "unknown"
        )
    test_name = re.sub(r"[^A-Za-z0-9_.\[\]-]+", "_", test_name)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return reports_dir / "confirmations" / f"{test_name}-{timestamp}"


def save_confirmation_screenshot(page: Page, path: Path, allure_name: str) -> None:
    """Screenshots the current page (e.g. a reservation confirmation)
    and both saves it to `path` and attaches it to the Allure report -
    the same kind of visual record a failure already gets via
    conftest's own failure-screenshot hook, but for a successful
    outcome worth keeping proof of too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)
    allure.attach(
        path.read_bytes(), name=allure_name, attachment_type=allure.attachment_type.PNG
    )


def save_email_screenshot(
    context: BrowserContext, html: str, path: Path, allure_name: str
) -> None:
    """Renders a Mailinator email's HTML body and screenshots it.

    Uses a throwaway context with no video recording so the tab does not
    split the test's single Playwright execution video (Playwright writes
    one .webm per page in a recording context).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    browser = context.browser
    scratch = browser.new_context() if browser is not None else None
    email_page = scratch.new_page() if scratch is not None else context.new_page()
    try:
        email_page.set_content(html, wait_until="load")
        email_page.screenshot(path=str(path), full_page=True)
    finally:
        if scratch is not None:
            scratch.close()
        else:
            email_page.close()
    allure.attach(
        path.read_bytes(), name=allure_name, attachment_type=allure.attachment_type.PNG
    )


def first_visible(locator: Locator) -> Locator:
    """Pick the first genuinely visible match from a locator instead of
    assuming index 0 is visible. Several Mariposa storefront pages
    duplicate content for mobile/desktop responsive layouts, with the
    inactive copy CSS-hidden rather than removed, so an unqualified
    ".first" can silently resolve to a hidden element and fail
    visibility checks."""
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            return candidate
    return locator.first


class LogMethodExceptions:
    """Decorator that logs and re-raises any exception raised by the wrapped method."""

    def __call__(
        self, method: Callable[Parameters, ReturnValue]
    ) -> Callable[Parameters, ReturnValue]:
        @wraps(method)
        def wrapped(
            *args: Parameters.args, **kwargs: Parameters.kwargs
        ) -> ReturnValue:
            try:
                return method(*args, **kwargs)
            except Exception:
                logging.getLogger(method.__module__).exception(
                    "Exception in %s", method.__qualname__
                )
                raise

        return wrapped


log_method_exceptions = LogMethodExceptions()
