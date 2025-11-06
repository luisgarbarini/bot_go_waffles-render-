from datetime import datetime
import pytz 
from fastapi import FastAPI, Request
import os
import requests
from openai import OpenAI
import uvicorn

app = FastAPI()

historial_chats = {}
MAX_MENSAJES = 10

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage" if TELEGRAM_TOKEN else ""

system_prompt = """
Eres el asistente virtual de Go Waffles 🍓. 
Responde solo preguntas relacionadas con el negocio usando EXCLUSIVAMENTE la información proporcionada en el contexto a continuación.

❗ REGLAS ESTRICAS:
- NO inventes nombres de productos, sabores, ingredientes, toppings, waffles, milkshakes, combos o promociones.
- Si el usuario pregunta por algo específico (ej: "¿tienen con frutilla?", "¿qué waffles tienen?", "¿recomiendas algo?"), NO menciones ejemplos ni descripciones.
- En su lugar, responde amablemente que puede ver TODOS los productos en gowaffles.cl/pedir.
- Si la información de referencia no contiene una lista explícita de productos o sabores, asume que NO puedes recomendar nada por nombre.
- Usa un tono juvenil, cercano y emojis cuando quede bien 😄, pero prioriza la exactitud sobre la creatividad.
- Si no sabes algo, di que escriba a contacto@gowaffles.cl ✉️.
- Si ya estás en medio de una conversación (el usuario ya te ha escrito antes), NO debes saludar con "¡Hola!" ni frases de bienvenida. Ve directo al punto.

✅ Tu única respuesta segura ante preguntas de productos es: 
“¡Tenemos una variedad rica de waffles dulces, salados, milkshakes y más! Puedes ver todos los productos y armar tu pedido en gowaffles.cl/pedir 🧇”

No alteres los enlaces. Respétalos exactamente como aparecen.
"""

info_negocio = {
    "ubicacion": "Estamos ubicados en Avenida Gabriel González Videla 3170, La Serena. También puedes encontrarnos en google maps como 'Go Waffles'.",
    "horarios": "De lunes a viernes entre las 16:00 y 21:00. Sábado y domingo entre 15:30 y 21:30.",
    "promociones": "Tenemos un 15% de descuento usando el cupón PRIMERACOMPRA en gowaffles.cl",
    "canales_venta": "Puedes comprar en tu delivery app favorita (UberEats, PedidosYa o Rappi) o a través de nuestra página web gowaffles.cl",
    "carta": "Encuentra todos nuestros productos en gowaffles.cl/pedir",
    "trabajo": "Si quieres trabajar con nosotros, puedes escribir a contacto@gowaffles.cl o rellenar el formulario en gowaffles.cl/nosotros",
    "problemas": "Si tuviste algún inconveniente con tu pedido escríbenos a contacto@gowaffles.cl",
    "retraso": "Si quieres conocer el estado de tu pedido puedes revisarlo directamente en la plataforma en la que hiciste tu pedido (delivery app o gowaffles.cl)",
    "ejecutivo": "Si necesitas hablar con un encargado del local, comunícate al https://wa.me/56953717707",
    "redes_sociales":"Encuentranos en instagram o tiktok como @gowaffles.cl",
    "categorías":"Tenemos waffles dulces, salados y personalizados. También tenemos milkshakes, frappes, limonadas, Mini Go, helados y bebidas",
    "productos_disponibles":"La carta completa con todos los productos, ingredientes y precios está disponible exclusivamente en gowaffles.cl/pedir",
    "zona_delivery":"Cada delivery app tiene su propio radio de despacho. En gowaffles.cl/local puedes ver la cobertura de despacho para las ventas de nuestro sitio web"
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
    hora_actual = ahora.strftime("%H:%M")
    
    # 👇 Añadimos el DÍA en español
    dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    dia_semana = dias_es[ahora.weekday()]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ Ups, no tengo acceso a mi cerebro. Por favor avisa al equipo de Go Waffles."

    client = OpenAI(api_key=api_key)

    # Contexto fijo + fecha/hora actuales
    contexto_fijo = generar_contexto(info_negocio)
    contexto_fijo += f"\nFecha y hora actual en La Serena, Chile: hoy es {dia_semana} a las {hora_actual}.\n"

    messages = [
        {"role": "system", "content": system_prompt + "\n\n" + contexto_fijo},
    ]
    messages.extend(historial)

    try:
        respuesta = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.3,
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
