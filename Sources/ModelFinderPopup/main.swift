import AppKit
import AVFoundation
import QuartzCore
import Darwin

private let canvasSize = NSSize(width: 580, height: 351)
private let defaultIdleSeconds: TimeInterval = 90
private let defaultConfirmationMinimum: TimeInterval = 0.8
private let defaultConfirmationMaximum: TimeInterval = 4.4

private struct RuntimeDocument: Decodable {
    struct Target: Decodable {
        let modelID: String
        let displayName: String
    }

    struct Member: Decodable {
        let name: String
        let role: String
        let avatarPath: String
        let avatarSource: String
        let portraitZoom: Double?
        let isLocal: Bool?
    }

    struct Popup: Decodable {
        struct Sounds: Decodable {
            let ready: String?
            let enter: String?
            let confirm: String?
        }

        struct Theme: Decodable {
            let frame: String
            let roleTank: String
            let roleHealer: String
            let roleDPS: String
            let cursor: String
            let cursorActive: String
        }

        let destinationURL: String
        let idleSeconds: Double?
        let confirmationMinSeconds: Double?
        let confirmationMaxSeconds: Double?
        let destinationLabel: String
        let sounds: Sounds
        let theme: Theme
    }

    let target: Target
    let members: [Member]
    let popup: Popup
}

private enum PartyRole: String {
    case tank = "TANK"
    case healer = "HEALER"
    case dps = "DPS"

    var accessibilityName: String {
        switch self {
        case .tank: return "tank"
        case .healer: return "healer"
        case .dps: return "damage"
        }
    }
}

private struct PartyMember {
    let name: String
    let role: PartyRole
    let image: NSImage
    let roleIcon: NSImage
    let portraitZoom: CGFloat
}

private struct PopupCopy {
    let modelID: String
    let modelName: String
    let destinationLabel: String

    var readyTitle: String { "Your \(modelName) group is ready!" }
    var waitingTitle: String { "Waiting for your \(modelName) group…" }
    var enterLabel: String { "ENTER \(modelName.uppercased())" }
    var openingLabel: String { "OPENING \(destinationLabel.uppercased())" }
}

private struct LoadedRuntime {
    let members: [PartyMember]
    let localMemberIndex: Int
    let frameSkin: NSImage
    let cursorImage: NSImage
    let cursorActiveImage: NSImage
    let readySound: Data?
    let enterSound: Data?
    let confirmSound: Data?
    let destination: URL
    let idleSeconds: TimeInterval
    let confirmationMinimum: TimeInterval
    let confirmationMaximum: TimeInterval
    let copy: PopupCopy
}

private struct RuntimeValidationError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

private enum PartyPhase {
    case ready
    case waiting
    case confirmed
    case openFailed
}

private final class PopupPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

private final class AccessibilityActionElement: NSAccessibilityElement {
    var action: (() -> Void)?

    override func accessibilityPerformPress() -> Bool {
        guard let action else { return false }
        action()
        return true
    }
}

private func fittedFont(_ text: String, in width: CGFloat, font initialFont: NSFont, minimum: CGFloat?) -> NSFont {
    guard let minimum else { return initialFont }
    var font = initialFont
    var pointSize = initialFont.pointSize
    while pointSize > minimum && (text as NSString).size(withAttributes: [.font: font]).width > width - 4 {
        pointSize = max(minimum, pointSize - 0.5)
        font = NSFontManager.shared.convert(initialFont, toSize: pointSize)
    }
    return font
}

private func drawCenteredText(
    _ text: String,
    in rect: NSRect,
    font initialFont: NSFont,
    minimumFontSize: CGFloat? = nil,
    color: NSColor,
    shadow: Bool = false
) {
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    paragraph.lineBreakMode = .byTruncatingTail
    let font = fittedFont(text, in: rect.width, font: initialFont, minimum: minimumFontSize)
    var attributes: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: color,
        .paragraphStyle: paragraph
    ]
    if shadow {
        let textShadow = NSShadow()
        textShadow.shadowColor = NSColor.black.withAlphaComponent(0.95)
        textShadow.shadowBlurRadius = 2
        textShadow.shadowOffset = NSSize(width: 1, height: -1)
        attributes[.shadow] = textShadow
    }
    let measured = (text as NSString).boundingRect(
        with: NSSize(width: rect.width, height: 1_000),
        options: [.usesLineFragmentOrigin, .usesFontLeading],
        attributes: attributes
    )
    let target = NSRect(x: rect.minX, y: rect.midY - measured.height / 2, width: rect.width, height: measured.height + 2)
    (text as NSString).draw(in: target, withAttributes: attributes)
}

private final class ModelFinderPartyView: NSView {
    let members: [PartyMember]
    let copy: PopupCopy
    let frameSkin: NSImage
    let cursorImage: NSImage
    let cursorActiveImage: NSImage
    let finderCursor: NSCursor
    let finderActiveCursor: NSCursor
    var phase: PartyPhase = .ready {
        didSet {
            needsDisplay = true
            window?.invalidateCursorRects(for: self)
        }
    }
    var confirmed: Set<Int> = [] { didSet { needsDisplay = true } }
    var onEnter: (() -> Void)?
    var onLeave: (() -> Void)?
    var onOpenDestination: (() -> Void)?

    private var hoverEnter = false
    private var hoverLeave = false
    private var hoverClose = false
    private var keyboardFocus = 0
    private var tracking: NSTrackingArea?
    var demoCursorPoint: NSPoint?
    var demoClickRing = false
    var demoButtonPressed = false
    var demoLeaveHovered = false

    private lazy var primaryAccessibilityButton: AccessibilityActionElement = {
        let element = AccessibilityActionElement()
        element.setAccessibilityRole(.button)
        element.setAccessibilityParent(self)
        element.action = { [weak self] in
            guard let self, self.phase == .ready else { return }
            self.onEnter?()
        }
        return element
    }()

