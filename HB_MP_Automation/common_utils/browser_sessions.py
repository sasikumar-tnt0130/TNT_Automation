"""Playwright browser/context helpers for headed and headless parity.

One session Chromium (root conftest). Desktop contexts use the largest
connected display at process start (laptop only, laptop + monitor, or a
larger docked panel) or an optional config override — same size headed
or headless. Optional Playwright video recording attaches to Allure.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import allure

from pages.common.hb_login_page import HBLoginPage

logger = logging.getLogger(__name__)

# Used only when the host display cannot be read (e.g. some CI images).
_FALLBACK_VIEWPORT = {"width": 1920, "height": 1080}
_VIDEOS_DIR = Path(__file__).resolve().parent.parent / "reports" / "videos"
_TRACES_DIR = Path(__file__).resolve().parent.parent / "reports" / "traces"
# Test leaf → video dir registered while recording contexts close; Allure
# attach happens once after every fixture teardown for that test.
_PENDING_VIDEO_DIRS: dict[str, Path] = {}
# Test leaf → [(allure attachment name, webm path), ...] for multi-video tests
# (storefront execution + HB settings + HB validation).
_PENDING_NAMED_VIDEOS: dict[str, list[tuple[str, Path]]] = {}
# Paths already attached during context/page close (settings / validation).
_IMMEDIATE_ATTACHED_VIDEOS: set[Path] = set()
_ATTACHED_VIDEO_LEAFS: set[str] = set()
_PENDING_TRACE_DIRS: dict[str, Path] = {}
_ATTACHED_TRACE_LEAFS: set[str] = set()
_TRACING_CONTEXT_IDS: set[int] = set()
_TRACE_SEQ: dict[str, int] = {}
# Set when a Mariposa/storefront failure was already captured so conftest
# does not overwrite the story with an HB page after cleanup.
_STOREFRONT_FAILURE_CAPTURED = False


def mark_storefront_failure_captured() -> None:
    global _STOREFRONT_FAILURE_CAPTURED
    _STOREFRONT_FAILURE_CAPTURED = True


def storefront_failure_was_captured() -> bool:
    return _STOREFRONT_FAILURE_CAPTURED


def reset_storefront_failure_capture() -> None:
    global _STOREFRONT_FAILURE_CAPTURED
    _STOREFRONT_FAILURE_CAPTURED = False


_FAILURE_SCROLL_SELECTORS = (
    "text=/did not go through/i",
    "text=/Invalid Card/i",
    "text=/error/i",
    ".v-messages__message",
    ".error--text",
    "[role=alert]",
    ".v-snack__content",
    ".toast",
    "button:has-text('Pay Now')",
    "#clickwrap",
)


def scroll_failure_into_view(page) -> str:
    """Scroll the likely error / payment control into the viewport.

    Long rental forms hide the failure below the fold; video/screenshots
    otherwise show only the top of the page.
    """
    for selector in _FAILURE_SCROLL_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            if not locator.is_visible():
                continue
            locator.scroll_into_view_if_needed(timeout=2000)
            return selector
        except Exception:
            continue
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        return "document-bottom"
    except Exception:
        return "none"


def capture_page_failure_artifacts(
    page,
    *,
    label: str = "failure",
    reports_dir: Path | None = None,
    app_config=None,
) -> dict[str, Any]:
    """Scroll to the error, then attach lean failure screenshots.

    Default: viewport PNG only. Full-page PNG / HTML page source are opt-in
    via [browser] attach_full_page_screenshot / attach_page_source — both
    inflate Allure (and --single-file reports) heavily.
    """
    from config.config_reader import load_config

    cfg = app_config or load_config()
    attach_full = cfg.getboolean(
        "browser", "attach_full_page_screenshot", fallback=False
    )
    attach_source = cfg.getboolean("browser", "attach_page_source", fallback=False)

    url = ""
    try:
        url = page.url
    except Exception:
        pass
    scrolled = scroll_failure_into_view(page)
    try:
        # Hold the scrolled frame so the execution video shows the error,
        # not only the top of a long form.
        page.wait_for_timeout(800)
    except Exception:
        pass
    allure.attach(
        f"URL: {url}\nScrolled to: {scrolled}",
        name=f"{label} URL at failure",
        attachment_type=allure.attachment_type.TEXT,
    )
    shots: dict[str, Any] = {"url": url, "scrolled_to": scrolled}
    try:
        viewport_png = page.screenshot(full_page=False)
        allure.attach(
            viewport_png,
            name=f"{label} viewport at failure",
            attachment_type=allure.attachment_type.PNG,
        )
        if reports_dir is not None:
            reports_dir.mkdir(parents=True, exist_ok=True)
            leaf = _test_video_leaf()
            path = reports_dir / f"{leaf}-{label}-viewport.png"
            path.write_bytes(viewport_png)
            shots["path"] = str(path)
        shots["viewport"] = True
    except Exception as exc:
        allure.attach(
            repr(exc)[:600],
            name=f"{label} viewport unavailable",
            attachment_type=allure.attachment_type.TEXT,
        )
    if attach_full:
        try:
            full_png = page.screenshot(full_page=True)
            allure.attach(
                full_png,
                name=f"{label} full page at failure",
                attachment_type=allure.attachment_type.PNG,
            )
            if reports_dir is not None:
                reports_dir.mkdir(parents=True, exist_ok=True)
                leaf = _test_video_leaf()
                path = reports_dir / f"{leaf}-{label}-full.png"
                path.write_bytes(full_png)
                shots["path"] = str(path)
            shots["full_page"] = True
        except Exception as exc:
            allure.attach(
                repr(exc)[:600],
                name=f"{label} full page unavailable",
                attachment_type=allure.attachment_type.TEXT,
            )
    if attach_source:
        try:
            html = page.content()
            # Cap runaway SPA HTML so one failure cannot dominate the report.
            max_chars = cfg.getint("browser", "page_source_max_chars", fallback=200_000)
            if len(html) > max_chars:
                html = html[:max_chars] + f"\n<!-- truncated at {max_chars} chars -->"
            allure.attach(
                html,
                name=f"{label} page source at failure",
                attachment_type=allure.attachment_type.HTML,
            )
        except Exception as exc:
            allure.attach(
                repr(exc)[:600],
                name=f"{label} page source unavailable",
                attachment_type=allure.attachment_type.TEXT,
            )
    return shots


def _windows_monitor_sizes() -> list[tuple[int, int, bool]]:
    """Return (width, height, is_primary) for every attached monitor."""
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    monitors: list[tuple[int, int, bool]] = []

    def _enum(hmonitor, _hdc, _lprect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            width = int(info.rcMonitor.right - info.rcMonitor.left)
            height = int(info.rcMonitor.bottom - info.rcMonitor.top)
            is_primary = bool(info.dwFlags & 1)  # MONITORINFOF_PRIMARY
            if width >= 800 and height >= 600:
                monitors.append((width, height, is_primary))
        return 1

    enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )(_enum)
    user32.EnumDisplayMonitors(None, None, enum_proc, 0)
    return monitors


def _pick_best_size(sizes: list[tuple[int, int, bool]]) -> dict[str, int] | None:
    """Prefer the largest panel (external monitor over laptop when docked)."""
    if not sizes:
        return None
    # Area first; if tied, prefer primary so single-display stays stable.
    width, height, _ = max(sizes, key=lambda item: (item[0] * item[1], item[2]))
    return {"width": width, "height": height}


def _detect_host_display() -> dict[str, int] | None:
    """Best connected display size in CSS pixels, or None if unavailable."""
    if sys.platform == "win32":
        try:
            picked = _pick_best_size(_windows_monitor_sizes())
            if picked:
                return picked
        except Exception:
            pass
        try:
            import ctypes

            user32 = ctypes.windll.user32
            width = int(user32.GetSystemMetrics(0))
            height = int(user32.GetSystemMetrics(1))
            if width >= 800 and height >= 600:
                return {"width": width, "height": height}
        except Exception:
            pass

    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        width = int(root.winfo_screenwidth())
        height = int(root.winfo_screenheight())
        root.destroy()
        if width >= 800 and height >= 600:
            return {"width": width, "height": height}
    except Exception:
        pass

    return None


@lru_cache(maxsize=8)
def desktop_viewport(
    width_override: int | None = None,
    height_override: int | None = None,
) -> dict[str, int]:
    """Resolve desktop viewport once per process.

    Prefer explicit overrides from config; otherwise use the largest
    connected display at session start (so a bigger docked monitor is
    picked automatically); last resort is a known-good CI fallback.
    Re-run pytest after plugging/unplugging a display so size refreshes.
    """
    if width_override and height_override:
        viewport = {"width": int(width_override), "height": int(height_override)}
        logger.info(
            "Desktop viewport from config: %sx%s",
            viewport["width"],
            viewport["height"],
        )
        return viewport

    monitors: list[tuple[int, int, bool]] = []
    if sys.platform == "win32":
        try:
            monitors = _windows_monitor_sizes()
        except Exception:
            monitors = []

    detected = _pick_best_size(monitors) if monitors else _detect_host_display()
    if detected:
        width = int(width_override) if width_override else detected["width"]
        height = int(height_override) if height_override else detected["height"]
        viewport = {"width": width, "height": height}
        if monitors:
            listed = ", ".join(
                f"{w}x{h}{'*' if primary else ''}" for w, h, primary in monitors
            )
            logger.info(
                "Desktop viewport %sx%s (largest of: %s)",
                width,
                height,
                listed,
            )
        else:
            logger.info("Desktop viewport %sx%s (auto-detected)", width, height)
        return viewport

    logger.info(
        "Desktop viewport %sx%s (fallback; no display detected)",
        _FALLBACK_VIEWPORT["width"],
        _FALLBACK_VIEWPORT["height"],
    )
    return dict(_FALLBACK_VIEWPORT)


def _viewport_from_config(app_config) -> dict[str, int]:
    width = app_config.getint("browser", "viewport_width", fallback=0) or None
    height = app_config.getint("browser", "viewport_height", fallback=0) or None
    return desktop_viewport(width, height)


def browser_permissions(app_config) -> list[str]:
    return [
        p.strip()
        for p in app_config.get("browser", "permissions", fallback="").split(",")
        if p.strip()
    ]


def chromium_launch_args(*, headless: bool, app_config=None) -> list[str]:
    """Launch flags shared headed/headless, plus maximize when headed."""
    viewport = (
        _viewport_from_config(app_config)
        if app_config is not None
        else desktop_viewport()
    )
    args = [
        # Avoid Windows DPI / scaling making headed look different from CI.
        "--force-device-scale-factor=1",
        # Chrome throttles timers when the window is occluded or in the
        # background (IDE/terminal focused instead of the browser). That
        # breaks Vue transitions under automation; disable those paths.
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--disable-features=CalculateNativeWinOcclusion",
    ]
    if headless:
        # Headless has no OS maximize; size the backing surface instead.
        args.insert(
            0,
            f"--window-size={viewport['width']},{viewport['height']}",
        )
    else:
        # Real window: maximize on the display Chrome opens on (laptop or
        # docked monitor). Pair with no_viewport in desktop_context_options.
        args.insert(0, "--start-maximized")
    return args


def _test_video_leaf() -> str:
    raw = os.environ.get("HB_MP_CURRENT_TEST") or os.environ.get("PYTEST_CURRENT_TEST") or "session"
    # PYTEST_CURRENT_TEST is "nodeid (call)"; keep the node leaf only.
    raw = raw.split(" ", 1)[0].rsplit("::", 1)[-1]
    return re.sub(r"[^\w.-]+", "_", raw).strip("_")[:80] or "session"


def _video_dir_for_current_test() -> Path:
    """One folder per test name so the run keeps a single execution video."""
    path = _VIDEOS_DIR / _test_video_leaf()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _video_dir_for_kind(kind: str) -> Path:
    """Stable folder for long-lived contexts (module HB settings).

    Not wiped by per-test reset_video_attach_state_for_test, so an open
    module recording is not deleted mid-run. Not nested under the test
    leaf — leaf at module open is often wrong / empty.
    """
    safe = re.sub(r"[^\w.-]+", "_", kind).strip("_")[:40] or "setup"
    path = _VIDEOS_DIR / f"_{safe}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def video_recording_options(
    app_config,
    *,
    size: dict[str, int] | None = None,
    enabled: bool | None = None,
    video_kind: str | None = None,
) -> dict[str, Any]:
    """Playwright new_context kwargs for video, or {} when disabled.

    enabled=None → follow [browser] record_video.
    enabled=False → never record (setup/discovery contexts).
    video_kind → optional subfolder for long-lived setup contexts.
    """
    if enabled is False:
        return {}
    if enabled is None and not app_config.getboolean(
        "browser", "record_video", fallback=False
    ):
        return {}
    if enabled is True and not app_config.getboolean(
        "browser", "record_video", fallback=False
    ):
        # Caller asked to record, but global switch is off.
        return {}
    # Size is required when headed uses no_viewport; otherwise Playwright
    # falls back to 1280x720 which may not match the maximized window.
    resolved = size or _viewport_from_config(app_config)
    video_dir = (
        _video_dir_for_kind(video_kind)
        if video_kind
        else _video_dir_for_current_test()
    )
    return {
        "record_video_dir": str(video_dir),
        "record_video_size": {
            "width": int(resolved["width"]),
            "height": int(resolved["height"]),
        },
    }


def should_attach_video(app_config, *, failed: bool | None) -> bool:
    mode = app_config.get("browser", "attach_video", fallback="always").strip().lower()
    if mode in {"never", "off", "false", "0"}:
        return False
    if mode in {"on_failure", "failure", "failed"}:
        return bool(failed)
    return True  # always


def should_attach_trace(app_config, *, failed: bool | None) -> bool:
    mode = app_config.get("browser", "attach_trace", fallback="on_failure").strip().lower()
    if mode in {"never", "off", "false", "0"}:
        return False
    if mode in {"on_failure", "failure", "failed"}:
        return bool(failed)
    return True  # always


def maybe_start_tracing(context, app_config, *, enabled: bool = True) -> None:
    """Start Playwright tracing on a test context (Allure gets the zip later)."""
    if not enabled:
        return
    if not app_config.getboolean("browser", "record_trace", fallback=True):
        return
    ctx_id = id(context)
    if ctx_id in _TRACING_CONTEXT_IDS:
        return
    try:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        _TRACING_CONTEXT_IDS.add(ctx_id)
        logger.info("Playwright tracing started for %s", _test_video_leaf())
    except Exception as exc:
        logger.debug("Tracing start skipped: %s", exc)


def _stop_tracing_to_dir(context) -> Path | None:
    """Stop tracing into reports/traces/<test>/ and return that folder."""
    ctx_id = id(context)
    if ctx_id not in _TRACING_CONTEXT_IDS:
        return None
    leaf = _test_video_leaf()
    trace_dir = _TRACES_DIR / leaf
    trace_dir.mkdir(parents=True, exist_ok=True)
    seq = _TRACE_SEQ.get(leaf, 0) + 1
    _TRACE_SEQ[leaf] = seq
    path = trace_dir / f"trace-{seq}.zip"
    try:
        context.tracing.stop(path=str(path))
        _TRACING_CONTEXT_IDS.discard(ctx_id)
        if path.exists():
            _PENDING_TRACE_DIRS[leaf] = trace_dir
            return trace_dir
    except Exception as exc:
        _TRACING_CONTEXT_IDS.discard(ctx_id)
        logger.debug("Tracing stop skipped: %s", exc)
    return None


def _primary_webm(video_dir: Path) -> Path | None:
    """Largest .webm in the folder = the main test page, not a short popup."""
    files = [path for path in video_dir.glob("*.webm") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_size)


def _primary_trace(trace_dir: Path) -> Path | None:
    files = [path for path in trace_dir.glob("*.zip") if path.is_file()]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_size)


def _ffmpeg_exe() -> str | None:
    """Prefer imageio-ffmpeg's bundled binary; fall back to PATH."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg")


