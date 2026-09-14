"""Startup wiring regression: route availability and secure native session setup."""
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

class AppEntryTests(unittest.TestCase):
    def test_secure_startup_routes_and_run_options(self):
        from nicegui import app
        with patch('native.configure_desktop'),patch('services.supabase.storage_secret',return_value='synthetic-test-secret'),patch('nicegui.ui.run') as run,patch.dict(app.native.start_args,{},clear=True):
            runpy.run_path(str(Path(__file__).resolve().parents[1]/'app.py'),run_name='__main__')
            options=run.call_args.kwargs
            self.assertEqual(options['host'],'127.0.0.1')
            self.assertEqual(options['storage_secret'],'synthetic-test-secret')
            self.assertTrue(options['native']);self.assertFalse(options['reload'])
            self.assertFalse(app.native.start_args['private_mode'])
            paths={route.path for route in app.routes}
            self.assertTrue({'/auth','/account','/workbench','/settings','/context'}.issubset(paths))
