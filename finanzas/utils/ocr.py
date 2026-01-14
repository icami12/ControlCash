import pytesseract
from PIL import Image
from io import BytesIO

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extraer_texto_imagen_bytes(img_bytes: bytes) -> str:
    """
    Extrae texto OCR desde una imagen en memoria (bytes).
    """
    img = Image.open(BytesIO(img_bytes))
    texto = pytesseract.image_to_string(img, lang="spa")
    return " ".join(texto.split())