def _merge_webms(paths: list[Path], out: Path) -> Path | None:
    """Concatenate webms into one file (setup → execution → validation)."""
    usable = [p for p in paths if p.exists() and p.stat().st_size >= 1024]
    if not usable:
        return None
    if len(usable) == 1:
        return usable[0]
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        logger.warning(
            "Cannot merge %s videos into one execution-video — "
            "install imageio-ffmpeg (or ffmpeg on PATH)",
            len(usable),
        )
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Merging %s Allure video clips (setup→execution→validation)...",
        len(usable),
    )
    # 1280p + realtime VP8 keeps teardown from hanging for minutes.
    parts: list[str] = []
    for index, _path in enumerate(usable):
        parts.append(
            f"[{index}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=15[v{index}]"
        )
    concat_in = "".join(f"[v{i}]" for i in range(len(usable)))
    filter_complex = (
        ";".join(parts)
        + f";{concat_in}concat=n={len(usable)}:v=1:a=0[v]"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *[arg for path in usable for arg in ("-i", str(path))],
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-c:v",
        "libvpx",
        "-cpu-used",
        "8",
        "-deadline",
        "realtime",
        "-crf",
        "35",
        "-b:v",
        "0",
        "-an",
        str(out),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0 or not out.exists() or out.stat().st_size < 1024:
            logger.warning(
                "ffmpeg merge failed (rc=%s): %s",
                result.returncode,
                (result.stderr or result.stdout or "")[-800:],
            )
            return None
        logger.info(
            "Merged %s clips → %s (%s bytes)",
            len(usable),
            out.name,
            out.stat().st_size,
        )
        return out
    except Exception as exc:
        logger.warning("ffmpeg merge skipped: %s", exc)
        return None


def _ordered_video_paths(named: list[tuple[str, Path]]) -> list[Path]:
    """Merge order: setup → execution (storefront) → validation → other."""

    def _rank(name: str) -> tuple[int, str]:
        lower = name.lower()
        if "setup" in lower:
            return (0, name)
        if (
            lower.startswith("execution-video")
            or "storefront" in lower
            or lower.startswith("mobile-execution")
            or lower.startswith("mp-storefront")
        ):
            return (1, name)
        if "validation" in lower:
            return (2, name)
        if "hb" in lower or "settings" in lower:
            return (3, name)
        return (4, name)

    ordered: list[Path] = []
    seen: set[Path] = set()
    for _name, path in sorted(named, key=lambda item: _rank(item[0])):
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(path)
    return ordered


def _defer_hb_clip_for_merge(app_config, name: str) -> bool:
    """Queue-only HB clips so teardown can merge setup|execution|validation."""
    if not app_config.getboolean("browser", "record_setup_video", fallback=False):
        return False
    lower = name.lower()
    return (
        lower.startswith("hb-")
        or "setup" in lower
        or "validation" in lower
        or "settings" in lower
    )


def _queue_named_video(leaf: str, name: str, path: Path | None) -> None:
    """Register a finalized .webm for Allure attach (skip empty/blank files)."""
    if path is None:
        return
    try:
        if not path.exists() or path.stat().st_size < 1024:
            logger.warning(
                "Skipping blank/empty video %s (%s bytes)",
                name,
                path.stat().st_size if path.exists() else 0,
            )
            return
    except OSError:
        return
    _PENDING_NAMED_VIDEOS.setdefault(leaf, []).append((name, path))
    _PENDING_VIDEO_DIRS[leaf] = path.parent


def _attach_webm_file(name: str, path: Path) -> bool:
    """Attach one webm to the current Allure test; return True if attached."""
    try:
        if not path.exists() or path.stat().st_size < 1024:
            logger.warning(
                "Skipping blank Allure video %s (%s bytes)",
                name,
                path.stat().st_size if path.exists() else 0,
            )
            return False
        allure.attach.file(
            str(path),
            name=name,
            attachment_type=allure.attachment_type.WEBM,
            extension="webm",
        )
        logger.info(
            "Allure attached %s (%s bytes) for %s",
            name,
            path.stat().st_size,
            _test_video_leaf(),
        )
        return True
    except Exception as exc:
        logger.debug("Allure video attach skipped for %s: %s", name, exc)
        return False


def close_page_with_video(
    page, app_config, *, name: str, attach_now: bool | None = None
) -> None:
    """Close one page and queue/attach its recording under ``name``.

    HB setup clips default to queue-only when ``record_setup_video`` is on
    so teardown can merge them into a single ``execution-video``.
    """
    if page is None:
        return
    leaf = _test_video_leaf()
    path: Path | None = None
    try:
        if page.video is not None:
            path = Path(page.video.path())
    except Exception:
        path = None
    try:
        page.close()
    except Exception as exc:
        logger.debug("page close skipped: %s", exc)
        return
    _queue_named_video(leaf, name, path)
    if attach_now is None:
        attach_now = not _defer_hb_clip_for_merge(app_config, name)
    if (
        attach_now
        and path is not None
        and should_attach_video(app_config, failed=None)
    ):
        if _attach_webm_file(name, path):
            _IMMEDIATE_ATTACHED_VIDEOS.add(path)


def finalize_hb_admin_session_video_for_test(
    hb_login_page: HBLoginPage,
    app_config,
    *,
    name: str = "execution-video",
) -> None:
    """Close the shared tab to finalize this test's execution-video.

    Does **not** reopen HB afterward — that short “launch dashboard” clip was
    being attached as a second video. The next test (or next HB use) calls
    ``ensure_hb_admin_page_ready`` to open a fresh tab when needed.
    """
    if not app_config.getboolean("browser", "record_video", fallback=False):
        return
    page = getattr(hb_login_page, "page", None)
    if page is None or page.is_closed():
        return
    try:
        if page.video is None:
            return
    except Exception:
        return
    if getattr(hb_login_page, "browser_context", None) is None:
        try:
            hb_login_page.browser_context = page.context
        except Exception:
            pass
    close_page_with_video(page, app_config, name=name, attach_now=False)


def ensure_hb_admin_page_ready(
    hb_login_page: HBLoginPage, app_config
) -> None:
    """Reopen the shared HB tab if the previous test closed it for video."""
    page = getattr(hb_login_page, "page", None)
    if page is not None and not page.is_closed():
        return
    context = getattr(hb_login_page, "browser_context", None)
    if context is None:
        return
    try:
        new_page = context.new_page()
        prepare_desktop_page(new_page, app_config, record_artifacts=False)
        hb_login_page.rebind_page(new_page)
        base = hb_login_page.base_url.rstrip("/").removesuffix("/login")
        new_page.goto(f"{base}/dashboard", wait_until="domcontentloaded")
        hb_login_page.ensure_logged_in()
    except Exception as exc:
        logger.warning("HB admin page re-open failed: %s", exc)


def close_context_with_videos(
    context,
    app_config,
    *,
    failed: bool | None = None,
    name: str = "execution-video",
) -> None:
    """Close context; queue named video(s) + trace for Allure attach later.

    Storefront ``execution-video`` is deferred to teardown. HB setup /
    validation clips are also deferred when ``record_setup_video`` is on
    so they merge into one Allure attachment (setup → execution →
    validation).
    """
    if context is None:
        return
    _stop_tracing_to_dir(context)
    leaf = _test_video_leaf()
    paths: list[Path] = []
    for page in list(context.pages):
        if page.video is None:
            continue
        try:
            paths.append(Path(page.video.path()))
        except Exception:
            pass
    if not paths:
        _PENDING_VIDEO_DIRS.setdefault(leaf, _video_dir_for_current_test())
    context.close()
    defer_hb = _defer_hb_clip_for_merge(app_config, name)
    for index, path in enumerate(paths):
        attach_name = name if index == 0 else f"{name}-{index + 1}"
        _queue_named_video(leaf, attach_name, path)
        if (
            attach_name != "execution-video"
            and not defer_hb
            and should_attach_video(app_config, failed=failed)
        ):
            if _attach_webm_file(attach_name, path):
                _IMMEDIATE_ATTACHED_VIDEOS.add(path)


def attach_execution_video_for_test(
    app_config,
    *,
    failed: bool | None = None,
    test_name: str | None = None,
) -> None:
    """Attach queued execution video(s) to Allure (idempotent).

    Desktop rentals use one shared tab (setup → storefront → validation),
    so a single clip is enough — no ffmpeg merge.
    """
    raw = test_name or os.environ.get("HB_MP_CURRENT_TEST") or ""
    leaf = re.sub(r"[^\w.-]+", "_", raw).strip("_")[:80] if raw else _test_video_leaf()
    if not leaf:
        leaf = _test_video_leaf()
    if leaf in _ATTACHED_VIDEO_LEAFS:
        return
    _ATTACHED_VIDEO_LEAFS.add(leaf)
    video_dir = _PENDING_VIDEO_DIRS.pop(leaf, None) or (_VIDEOS_DIR / leaf)
    named = list(_PENDING_NAMED_VIDEOS.pop(leaf, []))
    if should_attach_video(app_config, failed=failed):
        if not named:
            primary = _primary_webm(video_dir)
            if primary is not None:
                named = [("execution-video", primary)]
        # Prefer a single execution-video when several were queued (e.g. a
        # leftover name); do not ffmpeg-merge — shared-tab flow records one.
        execution = [
            (name, path)
            for name, path in named
            if name == "execution-video" or name.startswith("execution-video")
        ]
        to_attach = execution or named
        seen: set[Path] = set()
        for attach_name, path in to_attach:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen or path in _IMMEDIATE_ATTACHED_VIDEOS:
                continue
            seen.add(resolved)
            _attach_webm_file(attach_name, path)
    elif app_config.getboolean("browser", "record_video", fallback=False):
        for _, path in named:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        primary = _primary_webm(video_dir)
        if primary is not None:
            try:
                primary.unlink(missing_ok=True)
            except OSError:
                pass


def attach_execution_trace_for_test(
    app_config,
    *,
    failed: bool | None = None,
    test_name: str | None = None,
) -> None:
    """Attach one playwright-trace.zip to Allure (idempotent).

    Open locally with: ``npx playwright show-trace path/to/trace.zip``
    or https://trace.playwright.dev
    """
    raw = test_name or os.environ.get("HB_MP_CURRENT_TEST") or ""
    leaf = re.sub(r"[^\w.-]+", "_", raw).strip("_")[:80] if raw else _test_video_leaf()
    if not leaf:
        leaf = _test_video_leaf()
    if leaf in _ATTACHED_TRACE_LEAFS:
        return
    trace_dir = _PENDING_TRACE_DIRS.pop(leaf, None) or (_TRACES_DIR / leaf)
    primary = _primary_trace(trace_dir)
    if primary is None:
        return
    for path in trace_dir.glob("*.zip"):
        if path == primary:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    _ATTACHED_TRACE_LEAFS.add(leaf)
    if should_attach_trace(app_config, failed=failed):
        allure.attach.file(
            str(primary),
            name="playwright-trace",
            extension="zip",
        )
        allure.attach(
            "Download playwright-trace.zip from this test, then open with:\n"
            f"  npx playwright show-trace \"{primary}\"\n"
            "or drag the zip onto https://trace.playwright.dev",
            name="playwright-trace-how-to",
            attachment_type=allure.attachment_type.TEXT,
        )
        logger.info(
            "Allure attached playwright-trace (%s bytes) for %s",
            primary.stat().st_size,
            leaf,
        )
    elif app_config.getboolean("browser", "record_trace", fallback=True):
        try:
            primary.unlink(missing_ok=True)
        except OSError:
            pass


def reset_video_attach_state_for_test(test_name: str | None = None) -> None:
    """Clear per-test video/trace attach guards and leftovers at test start."""
    reset_storefront_failure_capture()
    raw = test_name or os.environ.get("HB_MP_CURRENT_TEST") or ""
    leaf = re.sub(r"[^\w.-]+", "_", raw).strip("_")[:80] if raw else _test_video_leaf()
    _ATTACHED_VIDEO_LEAFS.discard(leaf)
    _PENDING_VIDEO_DIRS.pop(leaf, None)
    _PENDING_NAMED_VIDEOS.pop(leaf, None)
    _IMMEDIATE_ATTACHED_VIDEOS.clear()
    _ATTACHED_TRACE_LEAFS.discard(leaf)
    _PENDING_TRACE_DIRS.pop(leaf, None)
    _TRACE_SEQ.pop(leaf, None)
    for base in (_VIDEOS_DIR / leaf, _TRACES_DIR / leaf):
        if base.exists():
            for leftover in list(base.glob("*.webm")) + list(base.glob("*.zip")):
                try:
                    leftover.unlink()
                except OSError:
                    pass
        base.mkdir(parents=True, exist_ok=True)


def _will_record_video(app_config, record_video: bool | None) -> bool:
    if not app_config.getboolean("browser", "record_video", fallback=False):
        return False
    if record_video is True or record_video is None:
        return True
    return app_config.getboolean("browser", "record_setup_video", fallback=False)


def desktop_context_options(
    app_config, *, record_video: bool | None = None, video_kind: str | None = None
) -> dict[str, Any]:
    """kwargs for browser.new_context(...) — desktop HB/storefront pages.

    Headed: no_viewport + --start-maximized / ensure_window_maximized so the
    OS window fills the display (desktop view, not a small fixed box).
    Video still records via record_video_size (explicit size) — do not pin
    context viewport just because recording is on (that shrank the window).

    Headless: explicit viewport from the largest connected display.
    record_video=None → follow [browser] record_video.
    record_video=False → still record when record_setup_video=true.
    """
    opts: dict[str, Any] = {"permissions": browser_permissions(app_config)}
    width = app_config.getint("browser", "viewport_width", fallback=0) or None
    height = app_config.getint("browser", "viewport_height", fallback=0) or None
    headless = app_config.getboolean("browser", "headless")

    if width and height:
        opts["viewport"] = desktop_viewport(width, height)
    elif headless:
        opts["viewport"] = _viewport_from_config(app_config)
    else:
        # Maximized real window; page size follows the OS chrome.
        opts["no_viewport"] = True

    if record_video is None:
        opts.update(video_recording_options(app_config, video_kind=video_kind))
    elif record_video:
        opts.update(
            video_recording_options(
                app_config, enabled=True, video_kind=video_kind
            )
        )
    else:
        setup_ok = app_config.getboolean(
            "browser", "record_setup_video", fallback=False
        )
        if setup_ok:
            opts.update(
                video_recording_options(
                    app_config,
                    enabled=True,
                    video_kind=video_kind or "hb-settings",
                )
            )
    return opts


def ensure_window_maximized(page) -> None:
    """Maximize the real Chrome window after new_page (headed only)."""
    session = None
    try:
        session = page.context.new_cdp_session(page)
        target = session.send("Browser.getWindowForTarget")
        window_id = target.get("windowId")
        if window_id is None:
            return
        session.send(
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"windowState": "maximized"}},
        )
        # Some hosts leave a small restored box after setWindowBounds;
        # re-assert maximized once the first paint settles.
        page.wait_for_timeout(200)
        session.send(
            "Browser.setWindowBounds",
            {"windowId": window_id, "bounds": {"windowState": "maximized"}},
        )
    except Exception as exc:
        logger.debug("Window maximize skipped: %s", exc)
    finally:
        # Detach or browser.close() can hang on Windows after many
        # maximize calls (HB setup/validation page slices).
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass


