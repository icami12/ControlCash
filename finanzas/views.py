from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from .models import Transaccion, Categoria, Perfil, Notificacion
from decimal import Decimal
from datetime import datetime, date, timedelta
import os, string, json, requests, random
import logging
from django.http import JsonResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
import re
import plotly.graph_objects as go
from plotly.offline import plot
from django.db.models.functions import TruncDay
import pandas as pd
from django.utils.timezone import now
from finanzas.utils.ocr import extraer_texto_imagen_bytes
from dotenv import load_dotenv
from openai import OpenAI
from finanzas.utils.fechas import resolver_fecha
from finanzas.utils.control_ia import (
    ia_bloqueada,
    registrar_no_transaccion,
    registrar_transaccion_valida
)
from finanzas.utils.formatos import formatear_pesos
from finanzas.utils.graficos import generar_grafico_balance

load_dotenv()
# Cargar también .env.local para permitir OPENAI_API_KEY local
load_dotenv(".env.local", override=True)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Logger de módulo
logger = logging.getLogger(__name__)

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
        # If form is invalid or authentication fails
        messages.error(request, 'Usuario/contraseña incorrecta')
        return render(request, 'finanzas/login.html', {'form': form})
    else:
        form = AuthenticationForm()
    return render(request, 'finanzas/login.html', {'form': form})

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, '¡Cuenta creada exitosamente!')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'finanzas/register.html', {'form': form})

@login_required
def dashboard(request):
    notificaciones = Notificacion.objects.filter(leido=False).order_by('-fecha')
    noti_count = notificaciones.count()

    movimientos_recientes = (
        Transaccion.objects
        .filter(usuario=request.user)
        .order_by('-fecha', '-id')[:5]
    )

    ingresos = Transaccion.objects.filter(
        usuario=request.user, tipo='ingreso'
    ).aggregate(total=Sum('cantidad'))['total'] or 0

    gastos = Transaccion.objects.filter(
        usuario=request.user, tipo='gasto'
    ).aggregate(total=Sum('cantidad'))['total'] or 0

    balance = ingresos - gastos

    chart_html = generar_grafico_balance(request.user)
    print("INGRESOS RAW:", ingresos, type(ingresos))
    print("GASTOS RAW:", gastos, type(gastos))
    print("BALANCE RAW:", balance, type(balance))

    context = {
        "transacciones": movimientos_recientes,
        "ingresos": formatear_pesos(ingresos),
        "gastos": formatear_pesos(gastos),
        "balance": formatear_pesos(balance),
        "chart": chart_html,
        "notificaciones": notificaciones,
        "noti_count": noti_count,
    }

    return render(request, "finanzas/dashboard.html", context)

def marcar_notificaciones_leidas(request):
    Notificacion.objects.filter(leido=False).update(leido=True)
    return JsonResponse({"ok": True})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def nuevo_registro(request):
    if request.method == "POST":
        # Tomar datos del formulario
        tipo = request.POST.get("tipo")
        cantidad = request.POST.get("cantidad")
        descripcion = request.POST.get("descripcion")
        categoria = request.POST.get("categoria")
        destino = request.POST.get("destino")
        fecha = request.POST.get("fecha")

        # Crear y guardar la transacción
        Transaccion.objects.create(
            usuario=request.user,
            tipo=tipo,
            cantidad=cantidad,
            descripcion=descripcion,
            categoria=categoria,
            destino=destino if destino else None,
            fecha=fecha
        )

        # Redirigir a dashboard u otra página
        return redirect("dashboard")

    # Si es GET, renderizamos el formulario
    categorias_fijas = ['Comida', 'Salario', 'Compras', 'Transferencias', 'Servicios','Ventas', 'Otros']
    return render(request, 'finanzas/nuevo_registro.html', {"categorias": categorias_fijas})

@login_required
def historial_transacciones(request):
    transacciones = Transaccion.objects.filter(usuario=request.user).order_by('-fecha', '-id')

    # Obtener categorías únicas de las transacciones del usuario para el filtro
    categorias = Transaccion.CATEGORIA_CHOICES

    # Filtros por fecha o categoría
    fecha_filtro = request.GET.get('fecha')
    categoria_filtro = request.GET.get('categoria')

    if fecha_filtro:
        transacciones = transacciones.filter(fecha=fecha_filtro)
    if categoria_filtro:
        transacciones = transacciones.filter(categoria=categoria_filtro)

    transacciones = transacciones[:20]

    context = {
        'transacciones': transacciones,
         "categorias": categorias,
    }
    return render(request, 'finanzas/historial_transacciones.html', context)


