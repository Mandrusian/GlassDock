"""Python macOS backend for GlassDock, using PyObjC and the shared config schema."""
import math
import os
import sys
import time

import objc
from AppKit import (
    NSApp, NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
    NSColor, NSImageScaleProportionallyUpOrDown, NSMenu, NSMenuItem, NSPanel,
    NSView, NSVisualEffectView, NSWorkspace, NSScreen, NSFont,
    NSTextField, NSSlider, NSButton, NSWindowStyleMaskBorderless,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
)
from Foundation import NSObject, NSMakeRect, NSTimer

from glassdock.core import config as C


def setting(key):
    return C.get_path(APP.config, key)


class DockView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(DockView, self).initWithFrame_(frame)
        if self is not None:
            self.hover = -1
            self.tracker = None
            self.applications = []
        return self

    def isFlipped(self):
        return True

    def resetTracking(self):
        from AppKit import NSTrackingArea, NSTrackingMouseMoved, NSTrackingActiveAlways, NSTrackingInVisibleRect, NSTrackingMouseEnteredAndExited
        if self.tracker is not None:
            self.removeTrackingArea_(self.tracker)
        self.tracker = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), NSTrackingMouseMoved | NSTrackingMouseEnteredAndExited |
            NSTrackingActiveAlways | NSTrackingInVisibleRect, self, None)
        self.addTrackingArea_(self.tracker)

    def updateTrackingAreas(self):
        objc.super(DockView, self).updateTrackingAreas()
        self.resetTracking()

    def mouseMoved_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        size = float(setting("size.icon_size"))
        spacing = float(setting("size.spacing"))
        idx = int((p.x - 12) // (size + spacing))
        self.hover = idx if 0 <= idx < len(self.applications) else -1
        self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        self.hover = -1
        self.setNeedsDisplay_(True)

    def mouseDown_(self, event):
        self.mouseMoved_(event)
        if 0 <= self.hover < len(self.applications):
            self.applications[self.hover].activateWithOptions_(1)

    def rightMouseDown_(self, event):
        self.mouseMoved_(event)
        menu = NSMenu.alloc().initWithTitle_("GlassDock")
        if 0 <= self.hover < len(self.applications):
            app = self.applications[self.hover]
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Activate " + (app.localizedName() or "Application"), "activateSelected:", "")
            item.setTarget_(APP)
            menu.addItem_(item)
            menu.addItem_(NSMenuItem.separatorItem())
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("GlassDock Settings…", "openSettings:", "")
        item.setTarget_(APP)
        menu.addItem_(item)
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit GlassDock", "quitDock:", "")
        item.setTarget_(APP)
        menu.addItem_(item)
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    def drawRect_(self, rect):
        from AppKit import NSBezierPath
        b = self.bounds()
        bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.11, 0.11, 0.15, float(setting("appearance.bg_opacity")))
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(0, 0, b.size.width, b.size.height), float(setting("appearance.corner_radius")), float(setting("appearance.corner_radius")))
        bg.setFill()
        path.fill()
        size = float(setting("size.icon_size"))
        spacing = float(setting("size.spacing"))
        factor = float(setting("animation.magnify_factor")) if setting("animation.magnify") else 1.0
        for index, app in enumerate(self.applications):
            icon = app.icon()
            if icon is None:
                continue
            offset = size * (factor - 1) / 2 if index == self.hover else 0
            x = 12 + index * (size + spacing)
            frame = NSMakeRect(x - offset, 12 - offset * 2, size + offset * 2, size + offset * 2)
            icon.drawInRect_fromRect_operation_fraction_(frame, NSMakeRect(0, 0, 0, 0), 2, 1.0)


class DockApp(NSObject):
    def applicationDidFinishLaunching_(self, notice):
        self.config = C.load_config()
        self.selected = None
        self.settings = None
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 400, 95), NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered, False)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setLevel_(3)
        self.panel.setCollectionBehavior_(1 << 0 | 1 << 7)
        self.view = DockView.alloc().initWithFrame_(NSMakeRect(0, 0, 400, 95))
        self.panel.setContentView_(self.view)
        self.panel.setAcceptsMouseMovedEvents_(True)
        self.refresh_(None)
        self.panel.orderFrontRegardless()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "refresh:", None, True)

    def refresh_(self, timer):
        if self.settings is None:
            self.config = C.load_config()
        apps = [app for app in NSWorkspace.sharedWorkspace().runningApplications()
                if app.activationPolicy() == 0 and not app.isTerminated()]
        apps.sort(key=lambda a: (a.localizedName() or "").lower())
        old = [a.processIdentifier() for a in self.view.applications]
        new = [a.processIdentifier() for a in apps]
        self.view.applications = apps
        size = float(setting("size.icon_size"))
        spacing = float(setting("size.spacing"))
        width = max(90, min(1800, len(apps) * (size + spacing) + 24))
        height = size + 24 + size * max(0.0, float(setting("animation.magnify_factor")) - 1)
        if old != new or abs(self.panel.frame().size.width - width) > 1 or abs(self.panel.frame().size.height - height) > 1:
            self.panel.setContentSize_((width, height))
            self.view.setFrame_(NSMakeRect(0, 0, width, height))
            screen = NSScreen.mainScreen() or NSScreen.screens()[0]
            visible = screen.visibleFrame()
            self.panel.setFrameOrigin_((visible.origin.x + (visible.size.width-width)/2, visible.origin.y + 12))
            self.view.resetTracking()
        self.view.setNeedsDisplay_(True)

    def activateSelected_(self, sender):
        i = self.view.hover
        if 0 <= i < len(self.view.applications):
            self.view.applications[i].activateWithOptions_(1)

    def openSettings_(self, sender):
        if self.settings is not None:
            self.settings.makeKeyAndOrderFront_(None)
            return
        win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 490, 350), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        win.setTitle_("GlassDock Settings · macOS")
        win.center()
        controls = [
            ("Icon size", "size.icon_size", 24, 128),
            ("Icon spacing", "size.spacing", 0, 32),
            ("Magnification", "animation.magnify_factor", 1.0, 2.0),
            ("Transparency", "appearance.bg_opacity", 0.1, 1.0),
            ("Corner radius", "appearance.corner_radius", 0, 80),
        ]
        self.sliders = {}
        for index, (label, key, minimum, maximum) in enumerate(controls):
            y = 280 - index * 51
            text = NSTextField.labelWithString_(label)
            text.setFrame_(NSMakeRect(22, y, 180, 22))
            win.contentView().addSubview_(text)
            slider = NSSlider.alloc().initWithFrame_(NSMakeRect(198, y, 260, 24))
            slider.setMinValue_(minimum)
            slider.setMaxValue_(maximum)
            slider.setDoubleValue_(float(C.get_path(self.config, key)))
            slider.setTarget_(self)
            slider.setAction_("changeSetting:")
            win.contentView().addSubview_(slider)
            self.sliders[slider] = key
        info = NSTextField.labelWithString_("Right-click dock icons to open Settings or Quit.")
        info.setFrame_(NSMakeRect(22, 20, 440, 24))
        win.contentView().addSubview_(info)
        self.settings = win
        self.settings.retain()
        win.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def changeSetting_(self, sender):
        key = self.sliders[sender]
        C.set_path(self.config, key, int(sender.doubleValue()) if C.SETTINGS[key].type == "int" else float(sender.doubleValue()))
        C.save_config(self.config)
        self.refresh_(None)

    def quitDock_(self, sender):
        NSApp.terminate_(None)


APP = DockApp.alloc().init()


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    app.setDelegate_(APP)
    app.run()


if __name__ == "__main__":
    main()
