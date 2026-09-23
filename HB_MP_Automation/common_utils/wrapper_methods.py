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


def save_confirmation_screenshot(
    page: Page, path: Path, allure_name: str, *, attach_allure: bool = True
) -> None:
    """Screenshots the current page (e.g. a reservation confirmation)
    and saves it to ``path``. Viewport only — full_page on thank-you /
    rental forms is slow and rarely needed for the report.

    When ``attach_allure`` is true (default), also attaches to Allure —
    set false when Rent-it only writes the file so Verify rental
    confirmation emails can attach it next to the matching email.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    png = page.screenshot(type="png", full_page=False)
    path.write_bytes(png)
    if attach_allure:
        allure.attach(
            png,
            name=allure_name,
            attachment_type=allure.attachment_type.PNG,
        )


def attach_saved_screenshot(path: Path, allure_name: str) -> bool:
    """Attach an existing PNG to Allure. Returns True when the file was found."""
    if not path.is_file():
        return False
    allure.attach(
        path.read_bytes(),
        name=allure_name,
        attachment_type=allure.attachment_type.PNG,
    )
    return True


def save_email_screenshot(
    context: BrowserContext, html: str, path: Path, allure_name: str
) -> None:
    """Renders an email's HTML body and screenshots the whole message.

    Uses a temporary tab on the caller's context (same Chromium window) so
    headed runs do not open a third browser window for each email shot.

    ``domcontentloaded`` (not ``load``) avoids hanging on tracking pixels /
    remote images. The tab is then sized to the document so the shot includes
    the body below the first screen.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    email_page = context.new_page()
    png = b""
    try:
        # Timeout: remote assets in email HTML must not block the suite.
        # Stop at domcontentloaded. Waiting for "load" sits on tracking
        # pixels that never finish.
        email_page.set_content(html, wait_until="domcontentloaded", timeout=15_000)
        height = email_page.evaluate(
            """() => Math.ceil(Math.max(
                document.documentElement.scrollHeight || 0,
                document.body ? document.body.scrollHeight : 0,
                800
            ))"""
        )
        height = min(max(int(height), 800), 9000)
        full_page = True
        try:
            width = (email_page.viewport_size or {}).get("width") or 1280
            email_page.set_viewport_size({"width": int(width), "height": height})
            full_page = False
        except Exception:
            pass
        png = email_page.screenshot(type="png", full_page=full_page)
        path.write_bytes(png)
    finally:
        try:
            email_page.close()
        except Exception:
            pass
    if png:
        allure.attach(
            png,
            name=allure_name,
            attachment_type=allure.attachment_type.PNG,
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
