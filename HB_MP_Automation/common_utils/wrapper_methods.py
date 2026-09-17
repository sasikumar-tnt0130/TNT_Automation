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


def confirmation_dir_for_current_test(reports_dir: Path) -> Path:
    """reports/confirmations/<test name>-<timestamp>/ for whichever
    pytest test is currently running, read from the PYTEST_CURRENT_TEST
    env var pytest sets for the duration of a test (no fixture/
    parameter plumbing needed through every call site). Groups a
    reservation's confirmation + email screenshots under one folder per
    test instead of a flat pile keyed only by reservation code, so
    which test produced which pair is obvious without cross-referencing
    Allure. Callers compute this once (e.g. in __init__) and reuse it -
    calling again mid-test would mint a new timestamp and split the
    pair across two folders."""
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "unknown")
    test_name = current_test.split("::")[-1].split(" ")[0]
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
    """Renders a Mailinator email's HTML body in a throwaway page (a new
    tab in the same browser context, not the caller's own page - the
    caller's page is usually still mid-flow, e.g. about to resume the
    reservation into a rental) and screenshots it, for the same
    visual-record reason as save_confirmation_screenshot. Mailinator's
    own API (see mailinator_utils.wait_for_email) is a plain HTTP
    fetch, not a live page - there's nothing to screenshot without
    rendering the body somewhere first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    email_page = context.new_page()
    try:
        email_page.set_content(html, wait_until="load")
        email_page.screenshot(path=str(path), full_page=True)
    finally:
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