    private lazy var secondaryAccessibilityButton: AccessibilityActionElement = {
        let element = AccessibilityActionElement()
        element.setAccessibilityRole(.button)
        element.setAccessibilityParent(self)
        element.action = { [weak self] in
            guard let self else { return }
            if self.phase == .ready {
                self.onLeave?()
            } else if self.phase == .openFailed {
                self.onOpenDestination?()
            }
        }
        return element
    }()

    init(
        frame frameRect: NSRect,
        members: [PartyMember],
        copy: PopupCopy,
        frameSkin: NSImage,
        cursorImage: NSImage,
        cursorActiveImage: NSImage
    ) {
        self.members = members
        self.copy = copy
        self.frameSkin = frameSkin
        self.cursorImage = cursorImage
        self.cursorActiveImage = cursorActiveImage
        finderCursor = NSCursor(image: cursorImage, hotSpot: NSPoint(x: 1, y: 1))
        finderActiveCursor = NSCursor(image: cursorActiveImage, hotSpot: NSPoint(x: 1, y: 1))
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = true
        setAccessibilityElement(true)
        setAccessibilityRole(.group)
        setAccessibilityLabel("\(copy.modelName) Model Finder")
        let roster = members.map { "\($0.name.capitalized) \($0.role.accessibilityName)" }.joined(separator: ", ")
        setAccessibilityHelp("Party roster: \(roster).")
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override var acceptsFirstResponder: Bool { true }
    override var mouseDownCanMoveWindow: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func accessibilityChildren() -> [Any]? {
        primaryAccessibilityButton.setAccessibilityLabel(phase == .ready ? copy.enterLabel.capitalized : "Party ready")
        primaryAccessibilityButton.setAccessibilityEnabled(phase == .ready)
        secondaryAccessibilityButton.setAccessibilityLabel(phase == .openFailed ? "Open \(copy.destinationLabel)" : "Leave queue")
        secondaryAccessibilityButton.setAccessibilityEnabled(phase == .ready || phase == .openFailed)
        if let window {
            primaryAccessibilityButton.setAccessibilityFrame(window.convertToScreen(convert(enterRect, to: nil)))
            secondaryAccessibilityButton.setAccessibilityFrame(window.convertToScreen(convert(leaveRect, to: nil)))
        }
        setAccessibilityValue(phase == .ready ? "Five players found" : "\(confirmed.count) of \(members.count) players confirmed")
        return [primaryAccessibilityButton, secondaryAccessibilityButton]
    }

    private var enterRect: NSRect { NSRect(x: 58, y: 37, width: 215, height: 41) }
    private var leaveRect: NSRect { NSRect(x: 305, y: 37, width: 218, height: 41) }
    private var closeRect: NSRect { NSRect(x: 526, y: 299, width: 40, height: 42) }

    override func updateTrackingAreas() {
        if let tracking { removeTrackingArea(tracking) }
        let area = NSTrackingArea(
            rect: bounds,
            options: [.activeAlways, .mouseMoved, .mouseEnteredAndExited],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
        tracking = area
        super.updateTrackingAreas()
    }

    override func resetCursorRects() {
        super.resetCursorRects()
        addCursorRect(bounds.intersection(visibleRect), cursor: finderCursor)
        addCursorRect(closeRect, cursor: finderActiveCursor)
        if phase == .ready {
            addCursorRect(enterRect, cursor: finderActiveCursor)
            addCursorRect(leaveRect, cursor: finderActiveCursor)
        } else if phase == .openFailed {
            addCursorRect(leaveRect, cursor: finderActiveCursor)
        }
    }

    override func mouseMoved(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let nextEnter = phase == .ready && enterRect.contains(point)
        let nextLeave = (phase == .ready || phase == .openFailed) && leaveRect.contains(point)
        let nextClose = closeRect.contains(point)
        if nextEnter != hoverEnter || nextLeave != hoverLeave || nextClose != hoverClose {
            hoverEnter = nextEnter
            hoverLeave = nextLeave
            hoverClose = nextClose
            needsDisplay = true
        }
    }

    override func mouseExited(with event: NSEvent) {
        hoverEnter = false
        hoverLeave = false
        hoverClose = false
        needsDisplay = true
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        window?.makeFirstResponder(self)
        if closeRect.contains(point) {
            onLeave?()
        } else if phase == .ready && enterRect.contains(point) {
            keyboardFocus = 0
            onEnter?()
        } else if phase == .ready && leaveRect.contains(point) {
            keyboardFocus = 1
            onLeave?()
        } else if phase == .openFailed && leaveRect.contains(point) {
            keyboardFocus = 1
            onOpenDestination?()
        } else {
            window?.performDrag(with: event)
        }
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {
            onLeave?()
        } else if event.keyCode == 48 {
            if phase == .ready {
                keyboardFocus = keyboardFocus == 0 ? 1 : 0
                needsDisplay = true
            } else if phase == .openFailed {
                keyboardFocus = 1
                needsDisplay = true
            }
        } else if event.keyCode == 36 || event.keyCode == 49 {
            if phase == .ready && keyboardFocus == 0 {
                onEnter?()
            } else if phase == .ready && keyboardFocus == 1 {
                onLeave?()
            } else if phase == .openFailed && keyboardFocus == 1 {
                onOpenDestination?()
            } else {
                super.keyDown(with: event)
            }
        } else {
            super.keyDown(with: event)
        }
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        NSGraphicsContext.saveGraphicsState()
        frameSkin.draw(in: bounds, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])

        if hoverClose {
            let glow = NSBezierPath(roundedRect: closeRect.insetBy(dx: 2, dy: 2), xRadius: 4, yRadius: 4)
            NSColor(calibratedRed: 1, green: 0.72, blue: 0.18, alpha: 0.22).setFill()
            glow.fill()
        }

        let title: String
        let subtitle: String
        switch phase {
        case .ready:
            title = copy.readyTitle
            subtitle = "MODEL FINDER  •  5 PLAYERS FOUND"
        case .waiting:
            title = copy.waitingTitle
            subtitle = "PARTY CONFIRMATION  •  \(confirmed.count)/5 READY"
        case .confirmed:
            title = copy.readyTitle
            subtitle = "5/5 CONFIRMED  •  \(copy.openingLabel)"
        case .openFailed:
            title = copy.readyTitle
            subtitle = "COULDN’T OPEN \(copy.destinationLabel.uppercased()) — OPEN IT MANUALLY"
        }

        drawCenteredText(
            title,
            in: NSRect(x: 52, y: 291, width: bounds.width - 104, height: 30),
            font: NSFont(name: "Palatino-Bold", size: 20) ?? .boldSystemFont(ofSize: 20),
            minimumFontSize: 13,
            color: NSColor(calibratedWhite: 0.97, alpha: 1),
            shadow: true
        )
        drawCenteredText(
            subtitle,
            in: NSRect(x: 62, y: 267, width: bounds.width - 124, height: 20),
            font: NSFont(name: "Palatino-Bold", size: 11.5) ?? .boldSystemFont(ofSize: 11.5),
            minimumFontSize: 8.5,
            color: NSColor(calibratedRed: 1.0, green: 0.79, blue: 0.26, alpha: 1),
            shadow: true
        )

        let cardWidth: CGFloat = 104
        let gap: CGFloat = 4
        let totalWidth = cardWidth * 5 + gap * 4
        let startX = (bounds.width - totalWidth) / 2
        for (index, member) in members.enumerated() {
            let x = startX + CGFloat(index) * (cardWidth + gap)
            drawMember(member, index: index, card: NSRect(x: x, y: 101, width: cardWidth, height: 153))
        }

        switch phase {
        case .ready:
            drawButtonLabel(enterRect, title: copy.enterLabel, hovered: hoverEnter || demoButtonPressed || isKeyboardFocused(0), active: true)
            drawButtonLabel(leaveRect, title: "LEAVE QUEUE", hovered: hoverLeave || demoLeaveHovered || isKeyboardFocused(1), active: true)
        case .waiting:
            drawButtonLabel(enterRect, title: "YOU: READY", hovered: false, active: false, positive: true)
            drawButtonLabel(leaveRect, title: "WAITING  \(confirmed.count)/5", hovered: false, active: false)
        case .confirmed:
            drawButtonLabel(enterRect, title: "PARTY READY", hovered: false, active: false, positive: true)
            drawButtonLabel(leaveRect, title: copy.openingLabel, hovered: false, active: false)
        case .openFailed:
            drawButtonLabel(enterRect, title: "PARTY READY", hovered: false, active: false, positive: true)
            drawButtonLabel(leaveRect, title: "OPEN \(copy.destinationLabel.uppercased())", hovered: hoverLeave || demoLeaveHovered || isKeyboardFocused(1), active: true)
        }

        if let point = demoCursorPoint { drawDemoCursor(at: point, clickRing: demoClickRing) }
        NSGraphicsContext.restoreGraphicsState()
    }

    private func drawMember(_ member: PartyMember, index: Int, card: NSRect) {
        let portrait = NSRect(x: card.midX - 50, y: card.minY + 54, width: 100, height: 100)
        let outerRing = NSBezierPath(ovalIn: portrait.insetBy(dx: -3, dy: -3))
        NSColor(calibratedWhite: 0.08, alpha: 0.96).setFill()
        outerRing.fill()
        NSColor(calibratedWhite: 0.48, alpha: 1).setStroke()
        outerRing.lineWidth = 2
        outerRing.stroke()
        let clip = NSBezierPath(ovalIn: portrait)
        NSGraphicsContext.saveGraphicsState()
        clip.addClip()
        drawAspectFill(member.image, in: portrait, zoom: member.portraitZoom)
        NSGraphicsContext.restoreGraphicsState()
        NSColor(calibratedRed: 0.72, green: 0.58, blue: 0.24, alpha: 1).setStroke()
        clip.lineWidth = 2
        clip.stroke()

        let roleIconRect = NSRect(x: card.midX - 22, y: card.minY - 18, width: 44, height: 44)
        member.roleIcon.draw(in: roleIconRect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
        drawCenteredText(
            member.name,
            in: NSRect(x: card.minX + 1, y: card.minY + 28, width: card.width - 2, height: 20),
            font: NSFont(name: "Palatino-Bold", size: 13) ?? .boldSystemFont(ofSize: 13),
            minimumFontSize: 8.5,
            color: NSColor(calibratedRed: 1.0, green: 0.82, blue: 0.38, alpha: 1),
            shadow: true
        )

        guard phase != .ready else { return }
        let statusRect = NSRect(x: portrait.maxX - 28, y: portrait.minY - 4, width: 32, height: 32)
        let statusPath = NSBezierPath(ovalIn: statusRect)
        if confirmed.contains(index) {
            NSColor(calibratedRed: 0.10, green: 0.50, blue: 0.10, alpha: 0.98).setFill()
            statusPath.fill()
            NSColor(calibratedRed: 0.66, green: 1.0, blue: 0.51, alpha: 1).setStroke()
            statusPath.lineWidth = 2
            statusPath.stroke()
            drawSymbol("checkmark", in: statusRect.insetBy(dx: 7, dy: 7), color: .white)
        } else {
            NSColor(calibratedWhite: 0.055, alpha: 0.97).setFill()
            statusPath.fill()
            NSColor(calibratedRed: 0.77, green: 0.60, blue: 0.22, alpha: 1).setStroke()
            statusPath.lineWidth = 1.5
            statusPath.stroke()
            drawSymbol("ellipsis", in: statusRect.insetBy(dx: 6, dy: 9), color: NSColor(calibratedRed: 1.0, green: 0.79, blue: 0.29, alpha: 1))
        }
    }

    private func drawButtonLabel(_ rect: NSRect, title: String, hovered: Bool, active: Bool, positive: Bool = false) {
        if hovered {
            let hover = NSBezierPath(roundedRect: rect.insetBy(dx: 2, dy: 2), xRadius: 4, yRadius: 4)
            NSColor(calibratedRed: 1, green: 0.72, blue: 0.18, alpha: 0.14).setFill()
            hover.fill()
            NSColor(calibratedRed: 1, green: 0.73, blue: 0.20, alpha: 0.92).setStroke()
            hover.lineWidth = 1.5
            hover.stroke()
        }
        drawCenteredText(
            title,
            in: rect,
            font: NSFont(name: "Palatino-Bold", size: 14.5) ?? .boldSystemFont(ofSize: 14.5),
            minimumFontSize: 9,
            color: positive
                ? NSColor(calibratedRed: 0.65, green: 1.0, blue: 0.49, alpha: 1)
                : NSColor(calibratedRed: 1.0, green: 0.79, blue: active ? 0.27 : 0.42, alpha: 1),
            shadow: true
        )
    }

    private func isKeyboardFocused(_ index: Int) -> Bool {
        window?.firstResponder === self && keyboardFocus == index
    }

    private func drawSymbol(_ name: String, in rect: NSRect, color: NSColor) {
        guard let base = NSImage(systemSymbolName: name, accessibilityDescription: nil) else { return }
        let configuration = NSImage.SymbolConfiguration(pointSize: rect.height, weight: .bold)
            .applying(NSImage.SymbolConfiguration(paletteColors: [color]))
        (base.withSymbolConfiguration(configuration) ?? base).draw(in: rect)
    }

    private func drawAspectFill(_ image: NSImage, in destination: NSRect, zoom: CGFloat) {
        let sourceSize = image.size
        guard sourceSize.width > 0, sourceSize.height > 0 else { return }
        let targetRatio = destination.width / destination.height
        let imageRatio = sourceSize.width / sourceSize.height
        var source: NSRect
        if imageRatio > targetRatio {
            let width = sourceSize.height * targetRatio
            source = NSRect(x: (sourceSize.width - width) / 2, y: 0, width: width, height: sourceSize.height)
        } else {
            let height = sourceSize.width / targetRatio
            source = NSRect(x: 0, y: (sourceSize.height - height) / 2, width: sourceSize.width, height: height)
        }
        source = source.insetBy(
            dx: source.width * (1 - 1 / zoom) / 2,
            dy: source.height * (1 - 1 / zoom) / 2
        )
        image.draw(in: destination, from: source, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
    }

    private func drawDemoCursor(at point: NSPoint, clickRing: Bool) {
        let image = (clickRing || demoButtonPressed || demoLeaveHovered) ? cursorActiveImage : cursorImage
        let size = NSSize(width: 32, height: 32)
        let destination = NSRect(x: point.x - 1, y: point.y - (size.height - 1), width: size.width, height: size.height)
        image.draw(in: destination, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.none])
    }
}

private final class ModelFinderWatchView: NSView {
    let elapsed: String
    let checkNumber: Int
    let detected: Bool
    let frameSkin: NSImage
    let copy: PopupCopy

    init(frame frameRect: NSRect, elapsed: String, checkNumber: Int, detected: Bool, frameSkin: NSImage, copy: PopupCopy) {
        self.elapsed = elapsed
        self.checkNumber = checkNumber
        self.detected = detected
        self.frameSkin = frameSkin
        self.copy = copy
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = true
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        frameSkin.draw(in: bounds, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
        drawCenteredText(
            "\(copy.destinationLabel) Model Finder",
            in: NSRect(x: 52, y: 290, width: bounds.width - 104, height: 30),
            font: NSFont(name: "Palatino-Bold", size: 21) ?? .boldSystemFont(ofSize: 21),
            minimumFontSize: 13,
            color: NSColor(calibratedWhite: 0.97, alpha: 1),
            shadow: true
        )
        drawCenteredText(
            "QUEUED FOR \(copy.modelName.uppercased()) ACCESS",
            in: NSRect(x: 65, y: 266, width: bounds.width - 130, height: 20),
            font: NSFont(name: "Palatino-Bold", size: 11.5) ?? .boldSystemFont(ofSize: 11.5),
            minimumFontSize: 8.5,
            color: NSColor(calibratedRed: 1.0, green: 0.79, blue: 0.26, alpha: 1),
            shadow: true
        )
        drawCenteredText(
            "QUEUE ELAPSED",
            in: NSRect(x: 90, y: 225, width: bounds.width - 180, height: 20),
            font: .systemFont(ofSize: 10.5, weight: .bold),
            color: NSColor(calibratedWhite: 0.63, alpha: 1),
            shadow: true
        )
        drawCenteredText(
            elapsed,
            in: NSRect(x: 72, y: 170, width: bounds.width - 144, height: 52),
            font: .monospacedDigitSystemFont(ofSize: 42, weight: .medium),
            color: detected ? NSColor(calibratedRed: 0.63, green: 1.0, blue: 0.48, alpha: 1) : NSColor(calibratedWhite: 0.96, alpha: 1),
            shadow: true
        )
        drawCenteredText(
            detected ? "\(copy.modelName) access detected — your group has been found." : "Checking \(copy.destinationLabel) access…",
            in: NSRect(x: 66, y: 124, width: bounds.width - 132, height: 25),
            font: NSFont(name: "Palatino-Roman", size: 12.5) ?? .systemFont(ofSize: 12.5, weight: .medium),
            minimumFontSize: 9,
            color: detected ? NSColor(calibratedRed: 0.65, green: 1.0, blue: 0.50, alpha: 1) : NSColor(calibratedWhite: 0.78, alpha: 1),
            shadow: true
        )
        drawCenteredText(
            "CHECK  #\(checkNumber)",
            in: NSRect(x: 58, y: 37, width: 215, height: 41),
            font: NSFont(name: "Palatino-Bold", size: 14.5) ?? .boldSystemFont(ofSize: 14.5),
            color: NSColor(calibratedRed: 1.0, green: 0.79, blue: 0.29, alpha: 1),
            shadow: true
        )
        drawCenteredText(
            detected ? "\(copy.modelName.uppercased()) FOUND" : "NOT YET",
            in: NSRect(x: 305, y: 37, width: 218, height: 41),
            font: NSFont(name: "Palatino-Bold", size: 14.5) ?? .boldSystemFont(ofSize: 14.5),
            minimumFontSize: 9,
            color: detected ? NSColor(calibratedRed: 0.65, green: 1.0, blue: 0.49, alpha: 1) : NSColor(calibratedWhite: 0.80, alpha: 1),
            shadow: true
        )
    }
}

private final class PopupController: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let runtime: LoadedRuntime
    private var panel: PopupPanel?
    private var partyView: ModelFinderPartyView?
    private var players: [AVAudioPlayer] = []
    private var isClosing = false
    private var hadAudioFailure = false
    private var completionScheduled = false

    init(runtime: LoadedRuntime) {
        self.runtime = runtime
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let screen = NSScreen.main ?? NSScreen.screens.first else {
            fputs("No display is available for the popup.\n", stderr)
            Darwin.exit(70)
        }
        let visible = screen.visibleFrame
        let fitScale = min(1.0, (visible.width * 0.88) / canvasSize.width, (visible.height * 0.80) / canvasSize.height)
        let finalSize = NSSize(width: canvasSize.width * fitScale, height: canvasSize.height * fitScale)
        let finalFrame = NSRect(
            x: visible.midX - finalSize.width / 2,
            y: visible.midY - finalSize.height / 2,
            width: finalSize.width,
            height: finalSize.height
        )
        let popup = PopupPanel(contentRect: finalFrame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        popup.delegate = self
        popup.isFloatingPanel = true
        popup.level = .floating
        popup.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        if #available(macOS 13.0, *) { popup.collectionBehavior.insert(.canJoinAllApplications) }
        popup.hidesOnDeactivate = false
        popup.canHide = false
        popup.isMovable = true
        popup.isMovableByWindowBackground = true
        popup.isOpaque = false
        popup.backgroundColor = .clear
        popup.hasShadow = true
        popup.animationBehavior = .utilityWindow
        popup.alphaValue = 0
        popup.isReleasedWhenClosed = false
        popup.acceptsMouseMovedEvents = true

        let view = ModelFinderPartyView(
            frame: NSRect(origin: .zero, size: finalSize),
            members: runtime.members,
            copy: runtime.copy,
            frameSkin: runtime.frameSkin,
            cursorImage: runtime.cursorImage,
            cursorActiveImage: runtime.cursorActiveImage
        )
        view.autoresizingMask = [.width, .height]
        view.onEnter = { [weak self] in self?.beginConfirmations() }
        view.onLeave = { [weak self] in
            guard let self else { return }
            let code: Int32 = self.partyView?.phase == .openFailed ? 69 : (self.hadAudioFailure ? 74 : 0)
            self.finish(exitCode: code)
        }
        view.onOpenDestination = { [weak self] in self?.openDestination() }
        popup.contentView = view
        view.frame = NSRect(origin: .zero, size: finalSize)
        view.bounds = NSRect(origin: .zero, size: canvasSize)
        panel = popup
        partyView = view

        popup.orderFrontRegardless()
        popup.invalidateCursorRects(for: view)
        let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        if !reduceMotion, let layer = view.layer {
            let scaleIn = CABasicAnimation(keyPath: "transform.scale")
            scaleIn.fromValue = 0.91
            scaleIn.toValue = 1.0
            scaleIn.duration = 0.34
            scaleIn.timingFunction = CAMediaTimingFunction(name: .easeOut)
            layer.add(scaleIn, forKey: "modelFinderPopupScaleIn")
        }
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = reduceMotion ? 0.16 : 0.34
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            popup.animator().alphaValue = 1
        }, completionHandler: { [weak self] in
            guard let self, !self.isClosing else { return }
            print("POPUP_SHOWN")
            print("TARGET_MODEL \(self.runtime.copy.modelID)")
            if !self.play(self.runtime.readySound, volume: 1.0) { self.hadAudioFailure = true }
        })
        DispatchQueue.main.asyncAfter(deadline: .now() + runtime.idleSeconds) { [weak self] in
            guard let self, self.partyView?.phase == .ready else { return }
            print("POPUP_DISMISSED_IDLE")
            self.finish(exitCode: self.hadAudioFailure ? 74 : 0)
        }
    }

    private func beginConfirmations() {
        guard !isClosing, let view = partyView, view.phase == .ready else { return }
        view.phase = .waiting
        view.confirmed.insert(runtime.localMemberIndex)
        let localName = runtime.members[runtime.localMemberIndex].name
        print("ENTER_CLICKED")
        if !play(runtime.enterSound, volume: 0.95) { hadAudioFailure = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) { [weak self] in
            guard let self, !self.isClosing else { return }
            if !self.play(self.runtime.confirmSound, volume: 0.38) { self.hadAudioFailure = true }
            print("PLAYER_CONFIRMED \(localName)")
        }

        let remoteIndices = runtime.members.indices.filter { $0 != runtime.localMemberIndex }
        let lowerBucket = Int(ceil(runtime.confirmationMinimum * 2))
        let upperBucket = Int(floor(runtime.confirmationMaximum * 2))
        let buckets = Array(lowerBucket...upperBucket).map { Double($0) / 2 }
        var schedule = remoteIndices.map { memberIndex -> (memberIndex: Int, delay: Double) in
            (memberIndex, buckets.randomElement() ?? runtime.confirmationMinimum)
        }

        // This is only a visual ready-check simulation. It does not inspect the
        // presence, consent, or actions of the people represented by these avatars.
        // Each simulated remote member chooses an independent half-second bucket,
        // so two or more confirmations may intentionally happen at the same time.
        if runtime.confirmationMaximum >= 3, !schedule.contains(where: { $0.delay >= 3 }) {
            let longBuckets = buckets.filter { $0 >= 3 }
            if let scheduleIndex = schedule.indices.randomElement(), let delay = longBuckets.randomElement() {
                schedule[scheduleIndex] = (schedule[scheduleIndex].memberIndex, delay)
            }
        }

        let sortedSchedule = schedule.sorted {
            if $0.delay == $1.delay { return $0.memberIndex < $1.memberIndex }
            return $0.delay < $1.delay
        }
        let names = sortedSchedule.map { runtime.members[$0.memberIndex].name }.joined(separator: ",")
        let receipt = sortedSchedule.map {
            "\(runtime.members[$0.memberIndex].name)@\(String(format: "%.1f", $0.delay))s"
        }.joined(separator: ",")
        print("SIMULATED_CONFIRMATION_ORDER \(names)")
        print("SIMULATED_CONFIRMATION_SCHEDULE \(receipt)")

        for entry in schedule {
            DispatchQueue.main.asyncAfter(deadline: .now() + entry.delay) { [weak self] in
                guard let self, !self.isClosing, let currentView = self.partyView else { return }
                currentView.confirmed.insert(entry.memberIndex)
                if !self.play(self.runtime.confirmSound, volume: 0.38) { self.hadAudioFailure = true }
                print("PLAYER_CONFIRMED \(self.runtime.members[entry.memberIndex].name)")
                if currentView.confirmed.count == self.runtime.members.count, !self.completionScheduled {
                    self.completionScheduled = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) { [weak self] in
                        guard let self, !self.isClosing else { return }
                        self.partyView?.phase = .confirmed
                        print("PARTY_CONFIRMED")
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2.50) { [weak self] in self?.openDestination() }
                    }
                }
            }
        }
    }

    private func openDestination() {
        guard !isClosing else { return }
        if NSWorkspace.shared.open(runtime.destination) {
            print("DESTINATION_OPENED \(runtime.destination.absoluteString)")
            finish(exitCode: hadAudioFailure ? 74 : 0)
        } else {
            fputs("Could not open destination: \(runtime.destination.absoluteString)\n", stderr)
            partyView?.phase = .openFailed
            DispatchQueue.main.asyncAfter(deadline: .now() + 12.0) { [weak self] in self?.finish(exitCode: 69) }
        }
    }

    @discardableResult
    private func play(_ data: Data?, volume: Float) -> Bool {
        guard !isClosing else { return false }
        guard let data else { return true }
        do {
            let player = try AVAudioPlayer(data: data)
            player.volume = volume
            player.prepareToPlay()
            guard player.play() else {
                fputs("Audio player could not start.\n", stderr)
                return false
            }
            players.append(player)
            return true
        } catch {
            fputs("Unable to play popup sound: \(error.localizedDescription)\n", stderr)
            return false
        }
    }

    private func finish(exitCode: Int32) {
        guard !isClosing else { return }
        isClosing = true
        guard let popup = panel else { Darwin.exit(exitCode) }
        let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        if !reduceMotion, let layer = partyView?.layer {
            let scaleOut = CABasicAnimation(keyPath: "transform.scale")
            scaleOut.fromValue = 1.0
            scaleOut.toValue = 0.975
            scaleOut.duration = 0.20
            scaleOut.timingFunction = CAMediaTimingFunction(name: .easeIn)
            layer.add(scaleOut, forKey: "modelFinderPopupScaleOut")
        }
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = reduceMotion ? 0.12 : 0.20
            context.timingFunction = CAMediaTimingFunction(name: .easeIn)
            popup.animator().alphaValue = 0
        }, completionHandler: {
            NSCursor.arrow.set()
            popup.orderOut(nil)
            Darwin.exit(exitCode)
        })
    }

    func windowWillClose(_ notification: Notification) {
        if !isClosing { finish(exitCode: hadAudioFailure ? 74 : 0) }
    }
}

