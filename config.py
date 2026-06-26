#!/usr/bin/env python3
"""
Configuracion - rpi-youtube-stream
==================================
Raspberry Pi Camera + YouTube Live Streaming.

Modulos:
  - Flask: servidor web API
  - YouTube: OAuth2 Device Flow + Live Streaming API
  - Video: libcamera-vid (RPi Camera Module)
  - Audio: ALSA + ffmpeg
  - Preview: ffmpeg -f fbdev sobre el framebuffer de la LCD (sin escritorio)

A diferencia de la version original, aqui NO hay stream key fija: la app
descubre o crea el stream por API una vez que la cuenta inicia sesion.
El cliente OAuth es de tipo "TV and Limited Input devices" (Device Flow).

Autor: Andres Mercado
"""

import os
import shutil
from pathlib import Path

# ==============================================================================
# SECCION 0: PATHS Y MARCA
# ==============================================================================

APP_DIR = Path(__file__).resolve().parent

# Nombre visible de la app, mostrado en el header (NO es un indicador de estado).
# Puedes personalizarlo por Pi con la variable BRAND_NAME (ej. un nombre o marca).
BRAND_NAME = os.environ.get("BRAND_NAME", "Transmision")

# Titulo por defecto del broadcast cuando el usuario no escribe uno.
DEFAULT_STREAM_TITLE = os.environ.get("DEFAULT_STREAM_TITLE", "Transmision en vivo")

# ==============================================================================
# SECCION 1: FLASK (SERVIDOR WEB)
# ==============================================================================

PORT = int(os.environ.get("PORT", "8082"))
HOST = os.environ.get("HOST", "0.0.0.0")

# ==============================================================================
# SECCION 2: YOUTUBE - CLIENTE OAUTH (DEVICE FLOW)
# ==============================================================================
#
# Estos dos valores los obtienes UNA sola vez al crear un cliente OAuth de tipo
# "TV and Limited Input devices" en Google Cloud Console (ver SETUP-GOOGLE.md).
# Son los MISMOS para todas las Raspberry Pi que usen este repo.
#
# NO se versionan: viven en el archivo .env (ignorado por git). El instalador
# (install.sh) te los pide y crea el .env la primera vez en cada Pi. Tambien
# puedes ponerlos a mano (ver .env.example).

YOUTUBE_CLIENT_ID = os.environ.get(
    "YT_CLIENT_ID",
    "PEGA_AQUI_TU_CLIENT_ID.apps.googleusercontent.com",
)
YOUTUBE_CLIENT_SECRET = os.environ.get(
    "YT_CLIENT_SECRET",
    "PEGA_AQUI_TU_CLIENT_SECRET",
)

YOUTUBE_TOKENS_FILE = APP_DIR / ".youtube_tokens.json"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube"]

# Titulo del stream reusable que la app crea/usa en la cuenta conectada.
STREAM_TITLE = os.environ.get("STREAM_TITLE", "rpi-youtube-stream")

# ==============================================================================
# SECCION 3: VIDEO (LIBCAMERA-VID)
# ==============================================================================
# Binario de captura de la camara. En Raspberry Pi OS reciente (Bookworm/Trixie)
# es "rpicam-vid"; en versiones anteriores, "libcamera-vid". Se auto-detecta el
# que exista; se puede forzar con la variable de entorno VIDEO_BIN.

def _detect_video_bin():
    for candidate in ("rpicam-vid", "libcamera-vid"):
        if shutil.which(candidate):
            return candidate
    return "libcamera-vid"


VIDEO_BIN = os.environ.get("VIDEO_BIN") or _detect_video_bin()
VIDEO_WIDTH = 2028
VIDEO_HEIGHT = 1080
VIDEO_FPS = 50
VIDEO_BITRATE = 6_000_000  # 6 Mbps
VIDEO_CODEC = "libav"
VIDEO_LIBAV_FORMAT = "mpegts"
VIDEO_INTRA = 100  # keyframe interval (frames)

# ==============================================================================
# SECCION 4: AUDIO (ALSA + FFMPEG)
# ==============================================================================

AUDIO_DEVICE = os.environ.get("AUDIO_DEVICE", "plughw:0,0")
AUDIO_SAMPLE_RATE = 44100
AUDIO_BITRATE = "160k"
AUDIO_THREAD_QUEUE = 512

# ==============================================================================
# SECCION 5: PREVIEW (FFMPEG -> FRAMEBUFFER LCD)
# ==============================================================================
# El preview se dibuja directo al framebuffer de la LCD con ffmpeg, sin necesitar
# escritorio/X. Se auto-detectan el dispositivo, la resolucion y el formato de
# pixel. Todo es sobreescribible por variables de entorno.

def _detect_fbdev():
    for fb in ("/dev/fb1", "/dev/fb0"):
        if os.path.exists(fb):
            return fb
    return "/dev/fb1"


PREVIEW_FBDEV = os.environ.get("PREVIEW_FBDEV") or _detect_fbdev()


def _fb_sysfs(attr):
    name = os.path.basename(PREVIEW_FBDEV)
    try:
        with open(f"/sys/class/graphics/{name}/{attr}") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _detect_preview_scale():
    size = _fb_sysfs("virtual_size")  # p.ej. "480,320"
    if size and "," in size:
        w, h = size.split(",")[:2]
        if w.isdigit() and h.isdigit():
            return f"{w}:{h}"
    return "480:320"


def _detect_preview_pixfmt():
    # 16 bpp (lo usual en LCD SPI) -> rgb565le; 32 bpp -> bgra.
    return "bgra" if _fb_sysfs("bits_per_pixel") == "32" else "rgb565le"


PREVIEW_SCALE = os.environ.get("PREVIEW_SCALE") or _detect_preview_scale()
PREVIEW_PIXFMT = os.environ.get("PREVIEW_PIXFMT") or _detect_preview_pixfmt()
PREVIEW_FPS = int(os.environ.get("PREVIEW_FPS", "15"))


def _detect_font():
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.exists(path):
            return path
    return None


# Pantalla de espera / mensajes en la LCD cuando no se transmite.
PREVIEW_FONT = os.environ.get("PREVIEW_FONT") or _detect_font()
STANDBY_SUBTITLE = os.environ.get("STANDBY_SUBTITLE", "Listo para transmitir")
PREPARING_SUBTITLE = os.environ.get("PREPARING_SUBTITLE", "Preparando transmision...")

# ==============================================================================
# SECCION 6: HEALTH CHECK
# ==============================================================================

HEALTH_CHECK_DELAY = 3  # segundos despues de inicio para verificar proceso

# ==============================================================================
# SECCION 7: VISITANTES (LINK INTERMEDIO)
# ==============================================================================

VISITORS_LOG_FILE = APP_DIR / ".visitors.csv"
VISITORS_LOG_FIELDS = ["timestamp", "broadcast_id", "nombre", "ip", "city", "country", "user_agent"]

# ==============================================================================
# SECCION 8: AJUSTES EDITABLES (OPCIONES AVANZADAS)
# ==============================================================================

SETTINGS_FILE = APP_DIR / ".settings.json"