def prepare_desktop_page(
    page, app_config, *, record_artifacts: bool = True
) -> None:
    """Apply desktop defaults after context.new_page().

    record_artifacts=True (test page/mobile): start Playwright tracing when
    [browser] record_trace is on. Setup contexts pass False.
    """
    page.set_default_timeout(app_config.getint("browser", "timeout"))
    if not app_config.getboolean("browser", "headless"):
        ensure_window_maximized(page)
    maybe_start_tracing(page.context, app_config, enabled=record_artifacts)


def create_hb_admin_session(
    browser,
    environment_config,
    app_config,
    *,
    record_video: bool | None = False,
    video_kind: str | None = "hb-settings",
) -> tuple[Any, HBLoginPage]:
    """Open a Chromium context and log into HB admin once.

    Caller owns teardown (``close_context_with_videos``). Prefer the
    module-scoped ``hb_admin_session`` fixture for MP admin configure;
    use ``hb_admin_context`` when open→yield→close in one block is enough.

    ``record_video=None`` follows ``[browser] record_video`` (shared-tab
    rentals). ``record_video=False`` still records when
    ``record_setup_video`` is true. ``video_kind`` isolates long-lived
    module recordings from per-test wipe.
    """
    timeout = app_config.getint("browser", "timeout")
    kind = video_kind
    if record_video is True:
        # Per-test clip — live in the test video folder.
        kind = None
    elif record_video is None:
        # Shared-tab rentals: stable folder (not wiped by per-test reset).
        kind = "shared-rental"
    context = browser.new_context(
        **desktop_context_options(
            app_config, record_video=record_video, video_kind=kind
        )
    )
    page = context.new_page()
    prepare_desktop_page(page, app_config, record_artifacts=True)
    hb_login_page = HBLoginPage(page, environment_config, timeout)
    hb_login_page.ensure_logged_in()
    return context, hb_login_page


@contextmanager
def hb_admin_context(
    browser,
    environment_config,
    app_config,
    *,
    video_name: str = "hb-admin-setup-video",
    record_video: bool | None = False,
) -> Iterator[HBLoginPage]:
    """One temporary Chromium context, logged into HB admin.

    Use for one-off open→yield→close callers. Module/class MP admin
    configure should use the ``hb_admin_session`` fixture instead so the
    same window is reused for APW, signing, and layout restore.
    Video/trace follow record_setup_video unless record_video is forced.
    """
    context, hb_login_page = create_hb_admin_session(
        browser, environment_config, app_config, record_video=record_video
    )
    try:
        yield hb_login_page
    finally:
        close_context_with_videos(context, app_config, name=video_name)
