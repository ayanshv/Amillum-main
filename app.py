import sys
from pathlib import Path
from multiprocessing import freeze_support

freeze_support() 

from nicegui import ui, app


if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    ROOT_DIR = Path(sys._MEIPASS).resolve()
else:
    ROOT_DIR = Path(__file__).resolve().parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))



app.add_static_files(
    '/images',
    str(ROOT_DIR / 'assets')
)

app.add_static_files(
    '/icons',
    str(ROOT_DIR / 'icons')
)

app.add_static_files(
    '/styles',
    str(ROOT_DIR / 'styles')
)



ui.add_head_html('<link rel="stylesheet" href="/styles/styles.css?v=native-20260911">', shared=True)


# Configure on import too: NiceGUI spawns a separate PyWebView process.
from native import configure_desktop
configure_desktop(app)

from screens.home import home
from screens.analysis import analyze
from screens.info import info
from screens.settings import settings
from screens.context import context
from components.errors import install_errors
install_errors()



if __name__ in ("__main__", "__mp_main__"):
    ui.run(
        title="Amillum",
        window_size=(1080, 740),
        favicon=str(ROOT_DIR / 'icons' / 'AmicusIcon.ico'), # Safe file system fallback path
        native=True,
        reload=False
    )
