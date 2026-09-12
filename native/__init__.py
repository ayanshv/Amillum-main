"""Optional desktop capabilities; importing this package has no OS side effects."""

import sys
import multiprocessing


def configure_desktop(app):
    """Configure NiceGUI before ui.run, including when multiprocessing reimports it."""
    if sys.platform == 'darwin':
        from native.macos import start_native
        app.native.start_args['func'] = start_native
        if (multiprocessing.current_process().name == 'MainProcess'
                and '--multiprocessing-fork' not in sys.argv):
            from native.bridge import configure_server
            configure_server(app)
