import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extraer_texto_imagen(ruta):
    img = Image.open(ruta)
    texto = pytesseract.image_to_string(img, lang="spa")
    return texto