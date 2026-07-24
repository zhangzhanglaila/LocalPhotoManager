"""GUI entry point for the iPhoto desktop application."""

from __future__ import annotations

import ctypes
import faulthandler
import logging
import os
import signal
import sys
import threading
from pathlib import Path

faulthandler.enable()
# Periodically dump all thread tracebacks to stderr for debugging hangs.
# This is expensive and should only be enabled when investigating a hang.
if os.environ.get("IPHOTO_FAULT_DUMP_INTERVAL"):
    try:
        interval = int(os.environ["IPHOTO_FAULT_DUMP_INTERVAL"])
    except ValueError:
        interval = 300
    faulthandler.dump_traceback_later(timeout=interval, repeat=True, file=sys.stderr)

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPalette, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from iPhoto.bootstrap.qt_shader_cache import configure_shader_cache_environment
from iPhoto.gui.render_backend import should_configure_global_desktop_opengl
from iPhoto.i18n import tr

_logger = logging.getLogger(__name__)
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_MACOS_EXTERNAL_TOOL_PATHS = (
    Path("/opt/homebrew/bin"),
    Path("/opt/homebrew/sbin"),
    Path("/usr/local/bin"),
    Path("/usr/local/sbin"),
    Path("/opt/local/bin"),
    Path("/opt/local/sbin"),
)


def _bootstrap_macos_external_tool_path() -> None:
    """Expose common Homebrew/MacPorts tool paths to GUI-launched app bundles."""

    if sys.platform != "darwin":
        return

    # Use the target platform's PATH separator rather than the host process
    # separator so darwin-specific normalization also behaves correctly in
    # cross-platform tests that monkeypatch ``sys.platform``.
    path_separator = ":"

    existing_tool_paths: list[str] = []
    for candidate in _MACOS_EXTERNAL_TOOL_PATHS:
        try:
            if candidate.is_dir():
                existing_tool_paths.append(candidate.as_posix())
        except OSError:
            continue

    current_paths = [
        entry
        for entry in os.environ.get("PATH", "").split(path_separator)
        if entry
    ]
    merged_paths: list[str] = []
    seen: set[str] = set()
    for entry in [*existing_tool_paths, *current_paths]:
        if entry in seen:
            continue
        seen.add(entry)
        merged_paths.append(entry)
    if merged_paths:
        os.environ["PATH"] = path_separator.join(merged_paths)


def _configure_qt_shader_disk_cache() -> None:
    """Route shader/program caches into a managed ``.iPhoto`` work directory."""
    configure_shader_cache_environment()


def _opengl_explicitly_disabled() -> bool:
    """Return whether all OpenGL-backed UI surfaces should be disabled."""

    return os.environ.get("IPHOTO_DISABLE_OPENGL", "").strip().lower() in _TRUE_ENV_VALUES


def _map_gl_surface_format(platform: str | None = None) -> QSurfaceFormat:
    """Return the conservative OpenGL surface format used by map widgets."""

    platform = sys.platform if platform is None else platform
    surface_format = QSurfaceFormat()
    surface_format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    surface_format.setAlphaBufferSize(8 if platform == "darwin" else 0)
    surface_format.setSamples(0)
    return surface_format


def _is_packaged_runtime() -> bool:
    """Return ``True`` when the app is running from a compiled/frozen bundle."""

    return "__compiled__" in globals() or getattr(sys, "frozen", False)


def _allow_packaged_linux_wayland() -> bool:
    """Return whether packaged Linux builds may keep Qt's default platform selection."""

    raw_value = os.environ.get("IPHOTO_ALLOW_PACKAGED_LINUX_WAYLAND", "").strip().lower()
    return raw_value in _TRUE_ENV_VALUES


def _prefer_local_source_tree() -> None:
    """Ensure direct script runs import the workspace package first.

    When ``main.py`` is launched directly from an IDE, Python may resolve the
    editable ``iPhoto`` install from another checkout before this repo's
    ``src`` tree. Prepending the local ``src`` path keeps the GUI aligned with
    the code being edited.
    """

    src_root = Path(__file__).resolve().parents[2]
    src_root_str = str(src_root)
    if sys.path and sys.path[0] == src_root_str:
        return
    try:
        sys.path.remove(src_root_str)
    except ValueError:
        pass
    sys.path.insert(0, src_root_str)