private func requiredText(_ value: String, label: String, maximumLength: Int) throws -> String {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { throw RuntimeValidationError(message: "\(label) must not be empty") }
    guard trimmed.rangeOfCharacter(from: .controlCharacters) == nil else {
        throw RuntimeValidationError(message: "\(label) must not contain control characters")
    }
    guard trimmed.count <= maximumLength else {
        throw RuntimeValidationError(message: "\(label) must be at most \(maximumLength) characters")
    }
    return trimmed
}

private func readableFileURL(_ path: String, label: String) throws -> URL {
    guard NSString(string: path).isAbsolutePath else {
        throw RuntimeValidationError(message: "\(label) must be an absolute path: \(path)")
    }
    let url = URL(fileURLWithPath: path).standardizedFileURL
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory), !isDirectory.boolValue else {
        throw RuntimeValidationError(message: "\(label) is not a readable file: \(url.path)")
    }
    guard FileManager.default.isReadableFile(atPath: url.path) else {
        throw RuntimeValidationError(message: "\(label) is not readable: \(url.path)")
    }
    return url
}

private func loadImage(path: String, label: String, logicalCursorSize: Bool = false) throws -> NSImage {
    let url = try readableFileURL(path, label: label)
    guard let image = NSImage(contentsOf: url), image.size.width > 0, image.size.height > 0 else {
        throw RuntimeValidationError(message: "\(label) is not a supported image: \(url.path)")
    }
    if logicalCursorSize { image.size = NSSize(width: 32, height: 32) }
    return image
}

