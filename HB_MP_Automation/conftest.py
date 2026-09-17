import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable, Generator
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from common_utils.browser_sessions import (
    attach_execution_trace_for_test,
    attach_execution_video_for_test,
    capture_page_failure_artifacts,
    chromium_launch_args,
    close_context_with_videos,
    desktop_context_options,
    desktop_viewport,
    maybe_start_tracing,
    prepare_desktop_page,
    reset_video_attach_state_for_test,
    storefront_failure_was_captured,
    video_recording_options,
)
from common_utils.test_data_reader import load_test_data
from common_utils.test_identities import new_hb_lead_guest
from common_utils.wrapper_methods import CURRENT_TEST_ENV
from config.config_reader import EnvironmentConfig, PropertyConfig, load_config, load_environment, property_for_role
from pages.common.hb_login_page import HBLoginPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"
ALLURE_RESULTS_DIR = REPORTS_DIR / "allure-results"
ALLURE_REPORT_DIR = REPORTS_DIR / "allure-report"
LOGS_DIR = REPORTS_DIR / "logs"

logger = logging.getLogger("hb_mp")

_CLEANUP_SUMMARY = pytest.StashKey[str]()
_TEST_LOG_PATH = pytest.StashKey[Path]()
_TEST_LOG_HANDLER = pytest.StashKey[logging.Handler]()


def _clean_before_session(config: pytest.Config, app_config: ConfigParser) -> str:
    """[cleanup] clean_before_session in config/environments.ini: deletes
    reports/ (Allure results and reports, logs, screenshots, test results)
    and every __pycache__ folder in the project before the session starts.
    Skipped for --collect-only, so counting tests can't wipe a run that's in
    progress. Anything Windows keeps locked (a report open elsewhere, say)
    is left in place and counted instead of failing the run."""
    if config.option.collectonly or not app_config.getboolean(
        "cleanup", "clean_before_session", fallback=False
    ):
        return ""
    locked: list[str] = []

    def note_locked(_function, path, _error) -> None:
        locked.append(str(path))

    if REPORTS_DIR.exists():
        shutil.rmtree(REPORTS_DIR, onexc=note_locked)
    caches = [
        path
        for path in PROJECT_ROOT.rglob("__pycache__")
        if not any(part.startswith(".") for part in path.relative_to(PROJECT_ROOT).parts)
    ]
    for cache in caches:
        shutil.rmtree(cache, onexc=note_locked)
    summary = f"clean_before_session: removed reports/ and {len(caches)} __pycache__ folder(s)"
    if locked:
        summary += f"; {len(locked)} locked item(s) left in place, e.g. {locked[0]}"
    return summary


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Per-test setup shared by confirmation screenshots and rerunfailures.

    1. Publish the pytest node name for confirmation screenshot folders
       (reservation setups call confirmation_dir_for_current_test without
       an explicit test_name; PYTEST_CURRENT_TEST alone has landed under
       reports/confirmations/unknown-*).
    2. Start a per-test file log (reports/logs/) capturing INFO+ from the
       suite loggers for Allure verification.
    3. On a pytest-rerunfailures retry (execution_count > 1), clear every
       "*_configured" fixture cache so class-scoped preconditions redo
       admin HB setup instead of reusing state from the failed attempt.
    """
    os.environ[CURRENT_TEST_ENV] = item.name
    reset_video_attach_state_for_test(item.name)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.name)[:100]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    log_path = LOGS_DIR / f"{safe}-{stamp}.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    item.stash[_TEST_LOG_PATH] = log_path
    item.stash[_TEST_LOG_HANDLER] = handler
    logger.info("START %s", item.nodeid)

    if getattr(item, "execution_count", 1) <= 1:
        return
    fixture_info = getattr(item, "_fixtureinfo", None)
    for name, fixture_defs in getattr(fixture_info, "name2fixturedefs", {}).items():
        if not name.endswith("_configured"):
            continue
        for fixture_def in fixture_defs:
            fixture_def.cached_result = None
            if hasattr(fixture_def, "_finalizers"):
                fixture_def._finalizers.clear()


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    failed = getattr(getattr(item, "rep_call", None), "failed", None)
    try:
        attach_execution_video_for_test(
            load_config(), failed=failed, test_name=item.name
        )
    except Exception as video_error:
        logger.debug("execution-video attach skipped: %s", video_error)
    try:
        attach_execution_trace_for_test(
            load_config(), failed=failed, test_name=item.name
        )
    except Exception as trace_error:
        logger.debug("playwright-trace attach skipped: %s", trace_error)

    handler = item.stash.get(_TEST_LOG_HANDLER, None)
    if handler is not None:
        logger.info("END %s", item.nodeid)
        logging.getLogger().removeHandler(handler)
        handler.close()
        try:
            del item.stash[_TEST_LOG_HANDLER]
        except KeyError:
            pass
    if os.environ.get(CURRENT_TEST_ENV) == item.name:
        os.environ.pop(CURRENT_TEST_ENV, None)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Keep Allure output at the project root regardless of launch directory.
    tryfirst, so the optional clean-up runs before Allure opens
    reports/allure-results."""
    app_config = load_config()
    config.stash[_CLEANUP_SUMMARY] = _clean_before_session(config, app_config)
    config.option.allure_report_dir = str(ALLURE_RESULTS_DIR)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )

    # Default reruns/reruns_delay come from config/environments.ini's
    # [browser] section, so they're editable in one place instead of
    # remembering --reruns/--reruns-delay on every invocation - an
    # explicit --reruns/--reruns-delay on the command line still wins.
    for option, ini_key in (("reruns", "reruns"), ("reruns_delay", "reruns_delay")):
        cli_flag = f"--{ini_key.replace('_', '-')}"
        passed_on_cli = any(
            arg == cli_flag or arg.startswith(f"{cli_flag}=")
            for arg in config.invocation_params.args
        )
        if not passed_on_cli:
            setattr(
                config.option, option, app_config.getint("browser", ini_key, fallback=0)
            )


