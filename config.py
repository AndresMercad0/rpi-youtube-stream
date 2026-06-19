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
  - Preview: ffplay sobre framebuffer LCD

A diferencia de la version original, aqui NO hay stream key fija: la app
descubre o crea el stream por API una vez que la cuenta inicia sesion.
El cliente OAuth es de tipo "TV and Limited Input devices" (Device Flow).

Autor: Andres Mercado
"""

import os
from pathlib import Path

# ==============================================================================
# SECCION 0: PATHS Y MARCA
# ==============================================================================

APP_DIR = Path(__file__).resolve().parent

# Nombre visible de la app (puedes sobreescribirlo con la variable BRAND_NAME).
BRAND_NAME = os.environ.get("BRAND_NAME", "Transmision en vivo")

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
# Binario de captura. En Raspberry Pi OS Bookworm puede ser "rpicam-vid".

VIDEO_BIN = os.environ.get("VIDEO_BIN", "libcamera-vid")
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
# SECCION 5: PREVIEW (FFPLAY + FRAMEBUFFER LCD)
# ==============================================================================

FFPLAY_SDL_FBDEV = os.environ.get("FFPLAY_SDL_FBDEV", "/dev/fb1")
FFPLAY_SCALE = os.environ.get("FFPLAY_SCALE", "482:257")

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