private func loadAudio(path: String?, label: String) throws -> Data? {
    guard let path else { return nil }
    let url = try readableFileURL(path, label: label)
    let data = try Data(contentsOf: url, options: .mappedIfSafe)
    do {
        _ = try AVAudioPlayer(data: data)
    } catch {
        throw RuntimeValidationError(message: "\(label) is not supported audio: \(url.path)")
    }
    return data
}

private func loadRuntime(from runtimeURL: URL) throws -> LoadedRuntime {
    let data = try Data(contentsOf: runtimeURL)
    let document: RuntimeDocument
    do {
        document = try JSONDecoder().decode(RuntimeDocument.self, from: data)
    } catch {
        throw RuntimeValidationError(message: "Invalid runtime JSON: \(error.localizedDescription)")
    }

    let modelID = try requiredText(document.target.modelID, label: "target.modelID", maximumLength: 128)
    let modelName = try requiredText(document.target.displayName, label: "target.displayName", maximumLength: 24)
    let destinationLabel = try requiredText(document.popup.destinationLabel, label: "popup.destinationLabel", maximumLength: 14)
    guard document.members.count == 5 else {
        throw RuntimeValidationError(message: "members must contain exactly five entries")
    }
    let explicitlyLocal = document.members.indices.filter { document.members[$0].isLocal == true }
    guard explicitlyLocal.count <= 1 else {
        throw RuntimeValidationError(message: "members may contain at most one isLocal=true entry")
    }
    let localMemberIndex = explicitlyLocal.first ?? document.members.index(before: document.members.endIndex)

    let roleTank = try loadImage(path: document.popup.theme.roleTank, label: "popup.theme.roleTank")
    let roleHealer = try loadImage(path: document.popup.theme.roleHealer, label: "popup.theme.roleHealer")
    let roleDPS = try loadImage(path: document.popup.theme.roleDPS, label: "popup.theme.roleDPS")
    var seenNames = Set<String>()
    let members: [PartyMember] = try document.members.enumerated().map { index, rawMember in
        let name = try requiredText(rawMember.name, label: "members[\(index)].name", maximumLength: 20)
        let displayName = name.uppercased()
        guard seenNames.insert(displayName).inserted else {
            throw RuntimeValidationError(message: "member names must be unique (duplicate: \(name))")
        }
        _ = try requiredText(rawMember.avatarSource, label: "members[\(index)].avatarSource", maximumLength: 2_048)
        guard let role = PartyRole(rawValue: rawMember.role.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()) else {
            throw RuntimeValidationError(message: "members[\(index)].role must be tank, healer, or dps")
        }
        let zoom = rawMember.portraitZoom ?? (index == localMemberIndex ? 1.23 : 1.17)
        guard zoom.isFinite, zoom >= 1, zoom <= 2 else {
            throw RuntimeValidationError(message: "members[\(index)].portraitZoom must be between 1 and 2")
        }
        let image = try loadImage(path: rawMember.avatarPath, label: "members[\(index)].avatarPath")
        let roleIcon: NSImage
        switch role {
        case .tank: roleIcon = roleTank
        case .healer: roleIcon = roleHealer
        case .dps: roleIcon = roleDPS
        }
        return PartyMember(name: displayName, role: role, image: image, roleIcon: roleIcon, portraitZoom: CGFloat(zoom))
    }

    let roleCounts = Dictionary(grouping: members, by: \.role).mapValues(\.count)
    guard roleCounts[.tank] == 1, roleCounts[.healer] == 1, roleCounts[.dps] == 3 else {
        throw RuntimeValidationError(message: "members must contain exactly one tank, one healer, and three dps")
    }

    guard let destinationComponents = URLComponents(string: document.popup.destinationURL),
          let scheme = destinationComponents.scheme?.lowercased(),
          ["codex", "http", "https"].contains(scheme) else {
        throw RuntimeValidationError(message: "popup.destinationURL must use the codex, http, or https scheme")
    }
    guard let host = destinationComponents.host, !host.isEmpty else {
        throw RuntimeValidationError(message: "popup.destinationURL must include a host")
    }
    guard destinationComponents.user == nil, destinationComponents.password == nil else {
        throw RuntimeValidationError(message: "popup.destinationURL must not contain a username or password")
    }
    if let port = destinationComponents.port, !(1...65_535).contains(port) {
        throw RuntimeValidationError(message: "popup.destinationURL contains an invalid port")
    }
    guard let destination = destinationComponents.url else {
        throw RuntimeValidationError(message: "popup.destinationURL is invalid")
    }
    let idleSeconds = document.popup.idleSeconds ?? defaultIdleSeconds
    guard idleSeconds.isFinite, idleSeconds >= 5, idleSeconds <= 300 else {
        throw RuntimeValidationError(message: "popup.idleSeconds must be between 5 and 300")
    }
    let confirmationMinimum = document.popup.confirmationMinSeconds ?? defaultConfirmationMinimum
    let confirmationMaximum = document.popup.confirmationMaxSeconds ?? defaultConfirmationMaximum
    guard confirmationMinimum.isFinite, confirmationMaximum.isFinite,
          confirmationMinimum >= 0.5,
          confirmationMaximum >= confirmationMinimum,
          confirmationMaximum <= 60 else {
        throw RuntimeValidationError(message: "confirmation timing must be finite, ordered, and between 0.5 and 60 seconds")
    }
    guard Int(ceil(confirmationMinimum * 2)) <= Int(floor(confirmationMaximum * 2)) else {
        throw RuntimeValidationError(message: "confirmation timing range must contain at least one half-second bucket")
    }

    let frameSkin = try loadImage(path: document.popup.theme.frame, label: "popup.theme.frame")
    let cursorImage = try loadImage(path: document.popup.theme.cursor, label: "popup.theme.cursor", logicalCursorSize: true)
    let cursorActiveImage = try loadImage(path: document.popup.theme.cursorActive, label: "popup.theme.cursorActive", logicalCursorSize: true)
    let readySound = try loadAudio(path: document.popup.sounds.ready, label: "popup.sounds.ready")
    let enterSound = try loadAudio(path: document.popup.sounds.enter, label: "popup.sounds.enter")
    let confirmSound = try loadAudio(path: document.popup.sounds.confirm, label: "popup.sounds.confirm")

    return LoadedRuntime(
        members: members,
        localMemberIndex: localMemberIndex,
        frameSkin: frameSkin,
        cursorImage: cursorImage,
        cursorActiveImage: cursorActiveImage,
        readySound: readySound,
        enterSound: enterSound,
        confirmSound: confirmSound,
        destination: destination,
        idleSeconds: idleSeconds,
        confirmationMinimum: confirmationMinimum,
        confirmationMaximum: confirmationMaximum,
        copy: PopupCopy(modelID: modelID, modelName: modelName, destinationLabel: destinationLabel)
    )
}

