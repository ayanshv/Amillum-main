"""Non-interactive AppKit sprite view. No screen or input access."""
from functools import lru_cache
import AppKit as AK
import objc
from core.mascot import png, ROWS


@lru_cache(maxsize=128)
def native_image(state, index=0):
    data=png(state,index)
    return AK.NSImage.alloc().initWithData_(AK.NSData.dataWithBytes_length_(data,len(data)))


class BeaverView(AK.NSView):
    @objc.python_method
    def configure(self, state='idle'):
        self.state=state
        self.index=0
        self.timer=None
        self.setAccessibilityElement_(False)

    def hitTest_(self, point):
        return None  # Dragging and button clicks belong to the selection overlay.

    @objc.python_method
    def show_state(self, state, visible=True):
        if state != self.state:
            self.state=state
            self.index=0
        self.setHidden_(not visible)
        motion=not AK.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion()
        if visible and motion and self.timer is None:
            self.timer=AK.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(.18,self,'tick:',None,True)
            AK.NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer,AK.NSRunLoopCommonModes)
        elif (not visible or not motion) and self.timer is not None:
            self.timer.invalidate(); self.timer=None
            self.index=0
        self.setNeedsDisplay_(True)

    def tick_(self, timer):
        if AK.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion():
            self.show_state(self.state,not self.isHidden())
            return
        self.index=(self.index+1)%len(ROWS[self.state][0])
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        AK.NSGraphicsContext.currentContext().setImageInterpolation_(AK.NSImageInterpolationNone)
        native_image(self.state,self.index).drawInRect_fromRect_operation_fraction_(
            self.bounds(),AK.NSZeroRect,AK.NSCompositingOperationSourceOver,1)

    @objc.python_method
    def dispose(self):
        if self.timer is not None:
            self.timer.invalidate(); self.timer=None
