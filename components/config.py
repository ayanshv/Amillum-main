import base64
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

BASE_DIR = ROOT_DIR

ICON_PATH = BASE_DIR / "icons" / "AmicusIcon.png"
BACKGROUND_PATH = BASE_DIR / "images" / "bg.png"

BG_IMAGE_URL = "/images/bg.png"


def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return ""


icon_base64 = get_base64_image(ICON_PATH)

icon_src = (
    f"data:image/png;base64,{icon_base64}"
    if icon_base64
    else ""
)