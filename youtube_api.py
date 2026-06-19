#!/usr/bin/env python3
"""
YouTube API - rpi-youtube-stream
================================
OAuth2 Device Flow + Live Streaming API para YouTube.

Diferencias clave respecto a la version original:
  - Autorizacion por Device Flow (codigo + verificacion en el telefono),
    apta para dispositivos headless. No requiere redirect URI ni dominio.
  - El stream NO se identifica por una stream key fija: se descubre o se crea
    por API en la cuenta que inicia sesion (get_or_create_stream).

Flujo de vinculacion:
  1. start_device_flow()  -> device_code + user_code + verification_url
  2. el usuario abre verification_url y escribe user_code
  3. poll_device_flow(device_code) -> al aprobar, guarda los tokens

Dependencias:
  - google-auth, google-api-python-client (cliente de la API)
  - El Device Flow se implementa con urllib (stdlib), sin libs extra.

Autor: Andres Mercado
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config


# ==============================================================================
# SECCION 0: CONSTANTES
# ==============================================================================

AUTH_REQUIRED_MESSAGE = "YouTube no vinculado. Abre /auth para vincular tu cuenta."
AUTH_REVOKED_MESSAGE = "Sesion de YouTube expirada o revocada. Abre /auth para volver a vincular."

_OAUTH_DEVICE_CODE_URI = "https://oauth2.googleapis.com/device/code"
_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# Refrescar token 5 minutos antes de que expire.
TOKEN_REFRESH_BUFFER = timedelta(minutes=5)

log = logging.getLogger("youtube_api")


# ==============================================================================
# SECCION 1: EXCEPCIONES
# ==============================================================================


class AuthorizationError(RuntimeError):
    """Error de autorizacion OAuth2."""
    pass


# ==============================================================================
# SECCION 2: DEVICE FLOW (VINCULACION)
# ==============================================================================


def _http_post_form(url, fields):
    """POST x-www-form-urlencoded. Retorna (status_code, dict)."""
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"error": "http_error", "error_description": body}
    except urllib.error.URLError as e:
        return 0, {"error": "network_error", "error_description": str(e.reason)}


def _credentials_configured():
    """Verifica que el cliente OAuth tenga valores reales (no placeholders)."""
    cid = config.YOUTUBE_CLIENT_ID or ""
    secret = config.YOUTUBE_CLIENT_SECRET or ""
    if not cid or not secret:
        return False
    if cid.startswith("PEGA_AQUI") or secret.startswith("PEGA_AQUI"):
        return False
    return True


def start_device_flow():
    """
    Inicia el Device Flow. Retorna dict con:
      device_code, user_code, verification_url, interval, expires_in.
    """
    if not _credentials_configured():
        raise AuthorizationError(
            "Faltan las credenciales OAuth (client_id/secret). "
            "Configuralas en config.py o por variables de entorno (ver SETUP-GOOGLE.md)."
        )

    code, data = _http_post_form(
        _OAUTH_DEVICE_CODE_URI,
        {
            "client_id": config.YOUTUBE_CLIENT_ID,
            "scope": " ".join(config.YOUTUBE_SCOPES),
        },
    )

    if code != 200:
        detail = data.get("error_description") or data.get("error") or str(data)
        raise AuthorizationError(f"No se pudo iniciar la vinculacion: {detail}")

    return {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_url": data.get("verification_url") or data.get("verification_uri"),
        "interval": int(data.get("interval", 5)),
        "expires_in": int(data.get("expires_in", 1800)),
    }


def poll_device_flow(device_code):
    """
    Consulta una vez el estado del Device Flow.

    Retorna tupla (status, message):
      - ("authorized", None): el usuario aprobo, tokens guardados.
      - ("pending", None): aun no aprueba.
      - ("slow_down", None): hay que aumentar el intervalo de polling.
      - ("error", "mensaje"): expirado, denegado u otro error.
    """
    code, data = _http_post_form(
        _OAUTH_TOKEN_URI,
        {
            "client_id": config.YOUTUBE_CLIENT_ID,
            "client_secret": config.YOUTUBE_CLIENT_SECRET,
            "device_code": device_code,
            "grant_type": _DEVICE_GRANT_TYPE,
        },
    )

    if code == 200 and "access_token" in data:
        creds = Credentials(
            token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_uri=_OAUTH_TOKEN_URI,
            client_id=config.YOUTUBE_CLIENT_ID,
            client_secret=config.YOUTUBE_CLIENT_SECRET,
            scopes=config.YOUTUBE_SCOPES,
        )
        # Expiry naive en UTC, como espera google-auth.
        creds.expiry = datetime.utcnow() + timedelta(seconds=int(data.get("expires_in", 3600)))
        _save_tokens(creds)
        log.info("Vinculacion completada por Device Flow")
        return "authorized", None

    err = data.get("error")
    if err == "authorization_pending":
        return "pending", None
    if err == "slow_down":
        return "slow_down", None
    if err == "expired_token":
        return "error", "El codigo expiro. Genera uno nuevo."
    if err == "access_denied":
        return "error", "Autorizacion denegada."
    return "error", data.get("error_description") or err or "Error desconocido al vincular."


# ==============================================================================
# SECCION 3: PERSISTENCIA DE TOKENS
# ==============================================================================


def _save_tokens(creds):
    """Guarda credenciales en archivo con permisos restringidos."""
    # Preservar refresh_token anterior si no viene en la respuesta.
    refresh_token = creds.refresh_token
    if not refresh_token and config.YOUTUBE_TOKENS_FILE.exists():
        try:
            with open(config.YOUTUBE_TOKENS_FILE) as f:
                previous = json.load(f)
            refresh_token = previous.get("refresh_token")
        except Exception:
            pass

    token_data = {
        "token": creds.token,
        "refresh_token": refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else config.YOUTUBE_SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }

    fd = os.open(config.YOUTUBE_TOKENS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(token_data, f)

    log.info("Tokens guardados, expiran: %s", creds.expiry)


def _load_credentials():
    """Carga credenciales desde archivo."""
    if not config.YOUTUBE_TOKENS_FILE.exists():
        return None

    try:
        with open(config.YOUTUBE_TOKENS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        _invalidate_tokens_file()
        return None

    if "token" not in data:
        _invalidate_tokens_file()
        return None

    expiry = None
    if data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(data["expiry"])
        except ValueError:
            pass

    return Credentials(
        token=data["token"],
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", _OAUTH_TOKEN_URI),
        client_id=data.get("client_id", config.YOUTUBE_CLIENT_ID),
        client_secret=data.get("client_secret", config.YOUTUBE_CLIENT_SECRET),
        scopes=data.get("scopes", config.YOUTUBE_SCOPES),
        expiry=expiry,
    )


def _invalidate_tokens_file():
    """Elimina archivo de tokens invalidos."""
    try:
        os.remove(config.YOUTUBE_TOKENS_FILE)
    except FileNotFoundError:
        pass


# ==============================================================================
# SECCION 4: REFRESH DE CREDENCIALES
# ==============================================================================


def _is_invalid_grant_error(error):
    """Detecta error de token expirado/revocado."""
    text = str(error).lower()
    return "invalid_grant" in text or "expired or revoked" in text


def _needs_refresh(creds):
    """Determina si el token necesita refresh (expirado o proximo a expirar)."""
    if not creds.expiry:
        return True

    now = datetime.now(timezone.utc)
    if creds.expiry.tzinfo is None:
        expiry = creds.expiry.replace(tzinfo=timezone.utc)
    else:
        expiry = creds.expiry

    return now >= (expiry - TOKEN_REFRESH_BUFFER)


def _refresh_credentials(creds):
    """Refresca credenciales si estan expiradas o proximas a expirar."""
    if creds.valid and not _needs_refresh(creds):
        return creds

    if not creds.refresh_token:
        _invalidate_tokens_file()
        raise AuthorizationError(AUTH_REQUIRED_MESSAGE)

    try:
        log.info("Refrescando token OAuth...")
        creds.refresh(Request())
        _save_tokens(creds)
        log.info("Token refrescado exitosamente")
    except RefreshError as e:
        if _is_invalid_grant_error(e):
            _invalidate_tokens_file()
            raise AuthorizationError(AUTH_REVOKED_MESSAGE) from e
        raise AuthorizationError(f"No se pudo refrescar credenciales: {e}") from e

    return creds


# ==============================================================================
# SECCION 5: VERIFICACION DE AUTORIZACION
# ==============================================================================


def is_authorized():
    """Verifica si la aplicacion esta vinculada y con token utilizable."""
    creds = _load_credentials()
    if creds is None:
        return False
    try:
        _refresh_credentials(creds)
        return True
    except AuthorizationError:
        return False


def assert_authorized():
    """Lanza excepcion si no esta vinculado."""
    creds = _load_credentials()
    if creds is None or not creds.refresh_token:
        raise AuthorizationError(AUTH_REQUIRED_MESSAGE)
    _refresh_credentials(creds)


def ensure_fresh_token():
    """Refresca el token proactivamente si esta proximo a expirar."""
    creds = _load_credentials()
    if creds is None:
        return False
    if not creds.refresh_token:
        return False
    try:
        _refresh_credentials(creds)
        return True
    except AuthorizationError:
        return False


def unlink():
    """Desvincula la cuenta borrando los tokens locales."""
    _invalidate_tokens_file()


# ==============================================================================
# SECCION 6: YOUTUBE SERVICE
# ==============================================================================


def _get_youtube_service():
    """Construye servicio de YouTube API autorizado."""
    creds = _load_credentials()
    if creds is None or not creds.refresh_token:
        raise AuthorizationError(AUTH_REQUIRED_MESSAGE)

    creds = _refresh_credentials(creds)
    return build("youtube", "v3", credentials=creds)


def _now_iso():
    """Retorna timestamp ISO8601 actual en UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def get_channel_info():
    """Devuelve {'id', 'title'} del canal de YouTube vinculado al token actual."""
    youtube = _get_youtube_service()
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])
    if not items:
        return None
    channel = items[0]
    return {
        "id": channel["id"],
        "title": channel.get("snippet", {}).get("title", ""),
    }


