"""PyInstaller runtime hook: restore native configuration before spawn dispatch.

In a frozen NiceGUI child, freeze_support dispatches directly to _open_window;
app.py's normal import-time configuration does not run. Configure only that spawn
path, before the entry point calls freeze_support. Do not initialize AppKit here.
"""

import sys

if sys.platform == 'darwin' and '--multiprocessing-fork' in sys.argv:
    from nicegui import app
    from native import configure_desktop
    configure_desktop(app)

