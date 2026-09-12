"""Permission checks are separate from user-initiated permission requests."""


def accessibility_granted():
    import ApplicationServices as AX
    return bool(AX.AXIsProcessTrusted())


def request_accessibility():
    """Called only after the user presses the explicit setup button."""
    import ApplicationServices as AX
    return bool(AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True}))



def capture_granted():
    import Quartz
    return bool(Quartz.CGPreflightScreenCaptureAccess())


def request_capture():
    import Quartz
    return bool(Quartz.CGRequestScreenCaptureAccess())