private func render(_ view: NSView, to output: URL) throws {
    let window = NSWindow(contentRect: NSRect(origin: .zero, size: canvasSize), styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = view
    view.frame = NSRect(origin: .zero, size: canvasSize)
    view.display()
    guard let representation = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
        throw RuntimeValidationError(message: "Could not allocate preview bitmap")
    }
    view.cacheDisplay(in: view.bounds, to: representation)
    guard let data = representation.representation(using: .png, properties: [:]) else {
        throw RuntimeValidationError(message: "Could not encode preview PNG")
    }
    try data.write(to: output, options: .atomic)
}

private func renderStates(runtime: LoadedRuntime, directory: URL, includeCursor: Bool) throws {
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let watches: [(String, String, Int, Bool)] = [
        ("watch-00.png", "00:00:00", 1, false),
        ("watch-01.png", "01:40:00", 11, false),
        ("watch-02.png", "03:20:00", 21, false),
        ("watch-03.png", "05:30:00", 34, false),
        ("watch-04-detected.png", "05:40:00", 35, true)
    ]
    for (filename, elapsed, checkNumber, detected) in watches {
        let view = ModelFinderWatchView(
            frame: NSRect(origin: .zero, size: canvasSize),
            elapsed: elapsed,
            checkNumber: checkNumber,
            detected: detected,
            frameSkin: runtime.frameSkin,
            copy: runtime.copy
        )
        try render(view, to: directory.appendingPathComponent(filename))
    }

    let preferredOrder = [runtime.localMemberIndex, 2, 0, 3, 1] + Array(runtime.members.indices)
    var seen = Set<Int>()
    let demoOrder = preferredOrder.filter { runtime.members.indices.contains($0) && seen.insert($0).inserted }
    let states: [(String, PartyPhase, Set<Int>)] = [
        ("00-ready.png", .ready, []),
        ("01-billy.png", .waiting, Set(demoOrder.prefix(1))),
        ("02-victor.png", .waiting, Set(demoOrder.prefix(2))),
        ("03-tibo.png", .waiting, Set(demoOrder.prefix(3))),
        ("04-sam.png", .waiting, Set(demoOrder.prefix(4))),
        ("05-andrew.png", .waiting, Set(demoOrder.prefix(5))),
        ("06-confirmed.png", .confirmed, Set(demoOrder)),
        ("07-open-failed.png", .openFailed, Set(demoOrder))
    ]
    for (filename, phase, confirmed) in states {
        let view = ModelFinderPartyView(
            frame: NSRect(origin: .zero, size: canvasSize),
            members: runtime.members,
            copy: runtime.copy,
            frameSkin: runtime.frameSkin,
            cursorImage: runtime.cursorImage,
            cursorActiveImage: runtime.cursorActiveImage
        )
        view.phase = phase
        view.confirmed = confirmed
        try render(view, to: directory.appendingPathComponent(filename))
    }

    let cursorPoints: [NSPoint] = [
        NSPoint(x: 548, y: 24), NSPoint(x: 488, y: 24), NSPoint(x: 428, y: 24),
        NSPoint(x: 366, y: 24), NSPoint(x: 304, y: 26), NSPoint(x: 250, y: 38),
        NSPoint(x: 196, y: 58)
    ]
    for (index, point) in cursorPoints.enumerated() {
        let view = ModelFinderPartyView(
            frame: NSRect(origin: .zero, size: canvasSize),
            members: runtime.members,
            copy: runtime.copy,
            frameSkin: runtime.frameSkin,
            cursorImage: runtime.cursorImage,
            cursorActiveImage: runtime.cursorActiveImage
        )
        if includeCursor { view.demoCursorPoint = point }
        view.demoButtonPressed = index >= 5
        try render(view, to: directory.appendingPathComponent(String(format: "cursor-%02d.png", index)))
    }

    let clickView = ModelFinderPartyView(
        frame: NSRect(origin: .zero, size: canvasSize),
        members: runtime.members,
        copy: runtime.copy,
        frameSkin: runtime.frameSkin,
        cursorImage: runtime.cursorImage,
        cursorActiveImage: runtime.cursorActiveImage
    )
    if includeCursor { clickView.demoCursorPoint = cursorPoints.last }
    clickView.demoClickRing = true
    clickView.demoButtonPressed = true
    try render(clickView, to: directory.appendingPathComponent("cursor-07-click.png"))

    let failedHoverView = ModelFinderPartyView(
        frame: NSRect(origin: .zero, size: canvasSize),
        members: runtime.members,
        copy: runtime.copy,
        frameSkin: runtime.frameSkin,
        cursorImage: runtime.cursorImage,
        cursorActiveImage: runtime.cursorActiveImage
    )
    failedHoverView.phase = .openFailed
    failedHoverView.confirmed = Set(demoOrder)
    failedHoverView.demoLeaveHovered = true
    if includeCursor { failedHoverView.demoCursorPoint = NSPoint(x: 414, y: 58) }
    failedHoverView.demoClickRing = true
    try render(failedHoverView, to: directory.appendingPathComponent("08-open-failed-hover.png"))
}

