"""Real transparent AppKit selection windows, without reading the screen."""

import logging
import objc
import AppKit as AK
import Quartz as Q

from native.selection import Display, Phase, Point, Rect, Selection
from native.macos import appearance as style
from native.macos.mascot_anchor import MascotAnchor
from native.macos.mascot import BeaverView

LOG = logging.getLogger(__name__)


def color(rgba):
    return AK.NSColor.colorWithSRGBRed_green_blue_alpha_(*rgba)


def mouse_point():
    point = AK.NSEvent.mouseLocation()
    return Point(point.x, point.y)


def displays():
    result = []
    for screen in AK.NSScreen.screens():
        frame = screen.frame()
        result.append(Display(int(screen.deviceDescription()['NSScreenNumber']),
                              Rect(frame.origin.x, frame.origin.y, frame.size.width, frame.size.height),
                              float(screen.backingScaleFactor())))
    return result


class SelectionPanel(AK.NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False


class SelectionView(AK.NSView):
    @objc.python_method
    def configure(self, controller, display):
        self.controller = controller
        self.display = display
        self.setWantsLayer_(True)
        self.layer().setContentsScale_(display.scale)
        self.halo = Q.CAShapeLayer.layer()
        self.border = Q.CAShapeLayer.layer()
        for layer in (self.halo, self.border):
            layer.setFillColor_(None)
            layer.setLineCap_('round')
            layer.setLineJoin_('round')
            layer.setContentsScale_(display.scale)
            self.layer().addSublayer_(layer)
        self.halo.setStrokeColor_(color((1, 1, 1, .90)).CGColor())
        self.halo.setLineWidth_(style.STROKE + 1.5)
        self.border.setStrokeColor_(color(style.BLUE).CGColor())
        self.border.setLineWidth_(style.STROKE)
        self.border.setLineDashPattern_(list(style.DASH))
        # A tiny native control strip. It intercepts clicks, never forwarding them.
        self.card = AK.NSView.alloc().initWithFrame_(AK.NSMakeRect(0, 0, style.CARD_WIDTH, style.CARD_HEIGHT))
        # The control strip is always light, including when macOS uses Dark Mode.
        self.card.setAppearance_(AK.NSAppearance.appearanceNamed_(AK.NSAppearanceNameAqua))
        self.card.setWantsLayer_(True)
        self.card.layer().setBackgroundColor_(color(style.PAPER).CGColor())
        self.card.layer().setCornerRadius_(10)
        self.card.layer().setBorderWidth_(.5)
        self.card.layer().setBorderColor_(color((.1, .13, .2, .18)).CGColor())
        self.label = AK.NSTextField.labelWithString_('Drag to select · Amillum')
        self.label.setFont_(AK.NSFont.systemFontOfSize_(11))
        self.label.setTextColor_(color(style.INK))
        self.label.setFrame_(AK.NSMakeRect(12, 41, 325, 19))
        self.card.addSubview_(self.label)
        self.cancel_button = AK.NSButton.buttonWithTitle_target_action_('Cancel', self, 'cancel:')
        self.cancel_button.setBezelStyle_(AK.NSBezelStyleRounded)
        self.cancel_button.setFont_(AK.NSFont.systemFontOfSize_(11))
        self.cancel_button.setFrame_(AK.NSMakeRect(280, 5, 62, 26))
        self.cancel_button.setToolTip_('Cancel selection (Escape). Nothing is captured or sent.')
        self.cancel_button.setAccessibilityLabel_('Cancel Amillum selection')
        self.card.addSubview_(self.cancel_button)
        self.read_button = AK.NSButton.buttonWithTitle_target_action_('Read locally', self, 'approve:')
        self.read_button.setBezelStyle_(AK.NSBezelStyleRounded)
        self.read_button.setFont_(AK.NSFont.systemFontOfSize_(11))
        self.read_button.setFrame_(AK.NSMakeRect(170, 5, 103, 26))
        self.read_button.setToolTip_('Approve reading only this region. Review the text before any AI request.')
        self.card.addSubview_(self.read_button)
        for button in (self.read_button, self.cancel_button):
            title = AK.NSAttributedString.alloc().initWithString_attributes_(
                button.title(), {AK.NSForegroundColorAttributeName: AK.NSColor.blackColor(),
                                 AK.NSFontAttributeName: button.font()})
            button.setAttributedTitle_(title)
            button.setAttributedAlternateTitle_(title)
        self.addSubview_(self.card)
        self.beaver = BeaverView.alloc().initWithFrame_(AK.NSMakeRect(0,0,64,77))
        self.beaver.configure()
        self.addSubview_(self.beaver)
        self.animating = False
        self.render()

    def acceptsFirstResponder(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def resetCursorRects(self):
        self.addCursorRect_cursor_(self.bounds(), AK.NSCursor.crosshairCursor())
        if not self.card.isHidden():
            self.addCursorRect_cursor_(self.card.frame(), AK.NSCursor.arrowCursor())

    def approve_(self, sender):
        self.controller.approve()

    def cancel_(self, sender):
        self.controller.cancel()

    def cancelOperation_(self, sender):
        self.controller.cancel()

    def keyDown_(self, event):
        if event.keyCode() == 53:
            self.controller.cancel()
        else:
            # Keep unrelated keystrokes inside selection mode, without invoking
            # browser shortcuts or altering the user's underlying document.
            objc.super(SelectionView, self).keyDown_(event)

    @objc.python_method
    def handle_mouse(self, action):
        try:
            action()
        except Exception:
            LOG.exception('Selection interaction failed; removing the overlay')
            self.controller.cancel()

    def mouseDown_(self, event):
        self.handle_mouse(lambda: self.controller.begin(self.display, mouse_point()))

    def mouseDragged_(self, event):
        self.handle_mouse(lambda: self.controller.move(mouse_point()))

    def mouseUp_(self, event):
        self.handle_mouse(lambda: self.controller.finish(mouse_point()))

    @objc.python_method
    def render(self):
        state = self.controller.selection
        owns = state.display is not None and state.display.identifier == self.display.identifier
        rect = state.rect if owns else None
        Q.CATransaction.begin()
        Q.CATransaction.setDisableActions_(True)
        try:
            if rect is not None and rect.width > 0 and rect.height > 0:
                local = AK.NSMakeRect(rect.x - self.display.bounds.x, rect.y - self.display.bounds.y,
                                      rect.width, rect.height)
                radius = min(style.RADIUS, rect.width / 2, rect.height / 2)
                path = Q.CGPathCreateWithRoundedRect(local, radius, radius, None)
            else:
                path = None
            self.halo.setPath_(path)
            self.border.setPath_(path)
        finally:
            Q.CATransaction.commit()
        selected = state.phase is Phase.SELECTED and owns
        animate = selected and not AK.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()
        if animate and not self.animating:
            animation = Q.CABasicAnimation.animationWithKeyPath_('lineDashPhase')
            animation.setFromValue_(0.0)
            animation.setToValue_(-sum(style.DASH))
            animation.setDuration_(style.DASH_DURATION)
            animation.setRepeatCount_(float('inf'))
            self.border.addAnimation_forKey_(animation, 'amillum.dashes')
        elif not animate:
            self.border.removeAllAnimations()
        self.animating = animate
        show_card = selected or (state.display is None and self.display.identifier == self.controller.initial_display)
        self.card.setHidden_(not show_card)
        if show_card:
            self.label.setStringValue_('Want me to help with this? Read locally first.' if selected else 'Drag to select · Amillum')
            self.read_button.setHidden_(not selected or self.controller.on_approve is None)
            bounds = self.display.bounds
            x = (bounds.width - style.CARD_WIDTH) / 2
            y = bounds.height - 82
            if selected:
                x = rect.x - bounds.x + rect.width - style.CARD_WIDTH
                y = rect.y - bounds.y - style.CARD_HEIGHT - 12
                if y < style.EDGE_MARGIN:
                    y = rect.y - bounds.y + rect.height + 12
            x = max(style.EDGE_MARGIN, min(x, bounds.width - style.CARD_WIDTH - style.EDGE_MARGIN))
            y = max(style.EDGE_MARGIN, min(y, bounds.height - style.CARD_HEIGHT - style.EDGE_MARGIN))
            self.card.setFrameOrigin_(AK.NSMakePoint(x, y))
        bounds=self.display.bounds
        if selected:
            x=rect.x-bounds.x+rect.width/2-32
            y=rect.y-bounds.y+rect.height-7
            x=max(0,min(x,bounds.width-64)); y=max(0,min(y,bounds.height-77))
            # Keep the mascot away from the approval controls near screen edges.
            if AK.NSIntersectsRect(AK.NSMakeRect(x,y,64,77),self.card.frame()):
                x=max(0,min(rect.x-bounds.x-66,bounds.width-64))
            self.beaver.setFrameOrigin_(AK.NSMakePoint(x,y))
        elif show_card:
            origin=self.card.frame().origin
            self.beaver.setFrameOrigin_(AK.NSMakePoint(max(0,origin.x-66),origin.y))
        self.beaver.show_state('asking' if selected else 'curious',show_card)
        if self.window():
            self.window().invalidateCursorRectsForView_(self)

    @objc.python_method
    def dispose(self):
        self.beaver.dispose()
        self.border.removeAllAnimations()
        self.halo.setPath_(None)
        self.border.setPath_(None)
        self.controller = None


class Overlay:
    def __init__(self, on_approve=None):
        self.on_approve = on_approve
        self.selection = Selection()
        self.anchor = MascotAnchor()
        self.panels = []
        self.previous_app = None
        self.previous_key_window = None
        self.initial_display = None

    def activate(self):
        if not self.selection.activate():
            return
        self.previous_app = AK.NSWorkspace.sharedWorkspace().frontmostApplication()
        self.previous_key_window = AK.NSApp.keyWindow()
        try:
            available = displays()
            if not available:
                raise RuntimeError('No display is available for selection.')
            pointer = mouse_point()
            chosen = next((d for d in available if d.bounds.contains(pointer)), available[0])
            self.initial_display = chosen.identifier
            for display in available:
                b = display.bounds
                panel = SelectionPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                    AK.NSMakeRect(b.x, b.y, b.width, b.height),
                    AK.NSWindowStyleMaskBorderless | AK.NSWindowStyleMaskNonactivatingPanel,
                    AK.NSBackingStoreBuffered, False)
                self.panels.append(panel)
                panel.setReleasedWhenClosed_(False)
                panel.setTitle_('Amillum selection')
                panel.setOpaque_(False)
                panel.setBackgroundColor_(AK.NSColor.clearColor())
                panel.setHasShadow_(False)
                panel.setLevel_(AK.NSStatusWindowLevel + 1)
                panel.setHidesOnDeactivate_(False)
                panel.setFloatingPanel_(True)
                panel.setBecomesKeyOnlyIfNeeded_(False)
                panel.setAcceptsMouseMovedEvents_(True)
                panel.setIgnoresMouseEvents_(False)
                panel.setCollectionBehavior_(AK.NSWindowCollectionBehaviorCanJoinAllSpaces |
                                              AK.NSWindowCollectionBehaviorFullScreenAuxiliary |
                                              AK.NSWindowCollectionBehaviorStationary |
                                              AK.NSWindowCollectionBehaviorIgnoresCycle)
                view = SelectionView.alloc().initWithFrame_(AK.NSMakeRect(0, 0, b.width, b.height))
                view.configure(self, display)
                panel.setContentView_(view)
                panel.orderFrontRegardless()
                panel.makeFirstResponder_(view)
            active = next(panel for panel in self.panels if panel.contentView().display.identifier == chosen.identifier)
            active.makeKeyAndOrderFront_(None)
            AK.NSCursor.crosshairCursor().set()
        except Exception:
            self.cancel()
            raise

    def begin(self, display, point):
        if self.selection.begin(display, point):
            for panel in self.panels:
                if panel.contentView().display.identifier == display.identifier:
                    panel.makeKeyAndOrderFront_(None)
                    panel.makeFirstResponder_(panel.contentView())
            self.render()

    def move(self, point):
        self.selection.move(point)
        self.render()

    def finish(self, point):
        if self.selection.finish(point):
            self.anchor.update(self.selection.rect)
        self.render()

    def render(self):
        for panel in self.panels:
            panel.contentView().render()

    def approve(self):
        if self.selection.phase is not Phase.SELECTED or self.on_approve is None:
            return
        rect, application = self.selection.rect, self.previous_app
        callback = self.on_approve
        self.cancel(restore_focus=False)
        callback(rect, application)

    def cancel(self, restore_focus=True):
        previous_app, previous_window = self.previous_app, self.previous_key_window
        was_active = self.selection.phase is not Phase.IDLE
        self.selection.cancel()
        self.anchor.update(None)
        # Clear state before disposing so repeated notifications are harmless.
        panels, self.panels = self.panels, []
        self.previous_app = self.previous_key_window = self.initial_display = None
        for panel in panels:
            try:
                panel.orderOut_(None)
                view = panel.contentView()
                if isinstance(view, SelectionView):
                    view.dispose()
                panel.close()
            except Exception:
                LOG.exception('Could not dispose a selection panel')
        if was_active:
            AK.NSCursor.arrowCursor().set()
        if restore_focus and was_active:
            current = AK.NSWorkspace.sharedWorkspace().frontmostApplication()
            # Never steal focus from a different app the user just switched to.
            if previous_app and current and current.processIdentifier() in (previous_app.processIdentifier(), AK.NSProcessInfo.processInfo().processIdentifier()):
                if previous_app.processIdentifier() == AK.NSProcessInfo.processInfo().processIdentifier():
                    if previous_window and previous_window.isVisible():
                        previous_window.makeKeyAndOrderFront_(None)
                elif not previous_app.isTerminated():
                    previous_app.activateWithOptions_(0)
