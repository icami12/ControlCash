import re
from datetime import date, timedelta

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

DIAS = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5,
    "domingo": 6,
}

from datetime import date, timedelta
import re

def resolver_fecha(text, data=None):
    texto = text.lower()
    hoy = date.today()

    # Relativos simples
    if "anteayer" in texto:
        return hoy - timedelta(days=2)

    if "ayer" in texto:
        return hoy - timedelta(days=1)

    if "hoy" in texto:
        return hoy

    # Día + mes (ANTES que días de semana)
    fecha = detectar_dia_mes(texto, hoy)
    if fecha:
        return fecha

    # Fecha numérica
    fecha = detectar_fecha_numerica(texto, hoy)
    if fecha:
        return fecha

    # Día de semana pasado explícito
    for dia, weekday in DIAS.items():
        if f"{dia} pasado" in texto or f"el {dia} pasado" in texto:
            return ultimo_dia_semana(weekday, hoy)

    # Día de semana genérico → último ocurrido
    for dia, weekday in DIAS.items():
        if re.search(rf'\b{dia}\b', texto):
            return ultimo_dia_semana(weekday, hoy)

    # Fallback desde data
    if data and data.get("fecha"):
        try:
            return date.fromisoformat(data["fecha"])
        except Exception:
            pass

    return hoy

def ultimo_dia_semana(target_weekday, hoy):
    delta = (hoy.weekday() - target_weekday) % 7
    return hoy - timedelta(days=delta or 7)

def detectar_dia_mes(texto, hoy):
    match = re.search(r'(\d{1,2})\s+de\s+([a-záéíóú]+)', texto)
    if not match:
        return None

    dia = int(match.group(1))
    mes = MESES.get(match.group(2))
    if not mes:
        return None

    fecha = date(hoy.year, mes, dia)

    # Solo ir al año anterior si la fecha todavía NO ocurrió este año
    if fecha > hoy and mes != hoy.month:
        fecha = date(hoy.year - 1, mes, dia)

    return fecha

def detectar_fecha_numerica(texto, hoy):
    match = re.search(r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?', texto)
    if not match:
        return None

    dia, mes, año = match.groups()
    dia, mes = int(dia), int(mes)

    if año:
        año = int(año)
        if año < 100:
            año += 2000
    else:
        año = hoy.year

    try:
        fecha = date(año, mes, dia)
        if not año and fecha > hoy:
            fecha = date(año - 1, mes, dia)
        return fecha
    except ValueError:
        return None