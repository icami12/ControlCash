from django.utils import timezone
from datetime import timedelta

MAX_STRIKES = 2
TIEMPO_BLOQUEO = timedelta(minutes=15)

def ia_bloqueada(perfil):
    if perfil.bloqueo_ia_hasta and timezone.now() < perfil.bloqueo_ia_hasta:
        return True
    return False


def registrar_no_transaccion(perfil):
    perfil.strikes_no_transaccion += 1

    if perfil.strikes_no_transaccion >= MAX_STRIKES:
        perfil.bloqueo_ia_hasta = timezone.now() + TIEMPO_BLOQUEO
        perfil.strikes_no_transaccion = 0  # reset luego del bloqueo

    perfil.save()


def registrar_transaccion_valida(perfil):
    perfil.strikes_no_transaccion = 0
    perfil.bloqueo_ia_hasta = None
    perfil.save()