def _prepare_qt_runtime_for_maps() -> None:
    """Apply Linux Qt platform flags required by the native OsmAnd widget.

    ``PhotoMapView`` prefers the native OsmAnd widget when its runtime is
    available. That widget expects Qt to use the XCB/GLX desktop OpenGL path on
    Linux; without these flags the application can start successfully and only
    fail later when the map view is opened with GLEW reporting missing GLX
    support.
    """

    if sys.platform != "linux":
        return

    if _opengl_explicitly_disabled():
        return

    if _is_packaged_runtime():
        if _allow_packaged_linux_wayland():
            return
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    else:
        try:
            from maps.map_sources import has_usable_osmand_native_widget, prefer_osmand_native_widget
        except Exception:
            return

        maps_package_root = Path(__file__).resolve().parents[2] / "maps"
        if not prefer_osmand_native_widget() or not has_usable_osmand_native_widget(maps_package_root):
            return

    if not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    if os.environ.get("QT_QPA_PLATFORM") == "xcb":
        os.environ.setdefault("QT_OPENGL", "desktop")
        os.environ.setdefault("QT_XCB_GL_INTEGRATION", "xcb_glx")


def _configure_qt_opengl_defaults() -> None:
    """Apply OpenGL context defaults required by the map widgets."""

    _configure_qt_shader_disk_cache()

    if _opengl_explicitly_disabled():
        return

    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass

    if should_configure_global_desktop_opengl():
        try:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL, True)
        except Exception:
            pass

    try:
        QSurfaceFormat.setDefaultFormat(_map_gl_surface_format())
    except Exception:
        return


def _install_global_exception_hook() -> None:
    """Log unhandled exceptions that would otherwise crash silently.

    PySide6 calls ``sys.excepthook`` when a Python exception propagates out of
    a C++-invoked slot.  Some PySide6 versions then call ``sys.exit(1)``.
    We override the hook so that exceptions are *logged only* and never trigger
    a process exit — the application continues running.
    """

    import traceback

    _hook_logger = logging.getLogger("iPhoto.crash")

    def _excepthook(exc_type, exc_value, exc_tb):
        _hook_logger.critical(
            "Unhandled exception (app continues):\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        # Write to crash log file as well (survives process death).
        # 尝试使用自定义工作目录，回退到用户目录
        from ..utils.pathutils import get_custom_workspace_base
        custom_base = get_custom_workspace_base()
        if custom_base is not None:
            crash_path = custom_base / "crash.log"
        else:
            crash_path = Path.home() / ".iPhoto" / "crash.log"
        try:
            crash_path.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_path, "a", encoding="utf-8") as f:
                f.write("=== Unhandled exception ===\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
                f.write("\n")
        except OSError:
            pass
        # Do NOT call sys.__excepthook__ — some PySide6 versions call
        # sys.exit(1) after excepthook returns.

    sys.excepthook = _excepthook
    # Also replace the internal reference so PySide6's PyErr_Print path
    # uses our hook instead of the default one.
    sys.__excepthook__ = _excepthook

    # Qt swallows exceptions in slots/signals — install a handler via
    # QThreadPool's exception handling or threading.
    import threading
    _orig_thread_excepthook = threading.excepthook

    def _thread_excepthook(args):
        _hook_logger.critical(
            "Unhandled exception in thread %s:\n%s",
            args.thread,
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_tb)),
        )
        # Do NOT call original thread excepthook (which may exit).

    threading.excepthook = _thread_excepthook


