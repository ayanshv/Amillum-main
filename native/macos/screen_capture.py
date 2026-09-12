"""One approved rectangle, one window, one image. No recording stream or files."""
import threading
from native.macos.region_reader import ReadBlocked, contains


def capture_region(pid, rect, valid):
    import Quartz as Q
    import ScreenCaptureKit as SC
    if not Q.CGPreflightScreenCaptureAccess():
        raise ReadBlocked('Local OCR needs macOS Screen Recording permission. Open Privacy & control → Set up region capture, grant permission, then select again.')
    if not valid():
        raise ReadBlocked('Selection cancelled. Nothing was captured.')
    event, output = threading.Event(), {}
    expired = threading.Event()
    approval_valid = valid
    valid = lambda: not expired.is_set() and approval_valid()

    def finished(image, error):
        if image is not None and valid():
            output['image'] = image
        else:
            output['error'] = 'The selected window could not be captured. Check permission and try again.'
        event.set()

    def available(content, error):
        try:
            if error or content is None or not valid():
                raise ReadBlocked('Screen capture is unavailable or the selection was cancelled.')
            # Match the frontmost on-screen window owned by the approved application.
            windows = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly, Q.kCGNullWindowID)
            window_id = None
            for info in windows:
                if info.get(Q.kCGWindowLayer, 0) != 0:
                    continue
                bounds = info.get(Q.kCGWindowBounds, {})
                b = tuple(bounds.get(k, 0) for k in ('X', 'Y', 'Width', 'Height'))
                from native.macos.region_reader import intersects
                if not intersects(b, rect):
                    continue
                if info.get(Q.kCGWindowOwnerPID) != pid or not contains(b, rect):
                    raise ReadBlocked('Another window overlaps the selection. Bring the document forward and select again.')
                window_id = info.get(Q.kCGWindowNumber)
                break
            window = next((w for w in content.windows() if w.windowID() == window_id), None)
            if window is None:
                raise ReadBlocked('The selected document window is no longer available.')
            frame = window.frame()
            x, y, width, height = rect
            source = (x-frame.origin.x, y-frame.origin.y, width, height)
            if not contains((0, 0, frame.size.width, frame.size.height), source):
                raise ReadBlocked('The document moved. Select again.')
            display = next((d for d in content.displays()
                            if contains((d.frame().origin.x,d.frame().origin.y,d.frame().size.width,d.frame().size.height),rect)),None)
            if display is None:
                raise ReadBlocked('Keep the selected region on one display.')
            d=display.frame()
            config = SC.SCStreamConfiguration.alloc().init()
            # Single-window filters ignore sourceRect. A display filter with one
            # included window honours this display-relative crop at capture time.
            config.setSourceRect_(Q.CGRectMake(x-d.origin.x,y-d.origin.y,width,height))
            config.setWidth_(int(width * 2))
            config.setHeight_(int(height * 2))
            config.setShowsCursor_(False)
            config.setIgnoreShadowsSingleWindow_(True)
            filter_ = SC.SCContentFilter.alloc().initWithDisplay_includingWindows_(display,[window])
            if not valid():
                raise ReadBlocked('Selection cancelled.')
            SC.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(filter_, config, finished)
        except Exception as exc:
            output['error'] = str(exc) if isinstance(exc, ReadBlocked) else 'Region capture failed. Please select again.'
            event.set()

    SC.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(True, True, available)
    if not event.wait(12):
        expired.set()
        raise ReadBlocked('Region capture timed out. Try a smaller region.')
    if not valid():
        raise ReadBlocked('Selection cancelled. The capture was discarded.')
    if 'image' not in output:
        raise ReadBlocked(output.get('error', 'Region capture was cancelled.'))
    return output['image']
