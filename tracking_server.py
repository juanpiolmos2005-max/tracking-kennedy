"""
SERVIDOR DE TRACKING — Email Marketing Kennedy
===============================================
Este servidor corre en la nube (Railway, Render, VPS, etc.)
y sigue funcionando aunque la PC esté apagada.

INSTALACION LOCAL (para probar):
    pip install flask

DEPLOY EN RAILWAY (gratis):
    1. Creá cuenta en https://railway.app
    2. "New Project" → "Deploy from GitHub repo"
       (o subí los archivos directamente)
    3. Agregá variable de entorno: PORT=8080
    4. Railway te da una URL pública tipo:
       https://tu-proyecto.up.railway.app
    5. Pegá esa URL en la app → pestaña Tracking → "URL pública"

DEPLOY EN RENDER (gratis):
    1. Creá cuenta en https://render.com
    2. "New" → "Web Service" → conectá tu repo
    3. Build command: pip install flask
    4. Start command: python tracking_server.py
    5. Render te da URL tipo: https://tu-app.onrender.com

ARCHIVOS NECESARIOS EN EL REPO:
    - tracking_server.py  (este archivo)
    - requirements.txt    (con "flask" adentro)

El tracking.json se guarda localmente en el servidor.
Para sincronizar, la app descarga el JSON via /api/tracking.
"""

import os
import json
import urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# En producción los datos se guardan en /tmp (efímero) o en un volumen persistente.
# Railway y Render soportan volúmenes persistentes. Para uso simple /tmp alcanza.
DATA_DIR     = os.environ.get("DATA_DIR", "/tmp")
TRACKING_FILE = os.path.join(DATA_DIR, "tracking.json")

# Contraseña opcional para proteger el endpoint de lectura
API_KEY = os.environ.get("API_KEY", "")

GIF_PIXEL = bytes([
    71,73,70,56,57,97,1,0,1,0,0,255,0,
    44,0,0,0,0,1,0,1,0,0,2,0,59
])


def load_tracking():
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_tracking(data):
    with open(TRACKING_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Endpoint principal de tracking ──────────────────────────────────────────
@app.route("/t")
def track():
    """
    Recibe eventos de:
      - apertura de mail (pixel 1x1)
      - clic en botón WhatsApp
      - clic en botón Formulario
    """
    accion  = request.args.get("a", "")
    mail    = request.args.get("m", "")
    nombre  = request.args.get("n", "")
    carrera = request.args.get("c", "")
    base_id = request.args.get("b", "")

    evento = {
        "ts":      datetime.now().isoformat(),
        "accion":  accion,
        "mail":    mail,
        "nombre":  nombre,
        "carrera": carrera,
        "base_id": base_id,
    }

    tracking = load_tracking()
    tracking.append(evento)
    save_tracking(tracking)

    if accion == "open":
        # Devolver pixel GIF 1x1 transparente
        return Response(
            GIF_PIXEL,
            mimetype="image/gif",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma":        "no-cache",
                "Expires":       "0",
            }
        )
    elif accion in ("wa", "form"):
        dest = request.args.get("dest", "")
        if dest:
            return app.redirect(dest, code=302)
        return Response("OK", status=200)
    else:
        return Response("OK", status=200)


# ── API para que la app descargue el tracking ────────────────────────────────
@app.route("/api/tracking")
def api_tracking():
    """
    La app desktop puede llamar a este endpoint para
    sincronizar el tracking sin necesidad de ngrok.
    """
    if API_KEY:
        key = request.args.get("key", "")
        if key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401

    tracking = load_tracking()
    return jsonify(tracking)


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """Limpiar el tracking desde la app."""
    if API_KEY:
        key = request.args.get("key", "")
        if key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
    save_tracking([])
    return jsonify({"ok": True})


@app.route("/api/stats")
def api_stats():
    """Resumen rápido de estadísticas."""
    tracking = load_tracking()
    aperturas_totales = sum(1 for x in tracking if x.get("accion") == "open")
    aperturas_unicas  = len({x.get("mail","").lower() for x in tracking
                              if x.get("accion") == "open" and x.get("mail")})
    clics_wa   = sum(1 for x in tracking if x.get("accion") == "wa")
    clics_form = sum(1 for x in tracking if x.get("accion") == "form")
    return jsonify({
        "total_eventos":    len(tracking),
        "aperturas_totales": aperturas_totales,
        "aperturas_unicas": aperturas_unicas,
        "clics_wa":         clics_wa,
        "clics_form":       clics_form,
    })


# ── Health check ─────────────────────────────────────────────────────────────
@app.route("/")
@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": datetime.now().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Servidor de tracking iniciando en puerto {port}...")
    print(f"Tracking file: {TRACKING_FILE}")
    app.run(host="0.0.0.0", port=port, debug=False)