def main(argv: list[str] | None = None) -> int:
    """Launch the Qt application and return the exit code."""

    _install_global_exception_hook()
    _prefer_local_source_tree()
    _bootstrap_macos_external_tool_path()
    maps_package_root = Path(__file__).resolve().parents[2] / "maps"
    try:
        from maps.map_sources import apply_pending_osmand_extension_install

        apply_pending_osmand_extension_install(maps_package_root)
    except Exception:
        _logger.warning("Failed to apply pending map extension install", exc_info=True)

    # Ensure the ``iPhoto`` root logger is configured before any component
    # creates a child logger.  ``get_logger()`` lazily attaches a StreamHandler
    # to the ``iPhoto`` logger so all ``iPhoto.*`` loggers propagate output to
    # stderr at INFO level by default.
    from iPhoto.utils.logging import get_logger as _init_logging
    _init_logging()

    arguments = list(sys.argv if argv is None else argv)
    _prepare_qt_runtime_for_maps()
    _configure_qt_opengl_defaults()
    # Suppress noisy Qt RHI/OpenGL debug output (e.g. the full GL extension
    # list printed by NVIDIA drivers) that clutters the terminal on startup.
    # Use explicit assignment (not setdefault) so it always takes effect.
    os.environ["QT_LOGGING_RULES"] = (
        "qt.rhi*=false;qt.gui*=false;"
        "qt.qpa.opengl*=false;qt.opengl*=false"
    )
    app = QApplication(arguments)

    # Allow Ctrl+C to terminate the app on Windows, even when the UI thread
    # is completely frozen in native code.  Python's signal handler cannot run
    # when the main thread is blocked inside Qt, so we register a Windows
    # Console Control Handler (runs in a dedicated OS thread) that directly
    # terminates the process via TerminateProcess.
    if sys.platform == "win32":
        _ctrl_c_event = threading.Event()

        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
        def _console_ctrl_handler(ctrl_type: int) -> int:
            if ctrl_type in (0, 1):  # CTRL_C_EVENT, CTRL_BREAK_EVENT
                _logger.info("Console Ctrl+C detected, force exiting")
                _ctrl_c_event.set()
                return 1
            return 0

        try:
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_ctrl_handler, 1)
        except Exception:
            pass

        def _watchdog() -> None:
            _ctrl_c_event.wait()
            os._exit(130)

        _watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
        _watchdog_thread.start()

    # ``QToolTip`` instances inherit ``WA_TranslucentBackground`` from the frameless
    # main window, which means they expect the application to provide an opaque fill
    # colour.  Some Qt styles ignore stylesheet rules for tooltips, so we proactively
    # update the palette that drives those popups to guarantee readable text.
    tooltip_palette = QPalette(app.palette())

    def _resolved_colour(source: QColor, fallback: QColor) -> QColor:
        """Return a copy of *source* with a fully opaque alpha channel.

        Qt reports transparent colours for certain palette roles when
        ``WA_TranslucentBackground`` is active.  Failing to normalise the alpha value
        causes the compositor to blend the tooltip against the desktop wallpaper,
        producing the solid black rectangle described in the regression report.
        Falling back to a well-tested default keeps the tooltip legible even on
        themes that omit one of the roles we query.
        """

        if not source.isValid():
            return QColor(fallback)

        resolved = QColor(source)
        resolved.setAlpha(255)
        return resolved

    base_colour = _resolved_colour(
        tooltip_palette.color(QPalette.ColorRole.Window), QColor("#eef3f6")
    )
    text_colour = _resolved_colour(
        tooltip_palette.color(QPalette.ColorRole.WindowText), QColor(Qt.GlobalColor.black)
    )

    # Ensure the text remains readable by checking the lightness contrast.  When the
    # palette provides nearly identical shades we fall back to a simple dark-on-light
    # scheme that mirrors Qt's built-in defaults.
    if abs(base_colour.lightness() - text_colour.lightness()) < 40:
        base_colour = QColor("#eef3f6")
        text_colour = QColor(Qt.GlobalColor.black)

    tooltip_palette.setColor(QPalette.ColorRole.ToolTipBase, base_colour)
    tooltip_palette.setColor(QPalette.ColorRole.ToolTipText, text_colour)
    app.setPalette(tooltip_palette, "QToolTip")

    from iPhoto.bootstrap.runtime_context import RuntimeContext
    from iPhoto.gui.coordinators.main_coordinator import MainCoordinator
    from iPhoto.gui.ui.main_window import MainWindow

    # Defer heavy library binding + initial scan until the event loop is running.
    context = RuntimeContext.create(defer_startup=True)
    # --- Phase 4: Coordinator Wiring ---
    window = MainWindow(context)

    # Startup overlay — shown immediately so the user sees progress feedback.
    from iPhoto.gui.ui.widgets.startup_overlay import StartupOverlay
    overlay = StartupOverlay(window.ui.window_shell)

    # Coordinator needs Window, Context, and Container
    overlay.show_overlay()
    window.show()

    # Break the heavy startup into multiple event-loop steps so the overlay
    # can repaint between each step (prevents "未响应" appearance).
    # ``processEvents()`` is called after each ``set_message`` to let the
    # overlay repaint before the next heavy synchronous operation begins.
    coordinator_ref: list = []
    _scan_finished = False  # 跟踪扫描是否完成

    def _step1_create_coordinator() -> None:
        try:
            overlay.set_message(tr("startup.init_components"))
            app.processEvents()
            _logger.info("startup step 1: creating MainCoordinator")
            coordinator = MainCoordinator(window, context)
            window.set_coordinator(coordinator)
            coordinator_ref.append(coordinator)
            QTimer.singleShot(0, _step2_start_coordinator)
        except Exception:
            _logger.exception("startup step 1: unhandled error")
            raise

    def _step2_start_coordinator() -> None:
        try:
            overlay.set_message(tr("startup.starting_services"))
            app.processEvents()
            _logger.info("startup step 2: starting coordinator")
            coordinator_ref[0].start()
            QTimer.singleShot(0, _step2b_check_first_launch)
        except Exception:
            _logger.exception("startup step 2: unhandled error")
            raise

    def _step2b_check_first_launch() -> None:
        """检查是否首次启动，如果是则显示欢迎向导。"""
        try:
            if context.needs_workspace_config():
                overlay.set_message("配置工作目录...")
                app.processEvents()
                _logger.info("startup step 2b: workspace configuration needed, showing welcome wizard")
                # 显示欢迎向导（会阻塞直到用户完成）
                context.show_welcome_wizard()
            QTimer.singleShot(0, _step3a_open_library)
        except Exception:
            _logger.exception("startup step 2b: unhandled error")
            raise

    def _step3a_open_library() -> None:
        try:
            overlay.set_message(tr("startup.opening_library"))
            app.processEvents()
            _logger.info("startup step 3a: opening library")
            context.resume_startup_tasks()
            QTimer.singleShot(0, _step3b_connect_scan_signals)
        except Exception:
            _logger.exception("startup step 3a: unhandled error")
            raise

    def _step3b_connect_scan_signals() -> None:
        """连接扫描进度信号到 overlay。"""
        try:
            overlay.set_message("准备扫描...")
            app.processEvents()
            _logger.info("startup step 3b: connecting scan signals")

            # 连接扫描进度信号
            def _on_scan_progress(root: Path, current: int, total: int) -> None:
                nonlocal _scan_finished
                if not _scan_finished:
                    overlay.show_scan_progress(current, total)
                    app.processEvents()

            def _on_scan_finished(root: Path, success: bool) -> None:
                nonlocal _scan_finished
                _scan_finished = True
                _logger.info("startup: scan finished, success=%s", success)
                # 扫描完成后继续下一步
                QTimer.singleShot(0, _step4_select_photos)

            # 连接信号
            context.facade.scanProgress.connect(_on_scan_progress)
            context.library.scanProgress.connect(_on_scan_progress)
            context.facade.scanFinished.connect(_on_scan_finished)
            context.library.scanFinished.connect(_on_scan_finished)

            # 检查是否已有扫描完成（可能扫描非常快）
            from iPhoto.utils.pathutils import resolve_work_dir
            lib_root = context.library.root()
            if lib_root:
                work_dir = resolve_work_dir(lib_root)
                db_path = (work_dir / "global_index.db") if work_dir is not None else None
                if db_path and db_path.exists():
                    # 数据库已存在，没有扫描
                    _scan_finished = True
                    _logger.info("startup: existing DB found, skipping scan wait")
                    QTimer.singleShot(0, _step4_select_photos)
                else:
                    # 等待扫描完成，设置超时
                    QTimer.singleShot(5000, _check_scan_timeout)
            else:
                # 没有库路径，继续
                _scan_finished = True
                QTimer.singleShot(0, _step4_select_photos)
        except Exception:
            _logger.exception("startup step 3b: unhandled error")
            raise

    def _check_scan_timeout() -> None:
        """检查扫描是否超时（5秒后）。"""
        nonlocal _scan_finished
        if not _scan_finished:
            _logger.warning("startup: scan timeout, continuing anyway")
            _scan_finished = True
            QTimer.singleShot(0, _step4_select_photos)

    def _step4_select_photos() -> None:
        try:
            # 确保扫描已完成后再继续
            if not _scan_finished:
                _logger.info("startup step 4: scan still in progress, waiting...")
                QTimer.singleShot(100, _step4_select_photos)
                return

            overlay.set_message(tr("startup.loading_photos"))
            app.processEvents()
            coordinator = coordinator_ref[0]
            # 检查是否有有效的相册路径参数（排除 --help 等选项）
            valid_path_arg = None
            if len(arguments) > 1:
                arg = arguments[1]
                # 跳过帮助选项和以 - 开头的选项
                if arg not in ("--help", "-h", "--version") and not arg.startswith("-"):
                    potential_path = Path(arg)
                    if potential_path.exists():
                        valid_path_arg = potential_path

            if valid_path_arg:
                _logger.info("startup step 4: opening album from CLI argument %s", valid_path_arg)
                coordinator.open_album_from_path(valid_path_arg)
            else:
                _logger.info("startup step 4: selecting All Photos in sidebar")
                window.ui.sidebar.select_all_photos(emit_signal=True)
            coordinator.finish_startup()
            # 现在安全地关闭 overlay
            overlay.dismiss()
            _logger.info("startup complete")
        except Exception:
            _logger.exception("startup step 4: unhandled error")
            raise

    QTimer.singleShot(0, _step1_create_coordinator)

    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual launch
    raise SystemExit(main())