private func usage() {
    fputs(
        "Usage: model-finder-popup RUNTIME.json\n" +
        "       model-finder-popup RUNTIME.json --render-states OUTPUT_DIRECTORY [--no-cursor]\n",
        stderr
    )
}

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard !arguments.isEmpty else {
        usage()
        Darwin.exit(64)
    }
    let isRenderMode = arguments.count >= 3 && arguments[1] == "--render-states"
    let validLiveArguments = arguments.count == 1
    let validRenderArguments = isRenderMode && (arguments.count == 3 || (arguments.count == 4 && arguments[3] == "--no-cursor"))
    guard validLiveArguments || validRenderArguments else {
        usage()
        Darwin.exit(64)
    }

    let runtimeURL = URL(fileURLWithPath: arguments[0]).standardizedFileURL
    let runtime = try loadRuntime(from: runtimeURL)
    if isRenderMode {
        _ = NSApplication.shared
        let outputDirectory = URL(fileURLWithPath: arguments[2]).standardizedFileURL
        try renderStates(runtime: runtime, directory: outputDirectory, includeCursor: !arguments.contains("--no-cursor"))
        print("RENDERED_STATES \(outputDirectory.path)")
        Darwin.exit(0)
    }

    let app = NSApplication.shared
    guard app.setActivationPolicy(.accessory) else {
        fputs("Unable to configure the popup as a persistent accessory application.\n", stderr)
        Darwin.exit(70)
    }
    let controller = PopupController(runtime: runtime)
    app.delegate = controller
    app.run()
} catch {
    fputs("Model Finder popup preflight failed: \(error.localizedDescription)\n", stderr)
    Darwin.exit(66)
}
