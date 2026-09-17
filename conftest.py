import json
import re
import subprocess
import uuid
from collections.abc import Callable, Generator
from datetime import datetime
from pathlib import Path

import allure
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from common_utils.test_data_reader import load_test_data
from common_utils.test_identities import new_hb_lead_guest
from config.config_reader import EnvironmentConfig, load_config, load_environment
from pages.common.hb_login_page import HBLoginPage
from pages.mariposa.mp_unit_search_page import MPUnitSearchPage


PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"
ALLURE_RESULTS_DIR = REPORTS_DIR / "allure-results"
ALLURE_REPORT_DIR = REPORTS_DIR / "allure-report"


def pytest_configure(config: pytest.Config) -> None:
    """Keep Allure output at the project root regardless of launch directory."""
    config.option.allure_report_dir = str(ALLURE_RESULTS_DIR)

    # Default reruns/reruns_delay come from config/environments.ini's
    # [browser] section, so they're editable in one place instead of
    # remembering --reruns/--reruns-delay on every invocation - an
    # explicit --reruns/--reruns-delay on the command line still wins.
    app_config = load_config()
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
    """Regenerates the Allure HTML report after every run - even a
    single test case - so reports/allure-report/<name> is always in
    sync with reports/allure-results without a separate manual `allure
    generate` step. Best-effort: a missing `allure` CLI just skips this
    with a note instead of failing the run."""
    report_dir = ALLURE_REPORT_DIR / _allure_report_name(session.config)
    try:
        subprocess.run(
            [
                "allure",
                "generate",
                str(ALLURE_RESULTS_DIR),
                "-o",
                str(report_dir),
                "--clean",
            ],
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(f"\nAllure report: {report_dir}")
    except FileNotFoundError:
        print("\nSkipped Allure report generation: 'allure' CLI not found on PATH.")
    except subprocess.CalledProcessError as error:
        print(f"\nAllure report generation failed:\n{error.stderr}")
    except subprocess.TimeoutExpired:
        print("\nSkipped Allure report generation: timed out after 60s.")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--env",
        action="store",
        default=None,
        help="MP environment from config/environments.ini, for example: --env uat",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Force every "*_configured" precondition fixture used by this test
    to redo its admin-side HB setup on a pytest-rerunfailures retry
    (item.execution_count > 1 - see pytest_rerunfailures.py's own
    pytest_runtest_protocol) instead of reusing whatever state the
    failed attempt left behind. These are the class-scoped fixtures
    (e.g. test_legacy_reservation.py's _legacy_flow_configured) that
    otherwise only run once per class - rerunfailures itself only clears
    a fixture's cached_result when that fixture raised, so a precondition
    that succeeded but left the server in a state the retried test can't
    pass against would otherwise never re-run. tryfirst=True so this
    clears the cache before the real fixture setup for this attempt
    runs."""
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
def playwright() -> Generator[Playwright, None, None]:
    with sync_playwright() as playwright_instance:
        yield playwright_instance


@pytest.fixture(scope="session")
def browser(playwright: Playwright, app_config) -> Generator[Browser, None, None]:
    browser_name = app_config.get("browser", "name")
    browser_type = getattr(playwright, browser_name)
    headless = app_config.getboolean("browser", "headless")
    browser_instance = browser_type.launch(
        headless=headless,
        slow_mo=app_config.getint("browser", "slow_mo"),
        args=[
            "--start-maximized",
            # --start-maximized only affects a real OS window, which
            # headless Chrome never opens - without it headless falls back
            # to a small default viewport, which flips the app's responsive
            # nav drawer into an overlay that sits on top of the page and
            # intercepts clicks on content beneath it. Force a desktop-size
            # window explicitly so headless renders the same wide, inline
            # layout as headed.
            *(["--window-size=1920,1080"] if headless else []),
            # This window rarely holds real OS focus during an automated
            # run (whoever's watching is usually focused on the terminal/
            # IDE driving it, not the browser itself), and Chrome throttles
            # timers/animations in a window it considers backgrounded -
            # page.bring_to_front() only activates the tab within the
            # browser, it doesn't grant OS-level window focus. That
            # throttling is a plausible cause of Vue-driven view state
            # closing/failing to render mid-interaction under real
            # automation despite behaving reliably when interacted with
            # directly. These flags disable that class of backgrounding
            # throttling outright.
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ],
    )
    yield browser_instance
    browser_instance.close()


def _browser_permissions(app_config) -> list[str]:
    """e.g. "microphone" for the MP storefront's AI chat widget, which
    otherwise triggers a native browser mic-permission prompt on load -
    granting it upfront avoids that prompt appearing at all, rather than
    having every page object dismiss it after the fact."""
    return [
        p.strip()
        for p in app_config.get("browser", "permissions", fallback="").split(",")
        if p.strip()
    ]


@pytest.fixture(scope="session")
def property_landing_page_url(
    browser: Browser, app_config
) -> Callable[[str, str, str], str]:
    """Factory: property_landing_page_url(mp_base_url, state, city) ->
    the MP storefront's exact property landing page URL for that
    state/city, discovered via the same click-through search
    MPUnitSearchPage.search_storage_location() uses and cached per
    (mp_base_url, state, city) for the rest of the session - a plain
    fixed value isn't enough since different test suites target
    different properties (e.g. Legacy's Garden Grove vs Two-Step's
    Rutland, see test_two_step_individual_reservation.py). Mobile
    tests reuse the result (via MPUnitSearchPage.open_property_page)
    instead of repeating that click-through, which has been observed
    intermittently landing on a bare "N Locations found near" search-
    results page instead of the intended property (confirmed live,
    2026-09-08, stage, mobile viewport). Discovery itself runs in a
    throwaway desktop-viewport context, since the click-through has
    only been observed unreliable on mobile, not desktop."""
    timeout = app_config.getint("browser", "timeout")
    cache: dict[tuple[str, str, str], str] = {}

    def discover(mp_base_url: str, state: str, city: str) -> str:
        key = (mp_base_url, state, city)
        if key in cache:
            return cache[key]
        context: BrowserContext = browser.new_context(
            permissions=_browser_permissions(app_config), no_viewport=True
        )
        discovery_page = context.new_page()
        discovery_page.set_default_timeout(timeout)
        try:
            rental_page = MPUnitSearchPage(discovery_page, mp_base_url, timeout)
            rental_page.open_storefront()
            rental_page.search_storage_location(state=state, city=city)
            cache[key] = discovery_page.url
            return cache[key]
        finally:
            context.close()

    return discover


@pytest.fixture
def mp_property_url(
    environment_config: EnvironmentConfig,
    property_landing_page_url: Callable[[str, str, str], str],
) -> str | None:
    """property_landing_page_url resolved against this session's
    default environment_config (config/environments.ini) - covers
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
def page(browser: Browser, app_config) -> Generator[Page, None, None]:
    # No fixed viewport: the page renders at whatever size the actual
    # browser window is - maximized (headed, via --start-maximized) or
    # the explicit --window-size (headless) set on the browser fixture
    # above - rather than a separate, possibly-inconsistent CSS viewport
    # override here.
    context: BrowserContext = browser.new_context(
        permissions=_browser_permissions(app_config),
        no_viewport=True,
    )
    page_instance = context.new_page()
    page_instance.set_default_timeout(app_config.getint("browser", "timeout"))
    yield page_instance
    context.close()


@pytest.fixture(scope="session")
def test_data(environment: str) -> Callable[[str], dict]:
    """test_data("move_out") -> dict from config/test_data/move_out.json."""
    return lambda feature: load_test_data(feature, environment)


@pytest.fixture
def hb_login_page(page: Page, environment_config: EnvironmentConfig, app_config) -> HBLoginPage:
    return HBLoginPage(page, environment_config, app_config.getint("browser", "timeout"))


@pytest.fixture
def mobile_page(
    browser: Browser, playwright: Playwright, app_config
) -> Generator[Page, None, None]:
    """A phone-viewport MP storefront page, separate from the desktop
    `page` fixture used for HB - lease configuration is set up on the
    desktop page/hb_login_page, then the storefront reservation/rental
    flow itself runs here for mobile-view test cases."""
    device = playwright.devices["iPhone 13"]
    context: BrowserContext = browser.new_context(
        permissions=_browser_permissions(app_config), **device
    )
    page_instance = context.new_page()
    page_instance.set_default_timeout(app_config.getint("browser", "timeout"))
    yield page_instance
    context.close()


@pytest.fixture
def mp_rental_page(
    browser: Browser, environment_config: EnvironmentConfig, app_config
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
        permissions=_browser_permissions(app_config), no_viewport=True
    )
    page_instance = context.new_page()
    page_instance.set_default_timeout(timeout)
    yield MPUnitSearchPage(page_instance, environment_config.mp_base_url, timeout)
    context.close()


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
    if report.when == "call":
        page_instance = item.funcargs.get("page")
        if page_instance:
            test_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.name)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            artifact_name = f"{test_name}-{timestamp}"
            log_path = REPORTS_DIR / "logs" / f"{artifact_name}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "Test: "
                f"{item.nodeid}\n"
                f"Outcome: {report.outcome}\n"
                f"URL: {page_instance.url}\n\n"
                f"Failure:\n{report.longrepr if report.failed else 'None'}\n",
                encoding="utf-8",
            )
            allure.attach(
                log_path.read_text(encoding="utf-8"),
                name=f"{item.name}-{report.outcome}-log",
                attachment_type=allure.attachment_type.TEXT,
            )
            if report.failed:
                screenshot_path = REPORTS_DIR / "screenshots" / f"{artifact_name}.png"
                report_path = REPORTS_DIR / "test-results" / f"{artifact_name}.json"
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                page_instance.screenshot(path=str(screenshot_path), full_page=True)
                report_path.write_text(
                    json.dumps(
                        {
                            "test": item.nodeid,
                            "outcome": report.outcome,
                            "url": page_instance.url,
                            "failure": str(report.longrepr),
                            "screenshot": str(screenshot_path),
                            "log": str(log_path),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                allure.attach(
                    screenshot_path.read_bytes(),
                    name=f"{item.name}-failure-screenshot",
                    attachment_type=allure.attachment_type.PNG,
                )
                allure.attach(
                    page_instance.content(),
                    name=f"{item.name}-failure-page-source",
                    attachment_type=allure.attachment_type.HTML,
                )