@csrf_exempt
def webhook(request):
    if request.method != "POST":
        return JsonResponse({"status": "invalid method"})

    data = json.loads(request.body)

    if "message" in data:
        # 📌 Si el usuario envía una FOTO → usar OCR
        if "photo" in data["message"]:
            chat_id = data["message"]["chat"]["id"]

            # Foto de mayor resolución
            file_id = data["message"]["photo"][-1]["file_id"]

            # Obtener info del archivo desde Telegram
            file_info = get_file_info(file_id)
            file_path = file_info["result"]["file_path"]
            url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

            # Descargar imagen en memoria
            img_bytes = requests.get(url).content

            texto = extraer_texto_imagen_bytes(img_bytes)

            if texto:
                try:
                    procesar_mensaje_usuario(chat_id, texto)
                except Exception as e:
                    send_message(chat_id, f"Error interno procesando OCR: {e}")
            else:
                send_message(chat_id, "No pude leer ningún texto en la imagen 😕")

            return JsonResponse({"status": "ok"})

        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Si es comando para vincular
        if text.startswith("/vincular"):
        # 1️⃣ Verificar si este chat YA está vinculado
            if Perfil.objects.filter(telegram_chat_id=chat_id).exists():
                send_message(
                    chat_id,
                    "📣 Este chat ya está vinculado a una cuenta de ControlCash.\n"
                    "Si necesitás cambiar la vinculación, desvincula este dispositivo desde la web."
                )
                return JsonResponse({"status": "ok"})

            # 2️⃣ Obtener código
            try:
                _, codigo = text.split(" ", 1)
                codigo = codigo.strip()
            except ValueError:
                send_message(chat_id, "Formato incorrecto. Usá: /vincular CODIGO")
                return JsonResponse({"status": "ok"})

            # 3️⃣ Validar código
            try:
                perfil = Perfil.objects.get(telegram_code=codigo)
            except Perfil.DoesNotExist:
                send_message(
                    chat_id,
                    "❌ Código inválido.\n"
                    "Respetá mayúsculas y números u obtené un código válido desde la web."
                )
                return JsonResponse({"status": "ok"})

            # Vincular
            perfil.telegram_chat_id = chat_id
            perfil.telegram_code = None
            perfil.save()
            nombre = perfil.user.username
            mensaje = f"Hola {nombre} 👋.Te vinculaste correctamente.\nDime la primer transacción que quieras que registre por favor."
            send_message(chat_id, mensaje)
            mensaje = "⚠️Recuerda detallar la fecha de la transacción, sino considero que es de hoy 😊.\nEnvía /ayuda para conocer qué comandos manejamos."
            send_message(chat_id, mensaje)
            return JsonResponse({"status": "ok"})
        elif text.strip() == "/ayuda":
            send_message(
                chat_id,
                "Comandos disponibles:\n"
                "/vincular - Vincular tu cuenta con ControlCash. Ej: /vincular 123456\n"
                "/ayuda - Mostrar este mensaje\n"
                "/saldo - Ver tu saldo actual\n"
                "Puedes escribir: 'gasté 20000 en comida el 24-10-25', 'hoy ingreso 150000 sueldo', o de la forma que quieras expresarte.0"
            )
            return JsonResponse({"status": "ok"})

        elif text.strip() == "/saldo":
            perfil = Perfil.objects.get(telegram_chat_id=chat_id)
            usuario = perfil.user

            ingresos = Transaccion.objects.filter(
                usuario=usuario,
                tipo='ingreso'
            ).aggregate(total=Sum('cantidad'))['total'] or Decimal('0')
            
            gastos = Transaccion.objects.filter(
                usuario=usuario,
                tipo='gasto'
            ).aggregate(total=Sum('cantidad'))['total'] or Decimal('0')
            
            balance = ingresos - gastos

            mensaje = (
                "💰 Saldo cta PESOS: "
                f"${formatear_pesos(balance)}\n\n"
                "📊 Estado de cuenta:\n"
                f"+ Ingresos: ${formatear_pesos(ingresos)}\n"
                f"- Gastos: ${formatear_pesos(gastos)}\n"
            )

            send_message(chat_id, mensaje)
            return JsonResponse({"status": "ok"})

        # Cualquier otro mensaje → verificar si está vinculado
        try:
            perfil = Perfil.objects.get(telegram_chat_id=chat_id)
        except Perfil.DoesNotExist:
            send_message(chat_id, "¡Hola!👋 Notamos que no estás vinculado al sistema ControlCash.\nEnvianos /vincular codigo_de_vinculacion para poder utilizar este bot.\nSi no tienes una cuenta puedes registrarte en https://terence-fibrotic-communicably.ngrok-free.dev/")
            return JsonResponse({"status": "ok"})

        # Usuario vinculado → procesar su mensaje
        # Ejemplo: solo repetimos
        try:
            procesar_mensaje_usuario(chat_id, text)
        except Exception as e:
            send_message(chat_id, f"Error interno: {e}")

    return JsonResponse({"status": "ok"})

def generar_codigo():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@login_required
def vincular_telegram(request):
    perfil, _ = Perfil.objects.get_or_create(user=request.user)

    if not perfil.telegram_code:
        perfil.telegram_code = generar_codigo()
        perfil.save()

    usuario_vinculado = perfil.telegram_chat_id not in [None, ""]

    return render(
        request,
        "finanzas/vincularConBot.html",
        {
            "codigo": perfil.telegram_code,
            "usuario_vinculado": usuario_vinculado,
        }
    )

def terminos(request):
    return render(request, 'finanzas/terminos.html')

