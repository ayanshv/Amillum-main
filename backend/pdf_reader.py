import pdfplumber
import os

def extract_pdf(pdf_file):
    reader = pdfplumber.open(pdf_file)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text+=extracted

    return text.strip()
