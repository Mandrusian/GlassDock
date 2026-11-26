"""Unit tests for the experimental macOS PyObjC backend and X11 starter backend."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _make_fake_cocoa_modules():
    objc = types.ModuleType("objc")

    class _SuperProxy:
        def __init__(self, target):
            self._target = target

        def initWithFrame_(self, frame):
            return self._target

        def updateTrackingAreas(self):
            return None

    objc.super = lambda _cls, self: _SuperProxy(self)

    foundation = types.ModuleType("Foundation")

    class NSObject:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

        def retain(self):
            return self

    class NSTimer:
        @staticmethod
        def scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(*_args):
            return None

    def NSMakeRect(x, y, w, h):
        return types.SimpleNamespace(
            origin=types.SimpleNamespace(x=x, y=y),
            size=types.SimpleNamespace(width=w, height=h),
        )

    foundation.NSObject = NSObject
    foundation.NSTimer = NSTimer
    foundation.NSMakeRect = NSMakeRect
    foundation.NSZeroRect = NSMakeRect(0, 0, 0, 0)

    appkit = types.ModuleType("AppKit")

    class _BaseView(NSObject):
        def initWithFrame_(self, frame):
            self._frame = frame
            return self

        def bounds(self):
            return self._frame

        def setFrame_(self, frame):
            self._frame = frame

        def addTrackingArea_(self, _area):
            return None

        def removeTrackingArea_(self, _area):
            return None

        def setNeedsDisplay_(self, _flag):
            return None

        def convertPoint_fromView_(self, pt, _view):
            return pt

        def addSubview_(self, _view):
            return None

    class _Panel(NSObject):
        def initWithContentRect_styleMask_backing_defer_(self, frame, *_args):
            self._frame = frame
            self._content = _BaseView()
            self.released_when_closed = True
            return self

        def frame(self):
            return self._frame

        def setContentSize_(self, size):
            self._frame.size.width, self._frame.size.height = size

        def setFrameOrigin_(self, origin):
            self._frame.origin.x, self._frame.origin.y = origin

        def setContentView_(self, view):
            self._content = view

        def contentView(self):
            return self._content

        def setReleasedWhenClosed_(self, flag):
            self.released_when_closed = flag

        def center(self):
            return None

        def makeKeyAndOrderFront_(self, _sender):
            return None

        def orderFrontRegardless(self):
            return None

        def __getattr__(self, _name):
            return lambda *_a, **_kw: None

    class _Control(NSObject):
        @classmethod
        def labelWithString_(cls, text):
            obj = cls()
            obj.text = text
            return obj

        def initWithFrame_(self, frame):
            self._frame = frame
            self._val = 0.0
            return self

        def setMinValue_(self, v):
            self._min = v

        def setMaxValue_(self, v):
            self._max = v

        def setDoubleValue_(self, v):
            self._val = v

        def doubleValue(self):
            return self._val

        def setTarget_(self, t):
            self._target = t

        def setAction_(self, a):
            self._action = a

        def setFrame_(self, f):
            self._frame = f

    appkit.NSView = _BaseView
    appkit.NSPanel = _Panel
    appkit.NSTextField = _Control
    appkit.NSSlider = _Control
    appkit.NSApplication = types.SimpleNamespace(sharedApplication=lambda: types.SimpleNamespace(
        setActivationPolicy_=lambda *_: None,
        setDelegate_=lambda *_: None,
        run=lambda: None,
        terminate_=lambda *_: None,
    ))
    appkit.NSApp = types.SimpleNamespace(
        activateIgnoringOtherApps_=lambda *_: None,
        terminate_=lambda *_: None,
    )
    appkit.NSColor = types.SimpleNamespace(
        clearColor=lambda: None,
        colorWithCalibratedRed_green_blue_alpha_=lambda *_a: types.SimpleNamespace(setFill=lambda: None),
    )
    appkit.NSBezierPath = types.SimpleNamespace(
        bezierPathWithRoundedRect_xRadius_yRadius_=lambda *_a: types.SimpleNamespace(fill=lambda: None)
    )
    appkit.NSTrackingArea = types.SimpleNamespace(alloc=lambda: types.SimpleNamespace(
        initWithRect_options_owner_userInfo_=lambda *_a: object()
    ))
    appkit.NSScreen = types.SimpleNamespace(
        mainScreen=lambda: None,
        screens=lambda: [],
    )
    appkit.NSWorkspace = types.SimpleNamespace(
        sharedWorkspace=lambda: types.SimpleNamespace(runningApplications=lambda: [])
    )
    appkit.NSMenu = NSObject
    appkit.NSMenuItem = NSObject
    for const in (
        "NSApplicationActivationPolicyAccessory",
        "NSBackingStoreBuffered",
        "NSFloatingWindowLevel",
        "NSTrackingActiveAlways",
        "NSTrackingInVisibleRect",
        "NSTrackingMouseEnteredAndExited",
        "NSTrackingMouseMoved",
        "NSWindowStyleMaskBorderless",
        "NSWindowStyleMaskClosable",
        "NSWindowStyleMaskTitled",
    ):
        setattr(appkit, const, 1)
    appkit.NSApplicationActivateAllWindows = 1 << 0
    appkit.NSApplicationActivateIgnoringOtherApps = 1 << 1
    appkit.NSCompositingOperationSourceOver = 2
    appkit.NSWindowCollectionBehaviorCanJoinAllSpaces = 1 << 0
    appkit.NSWindowCollectionBehaviorStationary = 1 << 4
    appkit.NSWindowCollectionBehaviorIgnoresCycle = 1 << 6
    return {"objc": objc, "AppKit": appkit, "Foundation": foundation}


class MacOSBackendTests(unittest.TestCase):
    def _load_macos_module(self):
        fake = _make_fake_cocoa_modules()
        spec = importlib.util.spec_from_file_location("glassdock_macos_test", ROOT / "glassdock" / "macos.py")
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, fake):
            spec.loader.exec_module(module)
        return module, fake

    def test_macos_source_compiles_and_avoids_fullscreen_primary_flag(self):
        source = (ROOT / "glassdock" / "macos.py").read_text(encoding="utf-8")
        compile(source, str(ROOT / "glassdock" / "macos.py"), "exec")
        self.assertNotIn("1 << 7", source)
        self.assertIn("setReleasedWhenClosed_(False)", source)
        self.assertIn("applicationShouldTerminateAfterLastWindowClosed_", source)

    def test_hover_index_calculation(self):
        mod, _ = self._load_macos_module()
        self.assertEqual(mod.hover_index_for_x(15, 3, 48, 8), 0)
        self.assertEqual(mod.hover_index_for_x(70, 3, 48, 8), 1)
        self.assertEqual(mod.hover_index_for_x(5, 3, 48, 8), -1)
        self.assertEqual(mod.hover_index_for_x(500, 3, 48, 8), -1)
        self.assertEqual(mod.hover_index_for_x(20, 0, 48, 8), -1)

    def test_settings_window_stays_non_released_and_saves_rounded_int(self):
        mod, _ = self._load_macos_module()
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            mod.APP.config = mod.C.load_config(str(cfg_path))
            mod.APP.settings = None
            mod.APP.panel = _make_fake_cocoa_modules()["AppKit"].NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                mod.NSMakeRect(0, 0, 200, 80)
            )
            mod.APP.view = mod.DockView.alloc().initWithFrame_(mod.NSMakeRect(0, 0, 200, 80))
            mod.APP.openSettings_(None)
            self.assertIsNotNone(mod.APP.settings)
            self.assertFalse(mod.APP.settings.released_when_closed)
            self.assertFalse(mod.APP.applicationShouldTerminateAfterLastWindowClosed_(None))

            icon_slider = next(s for s, k in mod.APP.sliders.items() if k == "size.icon_size")
            icon_slider.setDoubleValue_(63.6)
            with mock.patch.object(mod.C, "config_path", return_value=str(cfg_path)):
                mod.APP.changeSetting_(icon_slider)
            saved = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["size"]["icon_size"], 64)


class X11BackendTests(unittest.TestCase):
    def _load_x11_module(self):
        xlib = types.ModuleType("Xlib")
        xlib.X = types.SimpleNamespace(
            InputOutput=1, CopyFromParent=0, ExposureMask=1, ButtonPressMask=2, StructureNotifyMask=4,
            Expose=12, ButtonPress=4,
        )
        xlib.Xatom = types.SimpleNamespace(CARDINAL=6)
        xlib.display = types.SimpleNamespace(Display=mock.MagicMock())
        spec = importlib.util.spec_from_file_location("glassdock_x11_test", ROOT / "x11-support" / "glassdock-x11.py")
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"Xlib": xlib}):
            spec.loader.exec_module(module)
        return module

    def test_load_config_creates_defaults_and_filters_launchers(self):
        mod = self._load_x11_module()
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "sub" / "config.json"
            cfg = mod.load_config(cfg_path)
            self.assertTrue(cfg_path.is_file())
            self.assertEqual(cfg["edge"], "bottom")
            cfg_path.write_text(json.dumps({
                "edge": "top",
                "launchers": [{"name": "Term", "command": "foot"}, {"name": "", "command": "bad"}],
            }), encoding="utf-8")
            loaded = mod.load_config(cfg_path)
            self.assertEqual(loaded["edge"], "top")
            self.assertEqual(loaded["launchers"], [{"name": "Term", "command": "foot"}])

    def test_draw_uses_background_gc_not_foreground_gc(self):
        mod = self._load_x11_module()
        dock = object.__new__(mod.X11Dock)
        dock.window = mock.MagicMock()
        dock.disp = mock.MagicMock()
        dock.gc = "fg-gc"
        dock.bg_gc = "bg-gc"
        dock.active_gc = "active-gc"
        dock.dock_w = 300
        dock.height = 64
        dock.margin = 12
        dock.tile_w = 88
        dock.gap = 8
        dock.launchers = [{"name": "Term", "command": "xterm"}]
        dock.draw()
        dock.window.fill_rectangle.assert_any_call("bg-gc", 0, 0, 300, 64)
        self.assertNotIn(mock.call("fg-gc", 0, 0, 300, 64), dock.window.fill_rectangle.call_args_list)


if __name__ == "__main__":
    unittest.main()
