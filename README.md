# rpi-youtube-stream

Transmite video en vivo a YouTube desde una Raspberry Pi con camara y microfono
USB, controlado desde un panel web. Pensado para clonar e instalar con un solo
comando, y vincular YouTube iniciando sesion desde el navegador (sin tocar nada
en Google).

Captura camara + microfono, los envia en vivo a YouTube por RTMP, y muestra un
preview en una pantalla LCD.

---

## Inicio rapido (en la Raspberry Pi)

```bash
git clone https://github.com/AndresMercad0/rpi-youtube-stream.git
cd rpi-youtube-stream
./install.sh
```

Durante `install.sh` se te piden una vez el **Client ID** y **Client Secret**
de Google (se guardan en un `.env` local, no en el repo). Luego:

1. Abre el panel: `http://localhost:8082` (o `http://<IP-de-la-Pi>:8082` desde otro dispositivo).
2. Clic en **"Vincular con YouTube"** e inicia sesion con tu cuenta de Google.
3. Escribe un titulo y clic en **"Iniciar Transmisión"**.

Eso es todo. No hay stream key que copiar ni configuracion en YouTube Studio: la
app crea el stream por API en la cuenta que inicia sesion.

> **Antes del primer uso**, el dueno del repo debe hacer un setup unico en Google
> (crear el cliente OAuth de tipo dispositivo) y tener a la mano el Client ID y
> Secret para darselos al instalador. Ver **[SETUP-GOOGLE.md](SETUP-GOOGLE.md)**.
> Es una sola vez, no por cada Pi.

---

## Que necesitas

### Hardware
- Raspberry Pi con modulo de camara.
- Microfono USB.
- Pantalla LCD (opcional, para el preview).

### Software
Lo instala `install.sh` automaticamente: Python 3, ffmpeg, `libcamera-vid`
(o `rpicam-vid`), y las dependencias de Python.

---

## Como vincula con YouTube (Device Flow)

La vinculacion usa **OAuth 2.0 Device Flow** (el mismo metodo de los smart TVs):
la app muestra un codigo y un QR, la persona inicia sesion en su telefono, y
listo. No requiere dominio publico ni redirect URIs.

El video se transmite **en el canal de la cuenta que inicia sesion**, no en el
del dueno de la app. Los tokens se guardan localmente en cada Pi
(`.youtube_tokens.json`, nunca se versiona).

---

## Acceso remoto (opcional)

Por defecto el panel se ve en la red local (`http://<IP-de-la-Pi>:8082`). Para
abrirlo desde cualquier lugar, puedes exponerlo con un tunel de Cloudflare:

```bash
./install.sh --with-cloudflared
```

Eso instala el binario `cloudflared`. Los pasos completos para crear el tunel
(login, DNS y servicio), listos para copiar y pegar, estan en
**[CLOUDFLARE.md](CLOUDFLARE.md)**. El acceso remoto es solo para el panel;
**no** tiene relacion con la vinculacion de YouTube (esa funciona por Device Flow
sin dominio).

---

## Opciones avanzadas

En el panel, el botón **"Opciones avanzadas"** abre dos controles:

- **Transmitir sin micrófono:** por defecto la app exige un micrófono. Con este
  interruptor activo puedes iniciar sin micrófono; el audio se envía en silencio
  (una pista de silencio, para que YouTube reciba un stream bien formado).
- **Conexión WiFi:** la Pi se espera conectada por cable, pero desde aquí puedes
  buscar redes WiFi y conectarte (útil para pasar a WiFi y luego quitar el cable).
  El header muestra un indicador de si estás por **cable**, **WiFi** o **sin internet**.

> La conexión WiFi usa NetworkManager (`nmcli`) con un permiso sudo acotado que
> agrega `install.sh`. Si actualizas una Pi ya instalada y quieres esta función,
> vuelve a correr `./install.sh` (no solo `git pull`).

---

## Estructura

```
rpi-youtube-stream/
├── install.sh             # Instalador de un comando
├── app.py                 # Backend Flask (API + Device Flow)
├── config.py              # Configuracion (credenciales OAuth, hardware)
├── youtube_api.py         # Device Flow + Live Streaming API (auto-stream)
├── stream_manager.py      # Pipeline libcamera-vid | ffmpeg | ffplay
├── settings.py            # Ajustes editables (opciones avanzadas)
├── network.py             # Estado de red y WiFi (nmcli)
├── requirements.txt
├── .env.example           # Overrides opcionales
├── SETUP-GOOGLE.md         # Setup unico del dueno (cliente OAuth)
├── CLOUDFLARE.md           # Guia de acceso remoto (Cloudflare Tunnel)
└── static/                # Panel web (HTML/CSS/JS)
```

---

## Comandos utiles

```bash
# Ver logs en vivo
sudo journalctl -u rpi-youtube-stream -f

# Reiniciar / estado
sudo systemctl restart rpi-youtube-stream
sudo systemctl status rpi-youtube-stream
```

---

## Solucion de problemas

- **"YouTube no vinculado":** abre `/auth` y vincula. Si expiro, vuelve a vincular.
- **"Microfono no detectado":** revisa `arecord -l` y ajusta `AUDIO_DEVICE` en `.env`.
- **La camara no inicia:** verifica el binario. En Raspberry Pi OS Bookworm puede
  ser `rpicam-vid`; en ese caso pon `VIDEO_BIN=rpicam-vid` en `.env`. Prueba:
  `libcamera-vid --list-cameras` o `rpicam-vid --list-cameras`.
- **Aparece "Google no ha verificado esta app":** es normal (ver SETUP-GOOGLE.md).
  Clic en "Avanzado" y luego en el nombre de la app para continuar.

---

## Autor

Andres Mercado
