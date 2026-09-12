"""Persistent desktop presence; contextual suggestions reuse the same menu."""
import AppKit as AK
from native.macos.mascot import native_image


class IndicatorTarget(AK.NSObject):
    def select_(self, sender):
        self.owner.activate()

    def open_(self, sender):
        self.owner.open_workspace()

    def settings_(self, sender):
        self.owner.open_settings()

    def quit_(self, sender):
        self.owner.quit_app()


class ContextIndicator:
    def __init__(self, activate):
        self.activate = activate
        self.item = None
        self.target = IndicatorTarget.alloc().init()
        self.target.owner = self
        self.label = None
        self.persistent = False

    def start(self, open_workspace, open_settings, quit_app):
        self.open_workspace = open_workspace
        self.open_settings = open_settings
        self.quit_app = quit_app
        self.persistent = True
        self.render()

    def update(self, suggestion):
        label = suggestion.get('label') if suggestion else None
        if label != self.label:
            self.label = label
            self.render()

    def render(self):
        if not self.persistent and not self.label:
            self.remove()
            return
        if self.item is None:
            self.item = AK.NSStatusBar.systemStatusBar().statusItemWithLength_(AK.NSVariableStatusItemLength)
        icon=native_image('found' if self.label else 'idle').copy()
        icon.setSize_(AK.NSMakeSize(23,27))
        self.item.button().setImage_(icon)
        self.item.button().setTitle_('')
        self.item.button().setToolTip_('Amillum — ' + ('possible legal document; no document text read' if self.label else 'Open workspace or settings'))
        menu = AK.NSMenu.alloc().init()

        def action(title, selector):
            item = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, '')
            item.setTarget_(self.target)
            menu.addItem_(item)

        if self.persistent:
            action('Open Amillum', 'open:')
            action('Settings…', 'settings:')
            menu.addItem_(AK.NSMenuItem.separatorItem())
        if self.label:
            title = AK.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Possible ' + self.label.lower(), None, '')
            title.setEnabled_(False)
            menu.addItem_(title)
        action('Select a section to review…', 'select:')
        if self.persistent:
            menu.addItem_(AK.NSMenuItem.separatorItem())
            action('Quit Amillum', 'quit:')
        self.item.setMenu_(menu)

    def clear(self):
        self.update(None)

    def remove(self):
        if self.item is not None:
            AK.NSStatusBar.systemStatusBar().removeStatusItem_(self.item)
        self.item = None

    def close(self):
        self.remove()
        self.label = None
        self.persistent = False
        self.target.owner = None
