#!/usr/bin/env python3
"""
Stream Manager - rpi-youtube-stream
===================================
Gestion del pipeline de streaming: libcamera-vid | ffmpeg | ffplay

La URL RTMP (direccion + stream key) la entrega youtube_api por API y se pasa
a start(); ya no se lee una stream key fija de la configuracion.

Estados:
  - idle: sin transmision
  - preparing: creando broadcast en YouTube
  - starting: pipeline iniciando
  - streaming: en vivo
  - stopping: deteniendo procesos
  - error: fallo en el pipeline

Pipeline:
  libcamera-vid -> tee -> ffmpeg (RTMP YouTube)
                     -> ffplay (preview LCD)

Autor: Andres Mercado
"""

import collections
import os
import signal
import subprocess
import threading
import time
import zoneinfo
from datetime import datetime

import config


# ==============================================================================
# SECCION 0: CONSTANTES
# ==============================================================================

LOG_BUFFER_SIZE = 200
LONDON_TZ = zoneinfo.ZoneInfo("Europe/London")

STATE_IDLE = "idle"
STATE_PREPARING = "preparing"
STATE_STARTING = "starting"
STATE_STREAMING = "streaming"
STATE_STOPPING = "stopping"
STATE_ERROR = "error"


# ==============================================================================
# SECCION 1: CLASE PRINCIPAL
# ==============================================================================


