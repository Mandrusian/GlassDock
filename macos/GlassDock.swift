import AppKit

final class GlassDockController: NSObject, NSApplicationDelegate {
    private var panel: NSPanel!
    private var stack: NSStackView!
    private var apps = [NSRunningApplication]()
    private var signature = ""
    private let iconSize: CGFloat = 56

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 140, height: 80),
            styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.level = .floating
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        panel.hidesOnDeactivate = false
        let glass = NSVisualEffectView(frame: panel.contentView!.bounds)
        glass.material = .hudWindow
        glass.blendingMode = .behindWindow
        glass.state = .active
        glass.wantsLayer = true
        glass.layer?.cornerRadius = 20
        glass.layer?.masksToBounds = true
        glass.autoresizingMask = [.width, .height]
        panel.contentView?.addSubview(glass)
        stack = NSStackView()
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 9
        glass.addSubview(stack)
        refresh()
        panel.orderFrontRegardless()
        Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in self?.refresh() }
        let nc = NSWorkspace.shared.notificationCenter
        for name in [NSWorkspace.didActivateApplicationNotification,
                     NSWorkspace.didLaunchApplicationNotification,
                     NSWorkspace.didTerminateApplicationNotification] {
            nc.addObserver(self, selector: #selector(workspaceChanged(_:)), name: name, object: nil)
        }
    }

    @objc private func workspaceChanged(_ notification: Notification) { refresh() }

    private func refresh() {
        let found = NSWorkspace.shared.runningApplications.filter {
            $0.activationPolicy == .regular && !$0.isTerminated
        }.sorted { ($0.localizedName ?? "").localizedCaseInsensitiveCompare($1.localizedName ?? "") == .orderedAscending }
        let active = NSWorkspace.shared.frontmostApplication?.processIdentifier ?? -1
        let key = found.map { String($0.processIdentifier) }.joined(separator: "|") + "/\(active)"
        guard key != signature else { return }
        signature = key
        apps = found
        for view in stack.arrangedSubviews { stack.removeArrangedSubview(view); view.removeFromSuperview() }
        for (index, application) in found.enumerated() {
            let button = NSButton(frame: NSRect(x: 0, y: 0, width: iconSize, height: iconSize))
            button.isBordered = false
            button.image = application.icon ?? NSImage(named: NSImage.applicationIconName)
            button.imageScaling = .scaleProportionallyUpOrDown
            button.toolTip = application.localizedName ?? "Application"
            button.tag = index
            button.target = self
            button.action = #selector(activateApp(_:))
            button.translatesAutoresizingMaskIntoConstraints = false
            button.widthAnchor.constraint(equalToConstant: iconSize).isActive = true
            button.heightAnchor.constraint(equalToConstant: iconSize).isActive = true
            stack.addArrangedSubview(button)
        }
        let count = max(found.count, 1)
        let width = CGFloat(count) * iconSize + CGFloat(max(0, count - 1)) * 9 + 24
        panel.setContentSize(NSSize(width: width, height: 80))
        stack.frame = NSRect(x: 12, y: 12, width: width - 24, height: iconSize)
        if let screen = NSScreen.main ?? NSScreen.screens.first {
            let visible = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: visible.midX - width / 2, y: visible.minY + 12))
        }
    }

    @objc private func activateApp(_ sender: NSButton) {
        guard apps.indices.contains(sender.tag) else { return }
        apps[sender.tag].activate(options: [.activateAllWindows])
    }
}

let application = NSApplication.shared
let controller = GlassDockController()
application.delegate = controller
application.run()