@login_required
def eliminar_transaccion(request, id):
    if request.method == "POST":
        transaccion = get_object_or_404(Transaccion, id=id)
        transaccion.delete()
        messages.success(request, "Transacción eliminada correctamente.")
    # Redirige a la vista que carga las transacciones
    return redirect('historial_transacciones') 

@login_required
def desvincular_telegram(request):
    if request.method == "POST":
        perfil = request.user.perfil
        perfil.telegram_chat_id = ""
        perfil.save()
        messages.success(request, "Tu cuenta fue desvinculada correctamente.")

    return redirect('dashboard')

def procesar_mensaje_usuario(chat_id, text):
    try:
        perfil = Perfil.objects.get(telegram_chat_id=chat_id)
        usuario = perfil.user
    except Perfil.DoesNotExist:
        send_message(chat_id, "Tu cuenta no está vinculada. Vinculá desde la web.")
        return

    # 🚫 1) BLOQUEO DE IA (ANTES de gastar tokens)
    if ia_bloqueada(perfil):
        send_message(
            chat_id,
            "⏳ En unos minutos podré ayudarte con transacciones reales.\nDetecté mensajes que no debo procesar. Vuelve a intentar más tarde con algo como: \n"
            "Ej: 'gasté 1200 en comida hoy'"
        )
        return

    # 🤖 2) LLAMADA A LA IA
    data, err = extraer_transaccion_openai(text)
    if err or not data:
        registrar_no_transaccion(perfil)
        logger.error(f"[Bot] Error IA: err={err} data={data}")
        send_message(chat_id, "No pude entender la transacción 😕")
        return

    # 🛑 3) NO ES TRANSACCIÓN (suposición / futuro / idea)
    if not data.get("es_transaccion", True):
        registrar_no_transaccion(perfil)
        send_message(
            chat_id,
            "ℹ️ Parece que compartiste una idea o una compra futura.\n"
            "Sólo registro transacciones que ya ocurrieron."
        )
        return

    # 🧾 4) VALIDACIONES DE NEGOCIO
    if not data.get("tipo") or not data.get("monto"):
        registrar_no_transaccion(perfil)
        send_message(chat_id, "Falta información clave (tipo o monto). ¿Podés aclararlo?")
        return

    fecha = resolver_fecha(text, data)

    tipo = data["tipo"].lower()
    if tipo not in {"ingreso", "gasto"}:
        registrar_no_transaccion(perfil)
        send_message(chat_id, "No pude determinar si es ingreso o gasto.")
        return

    try:
        monto = Decimal(str(data["monto"]))
    except Exception:
        registrar_no_transaccion(perfil)
        send_message(chat_id, "El monto detectado no es válido.")
        return

    CATEGORIAS_VALIDAS = {
        "Comida", "Salario", "Compras",
        "Transferencias", "Servicios",
        "Ventas", "Otros"
    }
    categoria = data["categoria"] if data.get("categoria") in CATEGORIAS_VALIDAS else "Otros"

    # 🤔 5) CONFIDENCE BAJA → NO BLOQUEA
    if data.get("confidence", 0) < 0.7:
        send_message(
            chat_id,
            "Detecté esto, ¿confirmás?\n"
            + json.dumps(data, indent=2, ensure_ascii=False)
        )
        return

    # ✅ 6) TRANSACCIÓN VÁLIDA → RESET STRIKES
    registrar_transaccion_valida(perfil)
    print("MONTO IA:", data["monto"])
    print("MONTO FINAL A GUARDAR:", monto)

    Transaccion.objects.create(
        usuario=usuario,
        tipo=tipo,
        cantidad=monto,
        categoria=categoria,
        destino=data.get("destino"),
        fecha=fecha,
        descripcion=text
    )

    send_message(chat_id, "✅ Transacción registrada correctamente.")

    
def extraer_transaccion_openai(text):
    print("🔥 ENTRO A extraer_transaccion_openai 🔥", flush=True)
    print("Texto recibido:", text, flush=True)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "missing_api_key"

    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
                Extraé una transacción financiera SOLO si el texto describe
                una acción que YA ocurrió.

                Si es una suposición, intención futura o posibilidad,
                respondé EXCLUSIVAMENTE en formato JSON con:

                {
                "es_transaccion": false
                }

                Si ocurrió, respondé EXCLUSIVAMENTE en formato JSON con:

                {
                "tipo": "ingreso" | "gasto",
                "monto": number,
                "categoria": "Comida" | "Salario" | "Compras" | "Transferencias" | "Servicios" | "Ventas" | "Otros",
                "fecha": "YYYY-MM-DD" | null,
                "destino": string | null,
                "confidence": number
                }
                """
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=120
        )

        contenido = response.choices[0].message.content
        data = json.loads(contenido)

        return data, None

    except Exception as e:
        print("❌ ERROR IA:", e, flush=True)
        return None, "api_error"

def get_file_info(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    return requests.get(url).json()


def descargar_archivo(url, destino):
    r = requests.get(url)
    with open(destino, "wb") as f:
        f.write(r.content)

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)
