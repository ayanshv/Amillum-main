from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HOOK = Path(__file__).resolve().parents[1] / 'native' / 'macos' / 'frozen_hook.py'


class FrozenBootstrapTests(unittest.TestCase):
    def test_spawn_restores_native_start_callback_without_appkit(self):
        app = SimpleNamespace(native=SimpleNamespace(start_args={}))
        with patch('sys.platform', 'darwin'), patch('sys.argv', ['Amillum', '--multiprocessing-fork', 'pipe_handle=22']), patch.dict('sys.modules', {'nicegui': SimpleNamespace(app=app)}):
            runpy.run_path(str(HOOK))
        from native.macos import start_native
        self.assertIs(app.native.start_args['func'], start_native)

    def test_main_and_resource_tracker_do_not_load_nicegui(self):
        for argv in (['Amillum'], ['Amillum', '-c', 'from multiprocessing.resource_tracker import main;main(12)']):
            with patch('sys.platform', 'darwin'), patch('sys.argv', argv), patch('native.configure_desktop') as configure:
                runpy.run_path(str(HOOK))
                configure.assert_not_called()


if __name__ == '__main__':
    unittest.main()

