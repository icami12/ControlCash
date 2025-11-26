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
from django.http import JsonResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
import re
import plotly.graph_objects as go
from plotly.offline import plot
from django.db.models.functions import TruncDay
import pandas as pd
from django.utils.timezone import now
from .ocr_utils import extraer_texto_imagen
from io import BytesIO
from PIL import Image
import pytesseract
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

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
    noti_count = Notificacion.objects.filter(leido=False).count()

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

    # --- Series temporal real ---
    data = (
        Transaccion.objects.filter(usuario=request.user)
        .annotate(dia=TruncDay("fecha"))
        .values("dia")
        .annotate(total=Sum("cantidad"))
        .order_by("dia")
    )

    if data:
        df = pd.DataFrame(data)
        df["dia"] = pd.to_datetime(df["dia"])
    else:
        df = pd.DataFrame({"dia": [], "total": []})

    # --- Plotly figure (estilo moderno) ---
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["dia"],
        y=df["total"],
        mode="lines",
        line=dict(width=3, color="#d4af37"),  # dorado fino
        fill="tozeroy",
        fillcolor="rgba(212,175,55,0.15)",
        hovertemplate="%{x|%d-%m-%Y}<br>$%{y:.2f}<extra></extra>"
    ))

    # --- Layout minimalista ---
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=200,
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            tickformat="%b %d",
            color="#aaa",
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            visible=False
        )
    )

    # --- Calcular balance del mes anterior ---
    hoy = now()
    primer_dia_mes_actual = hoy.replace(day=1)

    ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
    primer_dia_mes_anterior = ultimo_dia_mes_anterior.replace(day=1)

    balance_mes_anterior = (
        Transaccion.objects.filter(
            usuario=request.user,
            fecha__gte=primer_dia_mes_anterior,
            fecha__lte=ultimo_dia_mes_anterior,
        ).aggregate(total=Sum("cantidad"))["total"] or 0
    )

    # --- Trend real ---
    if balance_mes_anterior == 0:
        balance_trend = 100 if balance > 0 else 0
    else:
        balance_trend = ((balance - balance_mes_anterior) / balance_mes_anterior) * 100

    chart_html = plot(fig, output_type='div', include_plotlyjs=False)

    context = {
        "transacciones": movimientos_recientes,
        "ingresos": ingresos,
        "gastos": gastos,
        "balance": balance,
        "balance_trend": balance_trend,
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
            img = Image.open(BytesIO(img_bytes))

            # Pasar por OCR directamente desde memoria
            texto = pytesseract.image_to_string(img)

            if texto.strip():
                # 🔥 Ahora procesás el OCR igual que un mensaje normal
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
            try:
                _, codigo = text.split(" ", 1)
            except:
                send_message(chat_id, "Formato incorrecto. Usá: /vincular CODIGO")
                return JsonResponse({"status": "ok"})

            try:
                perfil = Perfil.objects.get(telegram_code=codigo.strip())
            except Perfil.DoesNotExist:
                send_message(chat_id, "Código inválido ❌ Respeta mayúsculas y números u obten un codigo válido.")
                return JsonResponse({"status": "ok"})

            # Vincular
            perfil.telegram_chat_id = chat_id
            perfil.telegram_code = None
            perfil.save()
            nombre = perfil.user.username
            mensaje = f"Hola {nombre} 👋\nTu cuenta fue vinculada correctamente ✔️\nEnvía /ayuda para conocer qué comandos manejamos."

            send_message(chat_id, mensaje)
            return JsonResponse({"status": "ok"})
        elif text.strip() == "/ayuda":
            send_message(
                chat_id,
                "😊Comandos disponibles:\n"
                "/vincular - Vincular tu cuenta con ControlCash. Ej: /vincular 123456\n"
                "/ayuda - Mostrar este mensaje\n"
                "/saldo - Ver tu saldo actual\n"
                "Puedes también escribir: 'gasté 20000 en comida el 24-10-25' u 'hoy ingreso 150000 sueldo'"
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
                "💰 Saldo disponible: "
                f"${balance}\n\n"
                "📊 Estado de cuenta:\n"
                f"+ Ingresos: {ingresos}\n"
                f"- Gastos: {gastos}\n"
                "---------------------\n"
                f"💰 Saldo: {balance}"
            )

            send_message(chat_id, mensaje)
            return JsonResponse({"status": "ok"})

        # Cualquier otro mensaje → verificar si está vinculado
        try:
            perfil = Perfil.objects.get(telegram_chat_id=chat_id)
        except Perfil.DoesNotExist:
            send_message(chat_id, "¡Hola!👋 Notamos que no estás vinculado al sistema ControlCash.\nEnvianos tu CODIGO_DE_VINCULACION para poder utilizar este bot.\nSi no tienes una cuenta puedes registrarte en www.ControlCash. com.")
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

@login_required
def eliminar_transaccion(request, id):
    if request.method == "POST":
        transaccion = get_object_or_404(Transaccion, id=id)
        transaccion.delete()
        messages.success(request, "Transacción eliminada correctamente.")
    # Redirige a la vista que carga las transacciones
    return redirect('historial_transacciones')  # usa el nombre de tu URL

@login_required
def desvincular_telegram(request):
    if request.method == "POST":
        perfil = request.user.perfil
        perfil.telegram_chat_id = ""
        perfil.save()
        messages.success(request, "Tu cuenta fue desvinculada correctamente.")

    return redirect('dashboard')

def procesar_mensaje_usuario(chat_id, text):
    # Traer usuario
    try:
        perfil = Perfil.objects.get(telegram_chat_id=chat_id)
        usuario = perfil.user
    except Perfil.DoesNotExist:
        send_message(chat_id, "Tu cuenta no está vinculada. Vinculá desde la web.")
        return

    # Detectar tipo
    tipo = detectar_tipo(text)

    # Detectar monto
    cantidad = detectar_monto(text)

    if not tipo or not cantidad:
        send_message(chat_id,
            "No pude entender tu mensaje.\n\nProbá con:\n"
            "• 'ayer gasté 20000 en comida'\n"
            "• '17-11-25 ingreso 150000 sueldo'"
        )
        return

    categoria = detectar_categoria(text)
    destino = detectar_destino(text)  # opcional
    descripcion = text
    fecha = obtener_fecha(text)
    if fecha is None:
        send_message(chat_id, "No pude entender la fecha. ¿Podés indicarla? Ej: hoy, ayer, 20-11-2025")
        return

    Transaccion.objects.create(
        usuario=usuario,
        tipo=tipo,
        cantidad=cantidad,
        descripcion=descripcion,
        categoria=categoria,
        destino=destino,
        fecha = fecha
    )

    send_message(chat_id, f"✔ Registrado {tipo} de ${cantidad} correctamente.")
    #crear notificacion al registrar
    Notificacion.objects.create(
        texto=f"Se registró una nueva transacción por ${cantidad} el {fecha}."
    )

def detectar_tipo(text):
    t = text.lower()

    # Palabras clave de gasto
    gasto_kw = ["gast", "pag", "pagué", "pague", "compr", "transfer", "envie", "envié", "mand"]
    if any(k in t for k in gasto_kw):
        return "gasto"

    # Palabras clave de ingreso
    ingreso_kw = ["ingres", "cobr", "me deposit", "me pagaron", "vendí", "vendi", "me trans","me pas"]
    if any(k in t for k in ingreso_kw):
        return "ingreso"

    return None

def detectar_monto(text):
    t = text.lower()

    # 1️⃣ Quitar fechas tipo 12-11-24
    t = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', '', t)

    # 2️⃣ Buscar montos con signo $
    montos_con_signo = re.findall(
        r'\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,]\d{2})?|\d+)',
        t
    )

    if montos_con_signo:
        limpio = max(montos_con_signo, key=lambda x: float(x.replace(".", "").replace(",", ".")))
        limpio = limpio.replace(".", "").replace(",", ".")
        return Decimal(limpio)

    # 3️⃣ Buscar montos formateados tipo 78.000 o 1,250
    montos_formato = re.findall(
        r'\b[0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,]\d{2})?\b',
        t
    )

    if montos_formato:
        montos_formato = [m for m in montos_formato if len(m.replace(".", "").replace(",", "")) <= 10]
        if montos_formato:
            limpio = max(montos_formato, key=lambda x: float(x.replace(".", "").replace(",", ".")))
            limpio = limpio.replace(".", "").replace(",", ".")
            return Decimal(limpio)

    # 4️⃣ Buscar expresiones tipo "5 mil", "10mil", "3 lucas"
    multiplicadores = {
        "mil": 1000,
        "miles": 1000,
        "m": 1000,
        "k": 1000,
        "lucas": 1000,
        "luca": 1000,
    }

    matches_palabras = re.findall(r'(\d+)\s*(mil|miles|m|k|lucas|luca)\b', t)
    if matches_palabras:
        valores = []
        for numero, palabra in matches_palabras:
            valor = int(numero) * multiplicadores[palabra]
            valores.append(valor)
        return Decimal(max(valores))

    # 5️⃣ Números sueltos
    numeros = re.findall(r'\b\d{1,10}\b', t)
    if numeros:
        num = max(numeros, key=lambda x: int(x))
        return Decimal(num)

    return None

def detectar_categoria(text):
    t = text.lower()

    categorias = {
        "Comida": ["comida", "almuerzo", "cena","merienda", "restaurante"],
        "Salario": ["salario", "sueldo", "me pagaron", "cobré"],
        "Compras": ["compré", "compre","compra", "tienda","kiosco","local","shop", "tarjeta"],
        "Transferencias": ["transferi", "transfirio","mandé", "envie", "envié", "transferencia"],
        "Servicios": ["luz", "agua", "gas", "internet","boleta","telefono","alquiler","cable","seguro","colegio","escuela"],
        "Ventas": ["vendí", "vendi", "me trans","me pas", "venta"],
    }

    for cat, palabras in categorias.items():
        if any(p in t for p in palabras):
            return cat

    return "Otros"

def detectar_destino(text):
    t = text.replace("\n", " ")
    stopwords = r"(?:\bCUIT\b|\bCUIL\b|\bCBU\b|\bCVU\b|\bCuenta\b|\bBanco\b|\bAlias\b|\bNro\b|\bNúmero\b|\bImporte\b|\bMonto\b|\bTransacci[oó]n\b)"
    # 1. Tomar el texto después de A / Para / Hacia
    match = re.search(
        r"(?:Para|A|Hacia)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ .'-]{3,80})",
        t,
        re.IGNORECASE
    )
    if not match:
        return None

    candidato = match.group(1)

    # 2. Cortar por stopwords si aparecen
    #    Ej: "Juan Perez CBU 123..." -> "Juan Perez"
    candidato = re.split(stopwords, candidato, flags=re.IGNORECASE)[0].strip()

    # 3. Limpieza
    candidato = candidato.strip(" .:-")

    # 4. Validaciones fuertes para evitar falsos positivos
    # ❌ No debe contener números
    if re.search(r"\d", candidato):
        return None

    # ❌ No debe ser demasiado corto o demasiado largo
    if not (5 <= len(candidato) <= 60):
        return None

    # ❌ Debe tener al menos dos palabras tipo nombre-apellido
    partes = candidato.split()
    if len(partes) < 2:
        return None

    # ❌ Cada parte debe ser razonable
    for p in partes:
        # evitar cosas como "CTA", "BANCO", "TRANSFERENCIA"
        if len(p) < 2:
            return None
        if p.isupper() and len(p) > 4:  # palabras sospechosas tipo "TRANSFERENCIA"
            return None

    return candidato

#detectando fecha de menos a mas especifica
def detectar_fecha(text):
    t = text.lower()
    # Hoy
    if "hoy" in t:
        return date.today()
    # Ayer
    if "ayer" in t:
        return date.today() - timedelta(days=1)
    return None  # Deja que otros detectores analicen después

dias = {
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sábado": 5,
    "sabado": 5,
    "domingo": 6,
}
def detectar_dia_semana(text):
    t = text.lower()
    for nombre, num in dias.items():
        if nombre in t:
            hoy = date.today()
            hoy_num = hoy.weekday()
            diferencia = hoy_num - num
            if diferencia < 0:
                diferencia += 7
            return hoy - timedelta(days=diferencia)
    return None

def detectar_fecha_explicita(text):
    t = text.lower()
    # Formatos: 13-11-25 | 13/11/2025 | 13-11-2025
    match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", t)
    if match:
        dia, mes, año = match.groups()
        año = int(año)
        if año < 100:  # Interpretar 25 como 2025
            año = 2000 + año
        return date(año, int(mes), int(dia))
    return None

def obtener_fecha(text):
    # 1. hoy / ayer
    f1 = detectar_fecha(text)
    if f1:
        return f1
    # 2. día de la semana
    f2 = detectar_dia_semana(text)
    if f2:
        return f2
    # 3. fecha explícita
    f3 = detectar_fecha_explicita(text)
    if f3:
        return f3
    # 4. si nada coincide → hoy
    return None

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
