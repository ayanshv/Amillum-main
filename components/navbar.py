from nicegui import ui

from components.config import icon_src


def navbar():
    with ui.html(
        f"""
        <div class="rai-nav">

            <div
                class="brand"
                onclick="window.location.href='/'"
            >
                <img
                    src="{icon_src}"
                    style="
                        width: 34px;
                        height: 34px;
                        border-radius: 10px;
                        object-fit: cover;
                        background: #101010;
                    "
                    alt="Amicus"
                >

                <div class="brand-name">
                    Amicus
                </div>
            </div>

            <div class="nav-links">

                <a
                    class="hide-sm"
                    href="/#use-cases"
                >
                    Use cases
                </a>

                <a
                    class="hide-sm"
                    href="/#faq"
                >
                    FAQ
                </a>

                <a
                    class="nav-cta"
                    href="/analyze"
                >
                    Analyze a document
                </a>

            </div>

        </div>
        """,
        sanitize=False
    ):
        pass