# ==============================================================================
# SECCION 7: STREAMS Y BROADCASTS
# ==============================================================================


def get_or_create_stream(youtube=None):
    """
    Obtiene (o crea) un stream RTMP reusable en la cuenta conectada.

    Estrategia:
      1. Reusar el stream que esta app creo antes (por titulo STREAM_TITLE).
      2. Si no, reusar el primer stream RTMP existente.
      3. Si no hay ninguno, crear uno nuevo reusable.

    Returns:
        tuple: (stream_id, rtmp_url) donde rtmp_url ya incluye la stream key.
    """
    if youtube is None:
        youtube = _get_youtube_service()

    response = youtube.liveStreams().list(part="cdn,snippet,contentDetails", mine=True).execute()
    items = response.get("items", [])

    chosen = None

    # 1. Preferir el stream creado por esta app.
    for stream in items:
        if stream.get("snippet", {}).get("title") == config.STREAM_TITLE:
            chosen = stream
            break

    # 2. Si no, el primer stream RTMP disponible.
    if chosen is None:
        for stream in items:
            if stream.get("cdn", {}).get("ingestionType") == "rtmp":
                chosen = stream
                break

    # 3. Si no hay ninguno, crear uno nuevo reusable.
    if chosen is None:
        chosen = youtube.liveStreams().insert(
            part="snippet,cdn,contentDetails",
            body={
                "snippet": {"title": config.STREAM_TITLE},
                "cdn": {
                    "frameRate": "variable",
                    "ingestionType": "rtmp",
                    "resolution": "variable",
                },
                "contentDetails": {"isReusable": True},
            },
        ).execute()

    ingestion = chosen.get("cdn", {}).get("ingestionInfo", {})
    address = ingestion.get("ingestionAddress")
    stream_name = ingestion.get("streamName")

    if not address or not stream_name:
        raise RuntimeError("La respuesta de YouTube no incluyo la direccion RTMP del stream.")

    rtmp_url = f"{address}/{stream_name}"
    return chosen["id"], rtmp_url


