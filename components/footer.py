from nicegui import ui

from components.config import icon_src


def footer():
    with ui.element("footer").classes("amicus-footer"):
        ui.html(
            f"""
            <div class="amicus-footer-inner">

                <div class="amicus-footer-top">

                    <div class="amicus-footer-brand">

                        <div class="amicus-footer-logo">
                            <img
                                src="{icon_src}"
                                alt="Amicus"
                            >
                            <span>Amicus</span>
                        </div>

                        <p>
                            Clear legal understanding,<br>
                            in every language.
                        </p>

                    </div>

                    <div class="amicus-footer-columns">

                        <div class="amicus-footer-column">

                            <div class="amicus-footer-heading">
                                Product
                            </div>

                            <a href="/analyze">
                                Analyze a document
                            </a>

                            <a href="/#product-demo">
                                See Amicus in action
                            </a>

                            <a href="/#faq">
                                FAQ
                            </a>

                        </div>

                        <div class="amicus-footer-column">

                            <div class="amicus-footer-heading">
                                Resources
                            </div>

                            <a href="/#product-demo">
                                How it works
                            </a>

                            <a href="/#use-cases">
                                Use cases
                            </a>

                            <a href="/analyze">
                                Get started
                            </a>

                        </div>

                        <div class="amicus-footer-column">

                            <div class="amicus-footer-heading">
                                Amicus
                            </div>

                            <a href="/analyze">
                                Analysis tool
                            </a>

                            <a href="/#faq">
                                Privacy
                            </a>

                            <a href="/#faq">
                                Disclaimer
                            </a>

                        </div>

                    </div>

                </div>

                <div class="amicus-footer-status">

                    <span class="amicus-status-dot"></span>

                    All systems operational

                </div>

                <div class="amicus-footer-bottom">

                    <span class="amicus-footer-copy">
                        © 2026 Amicus. All rights reserved.
                    </span>

                    <div class="amicus-footer-socials">

                        <a
                            href="#"
                            aria-label="Instagram"
                        >
                            <i class="fa-brands fa-instagram"></i>
                        </a>

                        <a
                            href="#"
                            aria-label="GitHub"
                        >
                            <i class="fa-brands fa-github"></i>
                        </a>

                    </div>

                </div>

                <div class="amicus-footer-disclaimer">
                    Amicus provides informational insights and does not
                    constitute official legal advice.
                </div>

            </div>
            """,
            sanitize=False
        )