from nicegui import ui

from components.config import BG_IMAGE_URL


def image_bg():
    ui.html(
        f"""
        <img
            class="amicus-img-bg"
            src="{BG_IMAGE_URL}"
            alt="Background"
        >
        <div class="amicus-scrim"></div>
        """,
        sanitize=False
    )