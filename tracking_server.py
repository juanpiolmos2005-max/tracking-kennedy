"""
SERVIDOR DE TRACKING — Email Marketing Kennedy
===============================================
Guarda el tracking en GitHub como respaldo persistente.
Ante cualquier reinicio de Render, los datos se recuperan del repo.
"""
 
import os
import json
import base64
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, Response
 
app = Flask(__name__)
 
DATA_DIR      = os.environ.get("DATA_DIR", "/tmp")
TRACKING_FILE = os.path.join(DATA_DIR, "tracking.json")
 
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "")
GITHUB_FILE  = "tracking_data.json"  # archivo en el repo donde se guarda
 
API_KEY = os.environ.get("API_KEY", "")
 
GIF_PIXEL = bytes([
    71,73,70,56,57,97,1,0,1,0,0,255,0,
    44,0,0,0,0,1,0,1,0,0,2,0,59
])
 
_github_lock = threading.Lock()
 
 
# ── GitHub helpers ───────────────────────────────────────────────────────────
 
def _github_request(method, path, body=None):
    """Hace un request a la API de GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "tracking-kennedy"
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)
 
 
def _load_from_github():
    """Descarga el tracking desde GitHub."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None
    result, err = _github_request("GET", GITHUB_FILE)
    if err or not result:
        return None
    try:
        content = base64.b64decode(result["content"]).decode("utf-8")
        return json.loads(content), result.get("sha", "")
    except Exception:
        return None
 
 
def _save_to_github(data, sha=""):
    """Sube el tracking a GitHub (async para no bloquear respuestas)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    def _do():
        with _github_lock:
            # Obtener SHA actual si no lo tenemos
            current_sha = sha
            if not current_sha:
                result, _ = _github_request("GET", GITHUB_FILE)
                if result:
                    current_sha = result.get("sha", "")
 
            content = base64.b64encode(
                json.dumps(data, indent=2).encode()
            ).decode()
 
            body = {
                "message": f"tracking update {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "content": content,
            }
            if current_sha:
                body["sha"] = current_sha
 
            _github_request("PUT", GITHUB_FILE, body)
 
    threading.Thread(target=_do, daemon=True).start()
 
 
# ── Tracking local ──────────────────────────────────────────────────────────
 
def load_tracking():
    # Primero intenta local
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    # Si no hay local (reinicio), descarga de GitHub
    result = _load_from_github()
    if result:
        data, _ = result
        save_tracking(data)  # restaurar local
        print(f"[tracking] Restaurado desde GitHub: {len(data)} eventos")
        return data
    return []
 
 
def save_tracking(data):
    with open(TRACKING_FILE, "w") as f:
        json.dump(data, f, indent=2)
 
 
# ── Inicializar: restaurar desde GitHub al arrancar ──────────────────────────
def _init_from_github():
    if not os.path.exists(TRACKING_FILE):
        result = _load_from_github()
        if result:
            data, _ = result
            save_tracking(data)
            print(f"[init] Tracking restaurado desde GitHub: {len(data)} eventos")
 
_init_from_github()
 
 
# ── Endpoint principal ───────────────────────────────────────────────────────
@app.route("/t")
def track():
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
    # Guardar en GitHub de forma asíncrona (cada 10 eventos para no saturar la API)
    if len(tracking) % 10 == 0:
        _save_to_github(tracking)
 
    if accion == "open":
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
    elif accion == "tel":
        dest = request.args.get("dest", "tel:08002223340")
        page = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conectando...</title>
<style>
  body{{background:#111;color:#fff;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;
       height:100vh;margin:0;text-align:center;}}
  a{{color:#D10135;font-size:1.3em;font-weight:bold;text-decoration:none;}}
  p{{color:#aaa;font-size:0.9em;margin-top:12px;}}
</style>
</head><body>
<div>
  <div style="font-size:3em;margin-bottom:16px;">📞</div>
  <a href="{dest}">Llamar al 0800-222-3340</a>
  <p>Si no inicia automáticamente, tocá el número de arriba.</p>
</div>
<script>window.location.href="{dest}";</script>
</body></html>"""
        return Response(page, mimetype="text/html; charset=utf-8")
    else:
        return Response("OK", status=200)
 
 
# ── API ───────────────────────────────────────────────────────────────────────
@app.route("/api/tracking")
def api_tracking():
    if API_KEY:
        if request.args.get("key", "") != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
    return jsonify(load_tracking())
 
 
@app.route("/api/clear", methods=["POST"])
def api_clear():
    if API_KEY:
        if request.args.get("key", "") != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
    save_tracking([])
    _save_to_github([])
    return jsonify({"ok": True})
 
 
@app.route("/api/clear_tel", methods=["POST"])
def api_clear_tel():
    if API_KEY:
        if request.args.get("key", "") != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
    tracking = load_tracking()
    sin_tel = [x for x in tracking if x.get("accion") != "tel"]
    save_tracking(sin_tel)
    _save_to_github(sin_tel)
    eliminados = len(tracking) - len(sin_tel)
    return jsonify({"ok": True, "eliminados": eliminados})
 
 
@app.route("/api/backup", methods=["POST"])
def api_backup():
    """Fuerza un backup inmediato a GitHub."""
    tracking = load_tracking()
    _save_to_github(tracking)
    return jsonify({"ok": True, "eventos": len(tracking)})
 
 
@app.route("/api/stats")
def api_stats():
    tracking = load_tracking()
    return jsonify({
        "total_eventos":    len(tracking),
        "aperturas_totales": sum(1 for x in tracking if x.get("accion") == "open"),
        "aperturas_unicas":  len({x.get("mail","").lower() for x in tracking
                                   if x.get("accion") == "open" and x.get("mail")}),
        "clics_wa":   sum(1 for x in tracking if x.get("accion") == "wa"),
        "clics_tel":  sum(1 for x in tracking if x.get("accion") == "tel"),
        "clics_form": sum(1 for x in tracking if x.get("accion") == "form"),
    })
 
 
@app.route("/")
@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": datetime.now().isoformat()})
 
 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Servidor de tracking iniciando en puerto {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)

