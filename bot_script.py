from datetime import datetime, time
import pytz
from fastapi import FastAPI, Request
import os
import requests
from openai import OpenAI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware  # Importa el middleware de CORS

app = FastAPI()

# Agrega el middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.gowaffles.cl/",
        "https://gowaffles.cl"
    ],  # Permitir cualquier origen (¡cuidado en producción!)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

historial_chats = {}
MAX_MENSAJES = 10

# 👇 Define horarios como objetos `time` (¡muy limpio!)
HORARIO = {
    "lunes_viernes": {
        "inicio": time(16, 0),   # 16:00
        "fin": time(21, 0)       # 21:00
    },
    "sabado_domingo": {
        "inicio": time(15, 30),  # 15:30
        "fin": time(21, 30)       # 21:30
    }
}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage" if TELEGRAM_TOKEN else ""

def formatear_hora(t: time) -> str:
    """Convierte time(15, 30) → '15:30'"""
    return t.strftime("%H:%M")

def generar_texto_horario():
    lv = HORARIO["lunes_viernes"]
    sd = HORARIO["sabado_domingo"]
    return (
        f"De lunes a viernes entre las {formatear_hora(lv['inicio'])} y {formatear_hora(lv['fin'])}. "
        f"Sábado y domingo entre {formatear_hora(sd['inicio'])} y {formatear_hora(sd['fin'])}."
    )

def esta_abierto_ahora():
    chile_tz = pytz.timezone("America/Santiago")
    ahora = datetime.now(chile_tz)
    hora_actual = ahora.time()
    dia = ahora.weekday()  # 0=lunes, 6=domingo

    if dia < 5:  # lunes a viernes
        rango = HORARIO["lunes_viernes"]
    else:  # sábado o domingo
        rango = HORARIO["sabado_domingo"]

    # Compara objetos time directamente
    return rango["inicio"] <= hora_actual <= rango["fin"]

system_prompt = """
Rol: Asistente del local Go Waffles 🍓
Personalidad: Cercano, juguetón, joven (Gen Z/Alfa). Frases cortas o medias, cero formalidad.
Usa emojis como 🍓😎🤓👀🤌💯🤤🤙🧇🗿. No uses 😊.

Objetivo: ayudar y conversar a partir de la información disponible.
Cuando un usuario pregunte por productos o categorías SOLO ESTÁS AUTORIZADO a mencionar las categorías: Waffles dulces, salados y personalizados. Milkshakes, frappes, helados y café.
Está PROHIBIDA la mención de cualquier nombre de producto, ingredientes o precios. 

Reglas estrictas:
1. No inventes productos, precios ni ingredientes.
2. No describas comida.
3. No des recomendaciones específicas.
4. No repitas saludos si la conversación ya comenzó.
5. No alteres ningún enlace.

Ejemplos de estilo:
- “siii obvio 👀 mira todo acá 🤌 gowaffles.cl/pedir”
- “si andas con antojo dulce o salado, acá está la carta 🤤🤙 gowaffles.cl/pedir”

Si tu respuesta incluye por error un producto o ingrediente: descartala y genera otra que cumpla las reglas.
"""

info_negocio = {
    "ubicacion": "Avenida Gabriel González Videla 3170, La Serena. En Google Maps aparece como 'Go Waffles'.",
    "horarios": generar_texto_horario(),
    "promociones": "15% de descuento usando el cupón PRIMERACOMPRA en gowaffles.cl",
    "canales_venta": "Disponibles en UberEats, PedidosYa, Rappi y en gowaffles.cl",
    "carta": "Carta completa en gowaffles.cl/pedir",
    "trabajo": "Postulaciones en contacto@gowaffles.cl o en gowaffles.cl/nosotros",
    "problemas": "Contacto para problemas: contacto@gowaffles.cl",
    "retraso": "El estado del pedido se revisa directamente en la plataforma donde fue realizado",
    "ejecutivo": "Contacto con encargado: https://wa.me/56953717707",
    "redes_sociales": "Instagram y TikTok como @gowaffles.cl",
    "categorías": "Waffles dulces, salados y personalizados; milkshakes; frappes; limonadas; Mini Go; helados; café",
    "productos_disponibles": "Carta y precios: gowaffles.cl/pedir",
    "zona_delivery": "Cobertura depende de la delivery app. En gowaffles.cl/local está la cobertura del sitio web",
    "estacionamiento":"Sí, fuera del local",
    "medio_pago":"Efectivo, débito, crédito, ApplePay y GooglePay"
}