def pytest_report_header(config: pytest.Config) -> str | None:
    """Shows what clean_before_session removed, in pytest's header."""
    return config.stash.get(_CLEANUP_SUMMARY, "") or None


def _allure_report_name(config: pytest.Config) -> str:
    """Names the report after whatever was actually run - a single
    test file/case's own name (e.g. "test_login" or
    "test_login-test_can_login"), or "all-tests" for a full-suite run
    with no specific file/node-id on the command line - so a single
    test case's report doesn't get overwritten by, or confused with,
    a full-suite run's."""
    targets = [arg for arg in config.args if not arg.startswith("-")]
    if not targets:
        return "all-tests"
    names = []
    for target in targets:
        path_part, _, node_part = target.partition("::")
        name = Path(path_part).stem
        if node_part:
            name = f"{name}-{re.sub(r'[^A-Za-z0-9_.-]+', '_', node_part)}"
        names.append(name)
    return "_".join(names) if len(names) <= 3 else f"{len(names)}-targets"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Regenerate Allure HTML after every run (best-effort if CLI missing).

    Uses a multi-file report by default — open with `allure open`, not by
    double-clicking index.html in File Explorer (attachments will not load).
    Set [browser] allure_open = true to launch the viewer after generate.
    allure_single_file = true only if you truly need one self-contained HTML
    (embeds every video/trace and can reach hundreds of MB).
    """
    report_dir = ALLURE_REPORT_DIR / _allure_report_name(session.config)
    app_config = load_config()
    single_file = app_config.getboolean("browser", "allure_single_file", fallback=False)
    open_report = app_config.getboolean("browser", "allure_open", fallback=True)
    cmd = [
        "allure",
        "generate",
        str(ALLURE_RESULTS_DIR),
        "-o",
        str(report_dir),
        "--clean",
    ]
    if single_file:
        cmd.append("--single-file")
    try:
        subprocess.run(
            cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(f"\nAllure report: {report_dir}")
        if open_report and not single_file:
            # Detach so pytest can exit; `allure open` serves until closed.
            popen_kwargs: dict = {
                "shell": True,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                )
            subprocess.Popen(["allure", "open", str(report_dir)], **popen_kwargs)
            print(f"Opened with: allure open \"{report_dir}\"")
        elif not single_file:
            print(f"Open with: allure open \"{report_dir}\"")
    except FileNotFoundError:
        print("\nSkipped Allure report generation: 'allure' CLI not found on PATH.")
    except subprocess.CalledProcessError as error:
        print(f"\nAllure report generation failed:\n{error.stderr}")
    except subprocess.TimeoutExpired:
        print("\nSkipped Allure report generation: timed out after 120s.")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--env",
        action="store",
        default=None,
        help="MP environment from config/properties/<env>.ini, for example: --env uat_storoutlet",
    )
    parser.addoption(
        "--no-move-out",
        action="store_true",
        default=False,
        help=(
            "Skip HB move-out after rental tests so the space stays Current "
            "for inspection. Overrides [cleanup] move_out_after_rental."
        ),
    )
    parser.addoption(
        "--no-cancel-reservation",
        action="store_true",
        default=False,
        help=(
            "Skip HB cancel-reservation cleanup after tests so the lead/"
            "hold stays for inspection. Overrides "
            "[cleanup] cancel_reservation_after."
        ),
    )


@pytest.fixture(scope="session")
def app_config():
    return load_config()


@pytest.fixture(scope="session")
def environment(request: pytest.FixtureRequest, app_config) -> str:
    return request.config.getoption("--env") or app_config.get(
        "application", "default_environment"
    )


@pytest.fixture(scope="session")
def environment_config(app_config, environment: str) -> EnvironmentConfig:
    return load_environment(app_config, environment)


@pytest.fixture(scope="session")
def legacy_property(app_config, environment: str) -> PropertyConfig:
    """config/properties/<env>.ini legacy_property for this environment (Legacy)."""
    try:
        return property_for_role(app_config, environment, "legacy")
    except ValueError as error:
        pytest.skip(str(error))


@pytest.fixture(scope="session")
def two_step_property(app_config, environment: str) -> PropertyConfig:
    """config/properties/<env>.ini two_step_property for this environment (Two-Step)."""
    try:
        return property_for_role(app_config, environment, "two_step")
    except ValueError as error:
        pytest.skip(str(error))


@pytest.fixture(scope="session")
def move_out_after_rental(request: pytest.FixtureRequest, app_config) -> bool:
    """Whether rental tests should move the space out in cleanup.

    Default comes from [cleanup] move_out_after_rental in environments.ini
    (true). Pass --no-move-out to leave the rented space in place after the
    case finishes (useful when inspecting HB documents / tenant state).
    """
    if request.config.getoption("--no-move-out"):
        return False
    return app_config.getboolean(
        "cleanup", "move_out_after_rental", fallback=True
    )


@pytest.fixture(scope="session")
def cancel_reservation_after(request: pytest.FixtureRequest, app_config) -> bool:
    """Whether unfinished reservations should be cancelled in cleanup.

    Default comes from [cleanup] cancel_reservation_after in environments.ini
    (true). Pass --no-cancel-reservation to leave the reservation/lead hold
    in place for inspection.
    """
    if request.config.getoption("--no-cancel-reservation"):
        return False
    return app_config.getboolean(
        "cleanup", "cancel_reservation_after", fallback=True
    )


@pytest.fixture(scope="session")
def playwright() -> Generator[Playwright, None, None]:
    with sync_playwright() as playwright_instance:
        yield playwright_instance


@pytest.fixture(scope="session")
def browser(playwright: Playwright, app_config) -> Generator[Browser, None, None]:
    """One Chromium for the whole pytest session (headed or headless).

    Prefer new BrowserContext for isolation; do not launch Chromium per
    test or per step.
    """
    browser_name = app_config.get("browser", "name")
    browser_type = getattr(playwright, browser_name)
    headless = app_config.getboolean("browser", "headless")
    viewport = desktop_viewport()
    logger.info(
        "Launching %s headless=%s viewport=%sx%s record_video=%s attach_video=%s "
        "record_trace=%s attach_trace=%s",
        browser_name,
        headless,
        viewport["width"],
        viewport["height"],
        app_config.getboolean("browser", "record_video", fallback=False),
        app_config.get("browser", "attach_video", fallback="always"),
        app_config.getboolean("browser", "record_trace", fallback=True),
        app_config.get("browser", "attach_trace", fallback="on_failure"),
    )
    browser_instance = browser_type.launch(
        headless=headless,
        slow_mo=app_config.getint("browser", "slow_mo"),
        args=chromium_launch_args(headless=headless, app_config=app_config),
    )
    yield browser_instance
    logger.info("Closing session %s", browser_name)
    browser_instance.close()


def _browser_permissions(app_config) -> list[str]:
    """Delegates to browser_sessions.browser_permissions (single source)."""
    from common_utils.browser_sessions import browser_permissions

    return browser_permissions(app_config)


@pytest.fixture(scope="session")
def property_landing_page_url(
    browser: Browser, app_config
) -> Generator[Callable[[str, str, str], str], None, None]:
    """Factory: property_landing_page_url(mp_base_url, state, city) ->
    the MP storefront's exact property landing page URL for that
    state/city, discovered via the same click-through search
    MPUnitSearchPage.search_storage_location() uses and cached per
    (mp_base_url, state, city) for the rest of the session.

    Reuses one Chromium context for all discoveries in the session
    (same session browser as everything else) instead of
    open/close-per-lookup.
    """
    timeout = app_config.getint("browser", "timeout")
    cache: dict[tuple[str, str, str], str] = {}
    discovery_context: BrowserContext | None = None
    discovery_page: Page | None = None

    def discover(
        mp_base_url: str, state: str, city: str, page: Page | None = None
    ) -> str:
        nonlocal discovery_context, discovery_page
        key = (mp_base_url, state, city)
        if key in cache:
            return cache[key]
        # Prefer the caller's page (rental_case_runner) so we do not open a
        # third Chromium context just to resolve the landing URL.
        if page is not None:
            rental_page = MPUnitSearchPage(page, mp_base_url, timeout)
            rental_page.open_storefront()
            rental_page.search_storage_location(state=state, city=city)
            cache[key] = page.url
            return cache[key]
        if discovery_context is None:
            discovery_context = browser.new_context(
                **desktop_context_options(app_config, record_video=False)
            )
            discovery_page = discovery_context.new_page()
            prepare_desktop_page(discovery_page, app_config, record_artifacts=False)
        assert discovery_page is not None
        rental_page = MPUnitSearchPage(discovery_page, mp_base_url, timeout)
        rental_page.open_storefront()
        rental_page.search_storage_location(state=state, city=city)
        cache[key] = discovery_page.url
        return cache[key]

    yield discover
    if discovery_context is not None:
        close_context_with_videos(
            discovery_context, app_config, name="property-discovery-video"
        )


@pytest.fixture
def mp_property_url(
    environment_config: EnvironmentConfig,
    property_landing_page_url: Callable[[str, str, str], str],
) -> str | None:
    """property_landing_page_url resolved against this session's
    default environment_config (config/properties.ini) - covers
    every mobile test targeting that default property. None if this
    environment has no property configured (dev/uat), matching
    MPLegacyReservationSetup/MPTwoStepReservationSetup's own fallback to
    dynamic discovery in that case. Suites against a different
    property (e.g. test_two_step_individual_reservation.py, Lightning
    Storage/Rutland) call property_landing_page_url directly with
    their own config instead of using this fixture."""
    if not (environment_config.mp_state and environment_config.mp_city):
        return None
    return property_landing_page_url(
        environment_config.mp_base_url,
        environment_config.mp_state,
        environment_config.mp_city,
    )


@pytest.fixture
def page(browser: Browser, app_config, request) -> Generator[Page, None, None]:
    """Desktop page — maximized when headed; sized viewport when headless."""
    context: BrowserContext = browser.new_context(
        **desktop_context_options(app_config)
    )
    page_instance = context.new_page()
    prepare_desktop_page(page_instance, app_config)
    yield page_instance
    failed = getattr(getattr(request.node, "rep_call", None), "failed", None)
    close_context_with_videos(context, app_config, failed=failed)


@pytest.fixture(scope="session")
def test_data(environment: str) -> Callable[[str], dict]:
    """test_data("move_out") -> dict from config/test_data/move_out.json."""
    return lambda feature: load_test_data(feature, environment)


@pytest.fixture
def hb_login_page(page: Page, environment_config: EnvironmentConfig, app_config) -> HBLoginPage:
    return HBLoginPage(page, environment_config, app_config.getint("browser", "timeout"))


@pytest.fixture
def mobile_page(
    browser: Browser, playwright: Playwright, app_config, request
) -> Generator[Page, None, None]:
    """A phone-viewport MP storefront page, separate from the desktop
    `page` fixture used for HB - lease configuration is set up on the
    desktop page/hb_login_page, then the storefront reservation/rental
    flow itself runs here for mobile-view test cases."""
    device = playwright.devices["iPhone 13"]
    context: BrowserContext = browser.new_context(
        permissions=_browser_permissions(app_config),
        **device,
        **video_recording_options(app_config, size=device["viewport"]),
    )
    page_instance = context.new_page()
    page_instance.set_default_timeout(app_config.getint("browser", "timeout"))
    maybe_start_tracing(context, app_config)
    yield page_instance
    failed = getattr(getattr(request.node, "rep_call", None), "failed", None)
    close_context_with_videos(
        context, app_config, failed=failed, name="mobile-execution-video"
    )


@pytest.fixture
def mp_rental_page(
    browser: Browser, environment_config: EnvironmentConfig, app_config, request
) -> Generator[MPUnitSearchPage, None, None]:
    """A desktop MP storefront page/context, separate from the `page`
    fixture that drives HB admin - MPFMSInitialSetupPage.
    verify_two_step_on_storefront needs to read the real storefront
    and, on a mismatch, drive HB admin again through the same call
    (see its own docstring for why); that only works if the storefront
    check runs on its own page/navigation state rather than sharing
    one with HB admin, the same reasoning behind the `mobile_page`
    fixture's own separate context above."""
    timeout = app_config.getint("browser", "timeout")
    context: BrowserContext = browser.new_context(
        **desktop_context_options(app_config)
    )
    page_instance = context.new_page()
    prepare_desktop_page(page_instance, app_config)
    yield MPUnitSearchPage(page_instance, environment_config.mp_base_url, timeout)
    failed = getattr(getattr(request.node, "rep_call", None), "failed", None)
    close_context_with_videos(
        context, app_config, failed=failed, name="mp-storefront-video"
    )


