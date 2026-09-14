"""Non-activating suggestion surface; buttons never read or analyze content."""
import AppKit as AK
from PyObjCTools import AppHelper
from native.macos.mascot import native_image

class SuggestionTarget(AK.NSObject):
    def accept_(self,sender):self.owner.choose(True)
    def dismiss_(self,sender):self.owner.choose(False)

class SuggestionPanel:
    def __init__(self,respond):
        self.respond=respond;self.window=None;self.key=None;self.generation=0
        self.target=SuggestionTarget.alloc().init();self.target.owner=self

    def build(self):
        self.window=AK.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            AK.NSMakeRect(0,0,320,142),AK.NSWindowStyleMaskNonactivatingPanel|AK.NSWindowStyleMaskBorderless,AK.NSBackingStoreBuffered,False)
        self.window.setReleasedWhenClosed_(False)
        self.window.setLevel_(AK.NSFloatingWindowLevel)
        self.window.setHidesOnDeactivate_(False)
        self.window.setBecomesKeyOnlyIfNeeded_(True)
        self.window.setAppearance_(AK.NSAppearance.appearanceNamed_(AK.NSAppearanceNameAqua))
        self.window.setBackgroundColor_(AK.NSColor.colorWithSRGBRed_green_blue_alpha_(.97,.98,.99,1))
        self.window.setHasShadow_(True)
        root=self.window.contentView();root.setWantsLayer_(True);root.layer().setCornerRadius_(14)
        image=AK.NSImageView.alloc().initWithFrame_(AK.NSMakeRect(15,65,44,54))
        image.setImage_(native_image('asking'));root.addSubview_(image)
        label=AK.NSTextField.wrappingLabelWithString_("I think you’re working with\nsomething legal.")
        label.setFont_(AK.NSFont.systemFontOfSize_weight_(13,AK.NSFontWeightMedium))
        label.setTextColor_(AK.NSColor.colorWithSRGBRed_green_blue_alpha_(.12,.20,.30,1))
        label.setFrame_(AK.NSMakeRect(72,77,230,40));root.addSubview_(label)
        for title,selector,x in [('Take a look','accept:',72),('Not now','dismiss:',190)]:
            button=AK.NSButton.buttonWithTitle_target_action_(title,self.target,selector)
            button.setBezelStyle_(AK.NSBezelStyleRounded);button.setFrame_(AK.NSMakeRect(x,33,112,30));root.addSubview_(button)
        note=AK.NSTextField.labelWithString_('Choose a section next. Nothing sent to AI.')
        note.setFont_(AK.NSFont.systemFontOfSize_(10));note.setTextColor_(AK.NSColor.secondaryLabelColor())
        note.setFrame_(AK.NSMakeRect(17,10,290,16));root.addSubview_(note)

    def show(self,key):
        if self.key==key:return
        if self.window is None:self.build()
        self.key=key;self.generation+=1
        frame=AK.NSScreen.mainScreen().visibleFrame()
        self.window.setFrameOrigin_(AK.NSMakePoint(frame.origin.x+frame.size.width-338,frame.origin.y+frame.size.height-160))
        self.window.orderFrontRegardless()  # No activateIgnoringOtherApps / makeKeyWindow.
        AppHelper.callLater(12,self.expire,self.generation)

    def expire(self,generation):
        if generation==self.generation:self.choose(None)

    def choose(self,accepted):
        if self.key is None:return
        self.hide();self.respond(accepted)

    def hide(self):
        self.key=None;self.generation+=1
        if self.window:self.window.orderOut_(None)

    def close(self):
        self.hide()
        if self.window:self.window.close()
        self.target.owner=None