def generar_contexto(info):
    contexto = "Aquí tienes información de referencia sobre Go Waffles que puedes usar para responder:\n"
    for clave, valor in info.items():
        contexto += f"- {clave.capitalize()}: {valor}\n"
    contexto += "\nUsa esta información solo si aplica a la pregunta del usuario.\n"
    return contexto

def responder_pregunta_con_historial(historial, chat_id):
    chile_tz = pytz.timezone("America/Santiago")
    ahora = datetime.now(chile_tz)
    dia_semana = ahora.weekday()
    hora_str = ahora.strftime("%H:%M")

    dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    dia_nombre = dias_es[dia_semana]

    abierto = esta_abierto_ahora()
    estado = "abierto" if abierto else "cerrado"

    # ✅ Generamos UN SOLO contexto, con la info clave
    contexto_fijo = generar_contexto(info_negocio)
    contexto_fijo += (
        f"\nHoy es {dia_nombre} en La Serena, Chile, y son las {hora_str}.\n"
        f"El local está actualmente {estado}.\n"
        "Si el usuario pregunta si están abiertos, responde según este estado actual. "
        "No inventes ni supongas horarios distintos.\n"
    )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ Ups, no tengo acceso a mi cerebro. Por favor avisa al equipo de Go Waffles."

    client = OpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": system_prompt + "\n\n" + contexto_fijo},
    ]
    messages.extend(historial)

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.5,
            timeout=10
        )
        return respuesta.choices[0].message.content
    except Exception as e:
        print(f"❌ Error al llamar a OpenAI: {e}")
        return "¡Ups! Tuve un pequeño error al pensar mi respuesta. ¿Puedes repetirme tu pregunta? 🧇"

# --- ENDPOINT TELEGRAM ---
@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    if not TELEGRAM_TOKEN or not TELEGRAM_URL:
        print("❌ TELEGRAM_TOKEN no está definido en las variables de entorno.")
        return {"status": "error", "detalle": "Token de Telegram no configurado"}

    data = await request.json()
    print("📥 Recibido de Telegram:", data)

    try:
        mensaje = data["message"]["text"]
        chat_id = data["message"]["chat"]["id"]
    except KeyError:
        print("⚠️ Mensaje sin texto o chat_id. Ignorado.")
        return {"status": "ignored"}

    if chat_id not in historial_chats:
        historial_chats[chat_id] = []

    historial_chats[chat_id].append({"role": "user", "content": mensaje})

    if len(historial_chats[chat_id]) > MAX_MENSAJES:
        historial_chats[chat_id] = historial_chats[chat_id][-MAX_MENSAJES:]

    respuesta = responder_pregunta_con_historial(historial_chats[chat_id], chat_id)

    historial_chats[chat_id].append({"role": "assistant", "content": respuesta})

    print(f"📤 Respondiendo a {chat_id}: {respuesta}")

    try:
        response = requests.post(TELEGRAM_URL, json={"chat_id": chat_id, "text": respuesta}, timeout=5)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Error al enviar mensaje a Telegram: {e}")
        return {"status": "error", "detalle": str(e)}

    return {"status": "ok"}

# --- ENDPOINT WEB ---
@app.post("/webhook/web")
async def web_webhook(request: Request):
    data = await request.json()
    try:
        mensaje = data["mensaje"]
    except KeyError:
        return {"status": "error", "detalle": "Falta el campo 'mensaje'"}

    historial_simulado = [{"role": "user", "content": mensaje}]
    respuesta = responder_pregunta_con_historial(historial_simulado, chat_id="web_test")
    return {"respuesta": respuesta}

# --- HEALTH CHECK ---
@app.get("/health")
@app.head("/health") 
async def health_check():
    return {
        "status": "ok",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "telegram_configured": bool(os.getenv("TELEGRAM_TOKEN")),
        "webhook_url": "https://bot-go-waffles.onrender.com/webhook/telegram"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("bot_script:app", host="0.0.0.0", port=port)
