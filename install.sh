#!/usr/bin/env bash
# =============================================================================
# rpi-youtube-stream - Instalador de un comando
# =============================================================================
# Uso (en la Raspberry Pi, dentro de la carpeta del repo clonado):
#
#   ./install.sh
#
# Opciones:
#   --with-cloudflared   Instala tambien el binario de cloudflared (para exponer
#                        el panel de forma remota mediante un tunel de Cloudflare).
#
# Que hace:
#   1. Instala dependencias del sistema (python3, ffmpeg, camara).
#   2. Crea un entorno virtual e instala las dependencias de Python.
#   3. Instala y arranca el servicio systemd (rpi-youtube-stream).
#
# No requiere editar archivos: la vinculacion con YouTube se hace despues desde
# el navegador (boton "Vincular con YouTube").
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Parametros
# -----------------------------------------------------------------------------
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="rpi-youtube-stream"
RUN_USER="${SUDO_USER:-$USER}"
PORT="${PORT:-8082}"
WITH_CLOUDFLARED=0

for arg in "$@"; do
    case "$arg" in
        --with-cloudflared) WITH_CLOUDFLARED=1 ;;
        *) echo "Opcion desconocida: $arg"; exit 1 ;;
    esac
done

echo "==================================================================="
echo " Instalando $SERVICE_NAME"
echo "   Directorio : $INSTALL_DIR"
echo "   Usuario    : $RUN_USER"
echo "   Puerto     : $PORT"
echo "==================================================================="

# -----------------------------------------------------------------------------
# 1. Dependencias del sistema
# -----------------------------------------------------------------------------
echo
echo "==> [1/5] Instalando dependencias del sistema..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip ffmpeg alsa-utils

# Camara: el binario puede ser libcamera-vid (Bullseye) o rpicam-vid (Bookworm).
if ! command -v libcamera-vid >/dev/null 2>&1 && ! command -v rpicam-vid >/dev/null 2>&1; then
    echo "==> Instalando apps de camara..."
    sudo apt-get install -y libcamera-apps 2>/dev/null \
        || sudo apt-get install -y rpicam-apps 2>/dev/null \
        || echo "AVISO: no se pudo instalar libcamera-apps/rpicam-apps automaticamente."
fi

# Detectar el binario de camara disponible y avisar si difiere del default.
if command -v libcamera-vid >/dev/null 2>&1; then
    echo "    Camara: usando 'libcamera-vid'."
elif command -v rpicam-vid >/dev/null 2>&1; then
    echo "    Camara: detectado 'rpicam-vid'. Configura VIDEO_BIN=rpicam-vid en .env"
    echo "            (copia .env.example a .env y descomenta esa linea)."
else
    echo "    AVISO: no se encontro libcamera-vid ni rpicam-vid. Instalalo antes de transmitir."
fi

# -----------------------------------------------------------------------------
# 2. Entorno virtual de Python
# -----------------------------------------------------------------------------
echo
echo "==> [2/5] Creando entorno virtual de Python..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# -----------------------------------------------------------------------------
# 3. (Opcional) cloudflared
# -----------------------------------------------------------------------------
if [ "$WITH_CLOUDFLARED" -eq 1 ]; then
    echo
    echo "==> Instalando cloudflared..."
    if ! command -v cloudflared >/dev/null 2>&1; then
        ARCH="$(dpkg --print-architecture)"
        URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
        curl -L "$URL" -o /tmp/cloudflared.deb
        sudo dpkg -i /tmp/cloudflared.deb
        echo "    cloudflared instalado. Configura el tunel manualmente (ver README.md)."
    else
        echo "    cloudflared ya estaba instalado."
    fi
fi

# -----------------------------------------------------------------------------
# 4. Credenciales OAuth (.env, no se versiona)
# -----------------------------------------------------------------------------
echo
echo "==> [3/5] Configurando credenciales de YouTube..."
ENV_FILE="$INSTALL_DIR/.env"

if [ -f "$ENV_FILE" ] && grep -q "^YT_CLIENT_ID=" "$ENV_FILE"; then
    echo "    Ya existen credenciales en $ENV_FILE. Se conservan."
elif [ -t 0 ]; then
    echo "    Pega las credenciales del cliente OAuth de tipo 'TV and Limited Input"
    echo "    devices' (Google Cloud Console). Ver SETUP-GOOGLE.md."
    echo
    read -rp "    YT_CLIENT_ID: " YT_CID
    read -rp "    YT_CLIENT_SECRET: " YT_CSECRET
    touch "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    {
        echo "YT_CLIENT_ID=$YT_CID"
        echo "YT_CLIENT_SECRET=$YT_CSECRET"
    } >> "$ENV_FILE"
    echo "    Guardadas en $ENV_FILE (permisos 600)."
else
    echo "    AVISO: sin terminal interactiva y sin .env."
    echo "    Crea $ENV_FILE con YT_CLIENT_ID y YT_CLIENT_SECRET antes de transmitir"
    echo "    (copia .env.example a .env). La app arranca, pero no podra vincular."
fi

# -----------------------------------------------------------------------------
# 5. Servicio systemd
# -----------------------------------------------------------------------------
echo
echo "==> [4/5] Instalando servicio systemd ($SERVICE_NAME)..."
sudo tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null <<EOF
[Unit]
Description=rpi-youtube-stream API server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=-$INSTALL_DIR/.env
Environment=PORT=$PORT
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo
echo "==> [5/5] Habilitando y arrancando el servicio..."
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

# -----------------------------------------------------------------------------
# Resumen
# -----------------------------------------------------------------------------
sleep 2
echo
echo "==================================================================="
echo " Listo. El servicio esta corriendo."
echo "==================================================================="
echo
echo " 1. Abre el panel:   http://localhost:$PORT"
echo "    (o desde otro dispositivo:  http://<IP-de-la-Pi>:$PORT )"
echo
echo " 2. Haz clic en 'Vincular con YouTube' e inicia sesion con tu cuenta."
echo
echo " Comandos utiles:"
echo "    Ver logs:     sudo journalctl -u $SERVICE_NAME -f"
echo "    Reiniciar:    sudo systemctl restart $SERVICE_NAME"
echo "    Estado:       sudo systemctl status $SERVICE_NAME"
echo
