#!/usr/bin/env python3
"""
Flask App - rpi-youtube-stream
==============================
API REST para control de transmisiones en vivo a YouTube desde una Raspberry Pi.

La vinculacion con YouTube usa OAuth2 Device Flow (codigo + verificacion en el
telefono), apto para dispositivos headless. No requiere dominio ni redirect URI.

Endpoints:
  - GET  /                      : Panel principal (index.html)
  - GET  /auth                  : Pagina de vinculacion (auth.html)
  - GET  /api/status            : Estado actual del sistema
  - POST /api/start             : Iniciar transmision
  - POST /api/stop              : Detener transmision
  - POST /api/emergency         : Reinicio de emergencia
  - GET  /api/logs              : Obtener logs
  - POST /api/logs/clear        : Limpiar logs
  - POST /api/auth/device/start : Inicia Device Flow (devuelve codigo + URL)
  - POST /api/auth/device/poll  : Consulta si el usuario ya autorizo
  - POST /api/auth/unlink       : Desvincula la cuenta (borra tokens)

Autor: Andres Mercado
"""

import csv
import hashlib
import os
import re
import subprocess
import threading
import time
import urllib.request

from flask import Flask, jsonify, make_response, request, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

import config
import network
import settings
import youtube_api
from stream_manager import StreamManager


# ==============================================================================
# SECCION 0: CONFIGURACION FLASK
# ==============================================================================

app = Flask(__name__, static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
CORS(app)

manager = StreamManager()


# ==============================================================================
# SECCION 1: ESTADO GLOBAL
# ==============================================================================

_broadcast_id = None
_broadcast_title = None
_share_url = None
_start_lock = threading.Lock()

# Cache de estado de microfono
_MIC_STATUS_CACHE_TTL = 5.0
_last_mic_status = {
    "checked_at": 0.0,
    "connected": False,
    "message": f"Por favor, conecta el microfono ({config.AUDIO_DEVICE}) para iniciar.",
}


# ==============================================================================
# SECCION 2: DETECCION DE MICROFONO
# ==============================================================================


def _parse_alsa_device(audio_device):
    """Extrae card y device de formato ALSA (hw:X,Y o plughw:X,Y)."""
    match = re.search(r"(?:plughw|hw):\s*(\d+)\s*,\s*(\d+)", audio_device.strip().lower())
    if not match:
        return None
    return match.group(1), match.group(2)


def _probe_microphone():
    """Verifica si el dispositivo ALSA esta disponible."""
    card_and_device = _parse_alsa_device(config.AUDIO_DEVICE)
    if card_and_device is None:
        return False, (
            f'No se pudo validar el dispositivo "{config.AUDIO_DEVICE}". '
            "Usa formato hw:X,Y o plughw:X,Y."
        )

    card, device = card_and_device

    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except FileNotFoundError:
        return False, "No se encontro arecord para verificar el microfono."
    except subprocess.TimeoutExpired:
        return False, "No se pudo verificar el microfono a tiempo."

    output = f"{result.stdout}\n{result.stderr}"
    pattern = re.compile(rf"card\s+{card}\s*:.*device\s+{device}\s*:", re.IGNORECASE)

    if pattern.search(output):
        return True, None

    return False, f"Por favor, conecta el microfono ({config.AUDIO_DEVICE}) para iniciar."


def _get_microphone_status(force=False):
    """Retorna estado de microfono con cache TTL."""
    now = time.time()

    if not force and now - _last_mic_status["checked_at"] < _MIC_STATUS_CACHE_TTL:
        return _last_mic_status["connected"], _last_mic_status["message"]

    connected, message = _probe_microphone()
    _last_mic_status.update({
        "checked_at": now,
        "connected": connected,
        "message": message,
    })

    return connected, message


# ==============================================================================
# SECCION 3: CACHE BUSTING Y RUTAS ESTATICAS
# ==============================================================================


def _get_file_version(filename):
    """Retorna hash MD5 del archivo para cache busting."""
    filepath = os.path.join(app.static_folder, filename)
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except FileNotFoundError:
        return str(int(time.time()))


def _serve_html_with_no_cache(filename):
    """Sirve HTML con headers anti-cache y versionado de assets."""
    filepath = os.path.join(app.static_folder, filename)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return "Not found", 404

    css_version = _get_file_version("style.css")
    js_version = _get_file_version("script.js")
    content = content.replace('href="style.css"', f'href="style.css?v={css_version}"')
    content = content.replace('href="/style.css"', f'href="/style.css?v={css_version}"')
    content = content.replace('src="script.js"', f'src="script.js?v={js_version}"')

    response = make_response(content)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Content-Type"] = "text/html; charset=utf-8"

    return response


@app.route("/")
def index():
    """Panel principal."""
    return _serve_html_with_no_cache("index.html")


@app.route("/auth")
def auth_page():
    """Pagina de vinculacion (Device Flow)."""
    return _serve_html_with_no_cache("auth.html")


@app.route("/<path:filename>")
def static_files(filename):
    """Archivos estaticos."""
    response = send_from_directory(app.static_folder, filename)
    if "?v=" in request.url:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "public, max-age=300"
    return response


# ==============================================================================
# SECCION 4: API STATUS
# ==============================================================================


@app.route("/api/status")
def status():
    """Estado completo del sistema."""
    youtube_api.ensure_fresh_token()

    authorized = youtube_api.is_authorized()
    mic_connected, mic_message = _get_microphone_status()

    return jsonify({
        "state": manager.state,
        "brand": config.BRAND_NAME,
        "share_url": _share_url,
        "title": _broadcast_title,
        "authorized": authorized,
        "auth_error": None if authorized else youtube_api.AUTH_REQUIRED_MESSAGE,
        "microphone_connected": mic_connected,
        "microphone_message": mic_message,
        "allow_no_mic": settings.get("allow_no_mic", False),
        "connection": network.status(),
        "error": manager.error_message,
    })


# ==============================================================================
# SECCION 5: API START
# ==============================================================================


@app.route("/api/start", methods=["POST"])
def start_stream():
    """Inicia una transmision en vivo."""
    global _broadcast_id, _broadcast_title, _share_url

    if manager.state not in ("idle", "error"):
        return jsonify({"error": f"No se puede iniciar desde estado: {manager.state}"}), 409

    if not youtube_api.is_authorized():
        return jsonify({
            "error": youtube_api.AUTH_REQUIRED_MESSAGE,
            "auth_required": True,
            "redirect_to": "/auth",
        }), 401

    allow_no_mic = settings.get("allow_no_mic", False)
    use_mic = not allow_no_mic

    if use_mic:
        mic_connected, mic_message = _get_microphone_status(force=True)
        if not mic_connected:
            return jsonify({
                "error": mic_message or "Por favor, conecta el microfono para iniciar.",
                "microphone_required": True,
            }), 409

    data = request.json or {}
    title = data.get("title") or config.DEFAULT_STREAM_TITLE
    privacy = data.get("privacy", "unlisted")
    _broadcast_title = title

    try:
        manager.set_preparing()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 409

    manager.add_log(f'Creando broadcast: "{title}" ({privacy})')

    def _start_async():
        global _broadcast_id, _share_url

        with _start_lock:
            try:
                _run_start_sequence(title, privacy, use_mic)
            except Exception as e:
                _broadcast_id = None
                _share_url = None
                manager.add_log(f"ERROR en inicio: {e}")
                manager.reset_to_idle()

    threading.Thread(target=_start_async, daemon=True).start()

    return jsonify({"state": "preparing"})


def _run_start_sequence(title, privacy, use_mic=True):
    """Ejecuta secuencia de inicio del broadcast."""
    global _broadcast_id, _share_url

    # Paso 1: Crear broadcast (y obtener/crear stream + URL RTMP)
    if manager.cancelled:
        manager.add_log("Inicio cancelado antes de crear broadcast")
        manager.reset_to_idle()
        return

    bid, surl, rtmp_url = youtube_api.create_broadcast(title, privacy)
    _broadcast_id = bid
    _share_url = surl

    _broadcast_urls[bid] = surl

    manager.add_log(f"Broadcast creado: {surl}")

    # Paso 2: Esperar a YouTube
    if manager.cancelled:
        manager.add_log("Inicio cancelado despues de crear broadcast")
        manager.reset_to_idle()
        return

    manager.add_log("Esperando a YouTube (10s)...")
    for _ in range(20):  # 20 x 0.5s = 10s
        if manager.cancelled:
            manager.add_log("Inicio cancelado durante espera")
            manager.reset_to_idle()
            return
        time.sleep(0.5)

    # Paso 3: Iniciar pipeline
    if manager.cancelled:
        manager.add_log("Inicio cancelado antes de pipeline")
        manager.reset_to_idle()
        return

    manager.add_log("Iniciando pipeline de streaming...")
    manager.start(rtmp_url, use_mic)


# ==============================================================================
# SECCION 6: API STOP
# ==============================================================================


@app.route("/api/stop", methods=["POST"])
def stop_stream():
    """Detiene la transmision actual."""
    global _broadcast_id, _broadcast_title, _share_url

    if manager.state not in ("streaming", "starting", "preparing", "error"):
        return jsonify({"error": f"No hay transmision activa (estado: {manager.state})"}), 409

    manager.add_log("Solicitando detencion...")
    manager.stop()

    if _broadcast_id:
        try:
            youtube_api.end_broadcast(_broadcast_id)
            manager.add_log("Broadcast finalizado en YouTube")
        except Exception as e:
            manager.add_log(f"Error finalizando broadcast: {e}")

    _broadcast_id = None
    _broadcast_title = None
    _share_url = None

    return jsonify({"state": manager.state})


# ==============================================================================
# SECCION 7: API EMERGENCY
# ==============================================================================


@app.route("/api/emergency", methods=["POST"])
def emergency_reset():
    """Reinicio de emergencia: mata todos los procesos."""
    global _broadcast_id, _broadcast_title, _share_url

    manager.force_reset()

    if _broadcast_id:
        try:
            youtube_api.end_broadcast(_broadcast_id)
            manager.add_log("Broadcast finalizado en YouTube")
        except Exception:
            pass

    _broadcast_id = None
    _broadcast_title = None
    _share_url = None

    return jsonify({"state": manager.state})


# ==============================================================================
# SECCION 8: API LOGS
# ==============================================================================


@app.route("/api/logs")
def logs():
    """Retorna logs del sistema."""
    return jsonify({"logs": manager.get_logs()})


@app.route("/api/logs/clear", methods=["POST"])
def clear_logs():
    """Limpia el buffer de logs."""
    manager.clear_logs()
    return jsonify({"ok": True})


# ==============================================================================
# SECCION 9: API AUTH (DEVICE FLOW)
# ==============================================================================


@app.route("/api/auth/device/start", methods=["POST"])
def auth_device_start():
    """Inicia el Device Flow. Devuelve codigo y URL de verificacion."""
    try:
        info = youtube_api.start_device_flow()
    except youtube_api.AuthorizationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Error iniciando vinculacion: {e}"}), 500

    return jsonify({
        "device_code": info["device_code"],
        "user_code": info["user_code"],
        "verification_url": info["verification_url"],
        "interval": info["interval"],
        "expires_in": info["expires_in"],
    })


@app.route("/api/auth/device/poll", methods=["POST"])
def auth_device_poll():
    """Consulta si el usuario ya completo la vinculacion."""
    data = request.json or {}
    device_code = data.get("device_code")
    if not device_code:
        return jsonify({"status": "error", "message": "Falta device_code."}), 400

    try:
        result, message = youtube_api.poll_device_flow(device_code)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error consultando vinculacion: {e}"}), 500

    return jsonify({"status": result, "message": message})


@app.route("/api/auth/unlink", methods=["POST"])
def auth_unlink():
    """Desvincula la cuenta borrando los tokens locales."""
    youtube_api.unlink()
    return jsonify({"ok": True})


# ==============================================================================
# SECCION 9B: AJUSTES Y RED (OPCIONES AVANZADAS)
# ==============================================================================


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Devuelve los ajustes editables actuales."""
    return jsonify(settings.load())


@app.route("/api/settings", methods=["POST"])
def post_settings():
    """Actualiza ajustes (solo se aceptan claves conocidas)."""
    data = request.json or {}
    return jsonify(settings.update(data))


@app.route("/api/network/status")
def network_status():
    """Tipo de conexion a internet actual (ethernet/wifi/none)."""
    return jsonify(network.status())


@app.route("/api/network/wifi/scan")
def network_wifi_scan():
    """Lista redes WiFi disponibles."""
    return jsonify(network.scan())


@app.route("/api/network/wifi/connect", methods=["POST"])
def network_wifi_connect():
    """Conecta a una red WiFi dada."""
    data = request.json or {}
    ok, message = network.connect(data.get("ssid", ""), data.get("password", ""))
    return jsonify({"ok": ok, "message": message}), (200 if ok else 400)


# ==============================================================================
# SECCION 10: LINK INTERMEDIO PARA VISITANTES
# ==============================================================================

# Cache de broadcast_id -> youtube_url
_broadcast_urls = {}


def _get_geo_location(ip):
    """Obtiene ubicacion aproximada de una IP usando ip-api.com (gratuito)."""
    if ip in ("127.0.0.1", "localhost", "::1") or ip.startswith("192.168.") or ip.startswith("10."):
        return {"city": "Local", "country": "Local"}

    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,country,city"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = response.read().decode("utf-8")
            import json
            result = json.loads(data)
            if result.get("status") == "success":
                return {"city": result.get("city", "?"), "country": result.get("country", "?")}
    except Exception:
        pass

    return {"city": "?", "country": "?"}


def _log_visitor(broadcast_id, nombre, ip, user_agent):
    """Registra un visitante en el archivo CSV."""
    geo = _get_geo_location(ip)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    if not config.VISITORS_LOG_FILE.exists():
        with open(config.VISITORS_LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(config.VISITORS_LOG_FIELDS)

    with open(config.VISITORS_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            broadcast_id,
            nombre[:50] if nombre else "Anonimo",
            ip,
            geo["city"],
            geo["country"],
            user_agent[:100] if user_agent else "",
        ])


def _get_visitors(broadcast_id=None):
    """Lee visitantes del archivo CSV."""
    if not config.VISITORS_LOG_FILE.exists():
        return []

    visitors = []
    with open(config.VISITORS_LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, fieldnames=config.VISITORS_LOG_FIELDS)
        for row in reader:
            if row.get("timestamp") == "timestamp":
                continue
            if broadcast_id is None or row.get("broadcast_id") == broadcast_id:
                visitors.append(row)

    return visitors


@app.route("/watch/<broadcast_id>")
def watch_redirect(broadcast_id):
    """Pagina intermedia que pide el nombre antes de redirigir a YouTube."""
    youtube_url = _broadcast_urls.get(broadcast_id)

    if not youtube_url:
        return send_from_directory(app.static_folder, "watch_not_found.html")

    return _serve_html_with_no_cache("watch_welcome.html")


@app.route("/api/watch/<broadcast_id>/join", methods=["POST"])
def watch_join(broadcast_id):
    """Registra al visitante con su nombre y devuelve la URL de YouTube."""
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()

    if not nombre:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    youtube_url = _broadcast_urls.get(broadcast_id)
    if not youtube_url:
        return jsonify({"error": "Transmision no encontrada"}), 404

    ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For") or request.remote_addr
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    user_agent = request.headers.get("User-Agent", "")

    _log_visitor(broadcast_id, nombre, ip or "unknown", user_agent)

    return jsonify({"redirect_url": youtube_url})


@app.route("/api/visitors")
def api_visitors():
    """Retorna lista de visitantes."""
    broadcast_id = request.args.get("broadcast_id")
    visitors = _get_visitors(broadcast_id)
    return jsonify({"visitors": visitors, "count": len(visitors)})


@app.route("/api/visitors/clear", methods=["POST"])
def clear_visitors():
    """Limpia el registro de visitantes."""
    if config.VISITORS_LOG_FILE.exists():
        config.VISITORS_LOG_FILE.unlink()
    return jsonify({"ok": True})


# ==============================================================================
# SECCION 11: ENTRY POINT
# ==============================================================================


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT)
