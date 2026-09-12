"""Native startup entry must be importable without initializing AppKit."""


def start_native():
    """PyWebView calls this on a worker; AppKit installation belongs on main."""
    from PyObjCTools import AppHelper
    from native.macos.runtime import install
    AppHelper.callAfter(install)