class StreamManager:
    """
    Gestiona el ciclo de vida del pipeline de streaming.

    Thread-safe mediante lock interno.
    """

    def __init__(self):
        self._process = None
        self._state = STATE_IDLE
        self._error_message = None
        self._cancelled = False
        self._rtmp_url = None
        self._lock = threading.Lock()
        self._logs = collections.deque(maxlen=LOG_BUFFER_SIZE)

    # -------------------------------------------------------------------------
    # Propiedades
    # -------------------------------------------------------------------------

    @property
    def state(self):
        return self._state

    @property
    def error_message(self):
        return self._error_message

    @property
    def cancelled(self):
        return self._cancelled

    # -------------------------------------------------------------------------
    # Logs
    # -------------------------------------------------------------------------

    def get_logs(self):
        """Retorna copia de los logs."""
        with self._lock:
            return list(self._logs)

    def add_log(self, message):
        """Agrega entrada al log con timestamp."""
        ts = datetime.now(LONDON_TZ).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            self._logs.append(f"[{ts}] {message}")

    def clear_logs(self):
        """Limpia el buffer de logs."""
        with self._lock:
            self._logs.clear()

    # -------------------------------------------------------------------------
    # Control de estado
    # -------------------------------------------------------------------------

    def set_preparing(self):
        """Transiciona a estado 'preparing'."""
        with self._lock:
            if self._state not in (STATE_IDLE, STATE_ERROR):
                raise RuntimeError(f"No se puede iniciar desde estado: {self._state}")
            self._state = STATE_PREPARING
            self._error_message = None
            self._cancelled = False

    def reset_to_idle(self):
        """Fuerza transicion a 'idle' (usado tras cancelacion)."""
        with self._lock:
            self._state = STATE_IDLE
            self._error_message = None

    # -------------------------------------------------------------------------
    # Inicio de streaming
    # -------------------------------------------------------------------------

    def start(self, rtmp_url):
        """Inicia el pipeline de streaming hacia la URL RTMP dada."""
        if not rtmp_url:
            raise RuntimeError("No se recibio la URL RTMP del stream.")

        with self._lock:
            if self._cancelled:
                raise RuntimeError("Inicio cancelado")
            if self._state != STATE_PREPARING:
                raise RuntimeError(f"No se puede iniciar desde estado: {self._state}")
            self._state = STATE_STARTING
            self._rtmp_url = rtmp_url

        try:
            cmd = self._build_command(rtmp_url)
            env = self._build_env()

            self.add_log(f"Lanzando pipeline: {config.VIDEO_BIN} | ffmpeg | ffplay")

            self._process = subprocess.Popen(
                ["bash", "-c", cmd],
                preexec_fn=os.setsid,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=env,
            )

            threading.Thread(target=self._read_stderr_loop, daemon=True).start()
            threading.Thread(target=self._monitor, daemon=True).start()
            threading.Thread(target=self._health_check, daemon=True).start()

        except Exception as e:
            with self._lock:
                self._state = STATE_ERROR
                self._error_message = str(e)
            self.add_log(f"ERROR: {e}")
            raise

    def _build_env(self):
        """Construye variables de entorno para el pipeline."""
        env = os.environ.copy()
        env["SDL_FBDEV"] = config.FFPLAY_SDL_FBDEV
        env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
        env.setdefault("DISPLAY", ":0")
        return env

    def _build_command(self, rtmp_url):
        """Construye comando bash del pipeline."""
        # libcamera-vid: captura de video
        libcamera = (
            f"stdbuf -o0 {config.VIDEO_BIN} --nopreview -t 0 "
            f"--width {config.VIDEO_WIDTH} "
            f"--height {config.VIDEO_HEIGHT} "
            f"--framerate {config.VIDEO_FPS} "
            f"--bitrate {config.VIDEO_BITRATE} "
            f"--inline --intra {config.VIDEO_INTRA} "
            f"--codec {config.VIDEO_CODEC} "
            f"--libav-format {config.VIDEO_LIBAV_FORMAT} "
            f"-o -"
        )

        # ffmpeg: mezcla audio + video -> RTMP
        ffmpeg = (
            f"stdbuf -o0 ffmpeg -nostdin "
            f"-thread_queue_size {config.AUDIO_THREAD_QUEUE} -f alsa -i {config.AUDIO_DEVICE} "
            f"-thread_queue_size {config.AUDIO_THREAD_QUEUE} -f {config.VIDEO_LIBAV_FORMAT} -i - "
            f"-c:v copy "
            f"-c:a aac -b:a {config.AUDIO_BITRATE} -ar {config.AUDIO_SAMPLE_RATE} "
            f"-fflags nobuffer -flags low_delay -max_interleave_delta 0 -g {config.VIDEO_INTRA} "
            f'-f flv "{rtmp_url}"'
        )

        # ffplay: preview local en LCD
        ffplay = (
            f"stdbuf -o0 ffplay -fflags nobuffer -flags low_delay -sync ext "
            f"-analyzeduration 0 -probesize 32 -framedrop "
            f'-vf "scale={config.FFPLAY_SCALE}" '
            f"-autoexit -"
        )

        # Pipeline con tee para bifurcar salida
        return f"{libcamera} | tee >({ffmpeg}) >({ffplay} 2>/dev/null || true) > /dev/null"

    # -------------------------------------------------------------------------
    # Detencion de streaming
    # -------------------------------------------------------------------------

    def stop(self):
        """Detiene el pipeline de forma ordenada."""
        with self._lock:
            if self._state not in (STATE_STREAMING, STATE_STARTING, STATE_PREPARING, STATE_ERROR):
                self.add_log(f"Stop ignorado: estado actual es {self._state}")
                return False
            self._cancelled = True
            self._state = STATE_STOPPING

        self.add_log("Deteniendo procesos...")
        self._kill_all()
        self.add_log("Procesos terminados")

        with self._lock:
            self._state = STATE_IDLE
            self._error_message = None

        self.add_log("Transmision detenida")
        return True

    def force_reset(self):
        """Reinicio de emergencia: mata todos los procesos."""
        self.add_log("REINICIO DE EMERGENCIA solicitado")

        with self._lock:
            self._cancelled = True
            self._state = STATE_STOPPING

        self._kill_all()

        with self._lock:
            self._state = STATE_IDLE
            self._error_message = None
            self._process = None

        self.add_log("Estado reiniciado a idle")

    def _kill_all(self):
        """Termina todos los procesos del pipeline."""
        if self._process is not None:
            self._terminate_process_group()
            self._process = None

        for name in [config.VIDEO_BIN, "ffmpeg", "ffplay"]:
            subprocess.run(
                ["pkill", "-9", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    def _terminate_process_group(self):
        """Envia SIGTERM/SIGKILL al grupo de procesos."""
        try:
            pgid = os.getpgid(self._process.pid)
            os.killpg(pgid, signal.SIGTERM)
            self.add_log(f"SIGTERM enviado a grupo {pgid}")
        except (ProcessLookupError, OSError):
            return

        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                pgid = os.getpgid(self._process.pid)
                os.killpg(pgid, signal.SIGKILL)
                self.add_log(f"SIGKILL enviado a grupo {pgid}")
            except (ProcessLookupError, OSError):
                pass

    # -------------------------------------------------------------------------
    # Monitoreo
    # -------------------------------------------------------------------------

    def _read_stderr_loop(self):
        """Lee stderr del proceso y lo agrega a logs."""
        proc = self._process
        if proc is None or proc.stderr is None:
            return

        try:
            for raw_line in iter(proc.stderr.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                if line:
                    self.add_log(line)
        except (ValueError, OSError):
            pass

    def _health_check(self):
        """Verifica que el proceso inicio correctamente."""
        time.sleep(config.HEALTH_CHECK_DELAY)

        with self._lock:
            if self._state != STATE_STARTING:
                return

            if self._process is None or self._process.poll() is not None:
                self._state = STATE_ERROR
                self._error_message = "Proceso termino durante inicio"
                return

            self._state = STATE_STREAMING

        self.add_log("Estado: EN VIVO")

    def _monitor(self):
        """Monitorea proceso y detecta terminacion inesperada."""
        proc = self._process
        if proc is None:
            return

        proc.wait()

        with self._lock:
            if self._state == STATE_STREAMING:
                self._state = STATE_ERROR
                self._error_message = "Proceso termino inesperadamente"
                self.add_log("ERROR: Proceso termino inesperadamente")