def create_broadcast(title=None, privacy="unlisted"):
    """
    Crea un broadcast en vivo, obtiene/crea el stream y los vincula.

    Returns:
        tuple: (broadcast_id, share_url, rtmp_url)
    """
    if not title:
        title = config.DEFAULT_STREAM_TITLE

    youtube = _get_youtube_service()

    broadcast_body = {
        "snippet": {
            "title": title,
            "scheduledStartTime": _now_iso(),
        },
        "contentDetails": {
            "enableAutoStart": True,
            "enableAutoStop": True,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    try:
        broadcast = youtube.liveBroadcasts().insert(
            part="snippet,contentDetails,status",
            body=broadcast_body,
        ).execute()
    except HttpError as e:
        status = getattr(getattr(e, "resp", None), "status", None)
        if status == 401:
            _invalidate_tokens_file()
            raise AuthorizationError(AUTH_REVOKED_MESSAGE) from e
        raise

    broadcast_id = broadcast["id"]

    # Obtener/crear stream y vincular.
    stream_id, rtmp_url = get_or_create_stream(youtube)

    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

    share_url = f"https://youtube.com/watch?v={broadcast_id}"
    return broadcast_id, share_url, rtmp_url


def end_broadcast(broadcast_id):
    """Finaliza un broadcast en vivo."""
    if not broadcast_id:
        return

    try:
        youtube = _get_youtube_service()
        youtube.liveBroadcasts().transition(
            broadcastStatus="complete",
            id=broadcast_id,
            part="id,status",
        ).execute()
    except HttpError as e:
        if "redundantTransition" not in str(e):
            raise
