from decimal import Decimal

def formatear_pesos(valor, decimales=0):
    """
    Formatea números al formato argentino.
    Ej:
    244000 -> 244.000
    244000.5 -> 244.000,50
    """
    if valor is None:
        return "0"

    if isinstance(valor, Decimal):
        valor = float(valor)

    if decimales == 0:
        return f"{valor:,.0f}".replace(",", ".")
    else:
        return (
            f"{valor:,.{decimales}f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )