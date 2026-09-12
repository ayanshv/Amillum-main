"""Compact result-only AppKit panel. Receives no screenshots or extracted text."""
import AppKit as AK
from native.macos.mascot import BeaverView
from services.contextual_analysis import validate_result


class PanelTarget(AK.NSObject):
    def full_(self,sender):
        self.owner.open_full()
    def ask_(self,sender):
        self.owner.open_ask()
    def windowShouldClose_(self,window):
        window.orderOut_(None)
        if self.owner.beaver:self.owner.beaver.show_state('success',False)
        return False


class ContextPanel:
    def __init__(self,open_full,open_ask):
        self.open_full=open_full; self.open_ask=open_ask
        self.window=None; self.seen=None; self.closed=False
        self.target=PanelTarget.alloc().init(); self.target.owner=self
        self.beaver=None

    def build(self):
        window=AK.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            AK.NSMakeRect(0,0,420,570),AK.NSWindowStyleMaskTitled|AK.NSWindowStyleMaskClosable,
            AK.NSBackingStoreBuffered,False)
        self.window=window
        window.setTitle_('Amillum · Your selection')
        window.setReleasedWhenClosed_(False)
        window.setAppearance_(AK.NSAppearance.appearanceNamed_(AK.NSAppearanceNameAqua))
        window.setBackgroundColor_(AK.NSColor.colorWithSRGBRed_green_blue_alpha_(.97,.98,.99,1))
        window.setLevel_(AK.NSFloatingWindowLevel)
        window.setHidesOnDeactivate_(False)
        window.setDelegate_(self.target)
        root=window.contentView()
        self.beaver=BeaverView.alloc().initWithFrame_(AK.NSMakeRect(18,499,48,58))
        self.beaver.configure('success'); root.addSubview_(self.beaver)
        title=AK.NSTextField.labelWithString_('AMILLUM')
        title.setFont_(AK.NSFont.systemFontOfSize_weight_(14,AK.NSFontWeightSemibold))
        title.setFrame_(AK.NSMakeRect(78,518,300,24)); root.addSubview_(title)
        scroll=AK.NSScrollView.alloc().initWithFrame_(AK.NSMakeRect(20,99,380,398))
        scroll.setHasVerticalScroller_(True); scroll.setDrawsBackground_(False)
        self.text=AK.NSTextView.alloc().initWithFrame_(AK.NSMakeRect(0,0,360,398))
        self.text.setEditable_(False); self.text.setSelectable_(True)
        self.text.setDrawsBackground_(False); self.text.setVerticallyResizable_(True)
        self.text.setHorizontallyResizable_(False)
        self.text.setAutoresizingMask_(AK.NSViewWidthSizable)
        self.text.textContainer().setWidthTracksTextView_(True)
        self.text.setTextContainerInset_(AK.NSMakeSize(4,8))
        self.text.setFont_(AK.NSFont.systemFontOfSize_(13))
        self.text.setTextColor_(AK.NSColor.colorWithSRGBRed_green_blue_alpha_(.12,.20,.30,1))
        scroll.setDocumentView_(self.text); root.addSubview_(scroll)
        for label,selector,x,width in [('Open Full Analysis','full:',20,185),('Ask Amillum','ask:',216,182)]:
            button=AK.NSButton.buttonWithTitle_target_action_(label,self.target,selector)
            button.setBezelStyle_(AK.NSBezelStyleRounded)
            button.setFrame_(AK.NSMakeRect(x,57,width,30)); root.addSubview_(button)
        workbench=AK.NSButton.buttonWithTitle_target_action_('Add to Workbench',None,None)
        workbench.setBezelStyle_(AK.NSBezelStyleRounded); workbench.setEnabled_(False)
        workbench.setToolTip_('Workbench is not available yet. Nothing has been saved.')
        workbench.setFrame_(AK.NSMakeRect(20,18,180,30)); root.addSubview_(workbench)
        note=AK.NSTextField.labelWithString_('Workbench coming later')
        note.setFont_(AK.NSFont.systemFontOfSize_(10))
        note.setFrame_(AK.NSMakeRect(216,22,184,20)); root.addSubview_(note)

    def update(self,snapshot):
        if self.closed:return
        result=snapshot.get('result')
        if not result:
            if self.window:
                self.window.orderOut_(None)
                self.text.setString_('')
            if self.beaver:self.beaver.show_state('success',False)
            return
        if snapshot.get('revision')==self.seen:return
        try:validate_result(result)
        except ValueError:return
        if self.window is None:self.build()
        self.seen=snapshot['revision']
        text=('SUMMARY\n'+result['summary']+'\n\nATTENTION · '+result['attention']+
              '\nReview priority, not a legal determination.\n\n'+
              '\n\n'.join(title+'\n'+'\n'.join('• '+v for v in result[key]) for title,key in
                          [('WHY IT MATTERS','reasons'),('QUESTIONS TO CONSIDER','questions'),('NEXT STEPS','next_steps')]))
        self.text.setString_(text)
        self.text.scrollRangeToVisible_((0,0))
        frame=AK.NSScreen.mainScreen().visibleFrame()
        self.window.setFrameOrigin_(AK.NSMakePoint(max(frame.origin.x,frame.origin.x+frame.size.width-444),
                                                  max(frame.origin.y,frame.origin.y+frame.size.height-610)))
        self.beaver.show_state('success')
        self.window.orderFrontRegardless()

    def close(self):
        self.closed=True
        if self.beaver:self.beaver.dispose()
        if self.window:
            self.window.setDelegate_(None); self.window.close()
        self.target.owner=None