@pytest.fixture
def mp_guest() -> dict:
    """A fresh guest identity per test, email on a public Mailinator
    inbox so it stays disposable and doesn't collide across parallel
    runs or environments."""
    return _new_mp_guest()


@pytest.fixture
def mp_second_guest() -> dict:
    """A second, independent guest for tests needing two storefront
    tenants (e.g. linking one tenant's space into another's online
    account)."""
    return _new_mp_guest()


def _new_mp_guest() -> dict:
    suffix = uuid.uuid4().hex[:10]
    return {
        "first_name": "Auto",
        "last_name": "Tester",
        "email": f"mp-auto-{suffix}@mailinator.com",
        # 555-0100..0199 is the reserved fictional range - reservations
        # can trigger SMS, so never a possibly-real number. The storefront
        # accepts it (its phone check is an async lookup - see
        # MPLegacyReservationFormPage's phone wait).
        "mobile": f"(714) 555-01{int(suffix[:2], 16) % 100:02d}",
    }


@pytest.fixture
def hb_lead_guest() -> dict:
    """A fresh lead identity per test for HB-side contact creation, same
    reasoning as mp_guest - a unique email per run avoids landing on HB's
    own "similar contacts found" prompt for a previous run's leftover lead
    instead of creating a genuinely new one.

    The phone number is drawn from (707) 555-0100..0199, a range reserved
    for fictional use: Hummingbird texts new contacts (reservation/lease
    confirmations, bulk messages - see test_email_text_multiple_tenants.py),
    and the random 707-719-xxxx numbers used before could belong to real
    people. Only 100 such numbers exist, so unlike the email they can
    repeat across runs."""
    return new_hb_lead_guest()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
    if report.when != "call":
        return

    app_config = load_config()
    attach_mode = app_config.get("browser", "attach_log", fallback="on_failure").strip().lower()
    attach_log = attach_mode in {"always", "true", "1", "yes"} or (
        attach_mode in {"on_failure", "failure", "failed"} and report.failed
    )

    page_instance = item.funcargs.get("page")
    log_path = item.stash.get(_TEST_LOG_PATH, None)
    test_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.name)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    artifact_name = f"{test_name}-{timestamp}"

    summary_lines = [
        f"Test: {item.nodeid}",
        f"Outcome: {report.outcome}",
        f"URL: {page_instance.url if page_instance else '(no page fixture)'}",
        f"Failure: {report.longrepr if report.failed else 'None'}",
    ]
    if log_path is not None:
        summary_lines.append(f"Log file: {log_path}")
        try:
            # Flush file handler so the summary sees the latest lines.
            handler = item.stash.get(_TEST_LOG_HANDLER, None)
            if handler is not None:
                handler.flush()
            logger.info(
                "RESULT %s outcome=%s url=%s",
                item.nodeid,
                report.outcome,
                page_instance.url if page_instance else "",
            )
            if handler is not None:
                handler.flush()
        except Exception:
            pass

    if attach_log:
        body = "\n".join(summary_lines) + "\n"
        if log_path is not None and log_path.exists():
            body += "\n--- captured log ---\n"
            body += log_path.read_text(encoding="utf-8", errors="replace")
        allure.attach(
            body,
            name=f"{item.name}-{report.outcome}-log",
            attachment_type=allure.attachment_type.TEXT,
        )

    if report.failed and page_instance:
        # Prefer Mariposa (mobile_page or a still-on-storefront page). Rental
        # cleanup used to navigate the shared desktop page to HB first, so the
        # generic hook only showed Hummingbird — storefront is captured in
        # mp_rental_cases before cleanup when that happens.
        mobile = item.funcargs.get("mobile_page")
        capture_page = page_instance
        label = "hb-or-desktop"
        try:
            if mobile is not None and "tenant-platform.com" in (mobile.url or ""):
                if "/hummingbird" not in mobile.url and "/dashboard" not in mobile.url:
                    capture_page = mobile
                    label = "mariposa-mobile"
            elif "tenant-platform.com" in (page_instance.url or ""):
                if "/hummingbird" not in page_instance.url and "/dashboard" not in page_instance.url:
                    label = "mariposa-storefront"
                else:
                    label = "hummingbird"
        except Exception:
            pass

        if storefront_failure_was_captured() and label.startswith("hummingbird"):
            allure.attach(
                "Mariposa storefront was already captured at the failure; "
                "skipping HB page as the primary failure screenshot.",
                name="failure-screenshot-note",
                attachment_type=allure.attachment_type.TEXT,
            )
        else:
            screenshot_path = REPORTS_DIR / "screenshots" / f"{artifact_name}.png"
            report_path = REPORTS_DIR / "test-results" / f"{artifact_name}.json"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                capture_page_failure_artifacts(
                    capture_page,
                    label=label,
                    reports_dir=REPORTS_DIR / "screenshots",
                    app_config=app_config,
                )
                # Stable disk path for the JSON summary (viewport-sized).
                capture_page.screenshot(path=str(screenshot_path), full_page=False)
            except Exception as screenshot_error:
                allure.attach(
                    repr(screenshot_error)[:600],
                    name="failure-screenshot-unavailable",
                    attachment_type=allure.attachment_type.TEXT,
                )
            report_path.write_text(
                json.dumps(
                    {
                        "test": item.nodeid,
                        "outcome": report.outcome,
                        "url": getattr(capture_page, "url", None),
                        "failure": str(report.longrepr),
                        "screenshot": str(screenshot_path),
                        "log": str(log_path) if log_path else None,
                        "capture_label": label,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )