from PIL import Image
import numpy as np
import easyocr

def load_ocr_reader():
     return easyocr.Reader(['en'])

def extract_text_from_image(camera_buffer):
    img = Image.open(camera_buffer)
    img_array = np.array(img)
    reader = load_ocr_reader()
    results = reader.readtext(img_array)
    extracted_lines = [text[1] for text in results]
    return "\n".join(extracted_lines)



