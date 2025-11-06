# Go Waffles Bot

Bot de atención al cliente para Go Waffles, funcionando en Telegram y en la web, usando OpenAI GPT-3.5 y FastAPI.

---

## Estructura del proyecto
```

go_waffles_bot/
│
├─ main.py <- Código FastAPI con endpoints para Telegram y web
├─ requirements.txt <- Librerías necesarias
├─ Procfile <- Comando de inicio para Railway
└─ .gitignore <- Archivos/carpetas a ignorar en GitHub
```


---

## Variables de entorno

- `OPENAI_API_KEY` → tu API Key de OpenAI  
- `TELEGRAM_TOKEN` → token del bot de Telegram  


---

## Ejecutar localmente

1. Crear entorno virtual:

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
```

3. Correr el servidor:
```bash
uvicorn main:app --reload
```


