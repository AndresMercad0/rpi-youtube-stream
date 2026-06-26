# Ajustes del sistema en la Raspberry Pi (fuera del repo)

Estos son ajustes a nivel del **sistema operativo** de la Pi que `install.sh` NO
hace (porque son del SO, o dependen de la ubicacion/hardware) y que conviene
tener documentados para reproducir el despliegue en otra Pi.

El codigo de la app NO los necesita versionados; viven en la Pi.

---

## 1. Arrancar en consola (sin escritorio)

La app no necesita escritorio: corre como servicio systemd y dibuja el preview
directo al framebuffer de la LCD. Si la Pi trae escritorio (por ejemplo, instalado
junto con la pantalla via `goodtft/LCD-show`), quitarlo:
- elimina el error de PolicyKit que sale al arrancar, y
- libera la pantalla (framebuffer) para el preview de la camara.

```bash
sudo systemctl set-default multi-user.target
sudo systemctl disable lightdm
```

Ademas, `LCD-show` suele lanzar el escritorio con `startx` desde el login. Comenta
esas lineas en `~/.bash_profile`:

```bash
sed -i 's|^export FRAMEBUFFER=|#&|; s|^startx|#&|' ~/.bash_profile
```

## 2. Ocultar el cursor de la consola en la LCD

Sin escritorio, la consola comparte la pantalla con el preview y su cursor
parpadea encima (se ve un cuadrito). Para ocultarlo, agrega a `~/.bash_profile`:

```bash
[ "$(tty)" = "/dev/tty1" ] && setterm --cursor off 2>/dev/null
```

Alternativa a nivel kernel (si `setterm` no basta): agregar
`vt.global_cursor_default=0` al final de la unica linea de
`/boot/firmware/cmdline.txt` y reiniciar.

## 3. Pais de WiFi (regulatorio)

Para que el WiFi escanee y conecte, el kernel necesita el pais configurado; si no,
el radio queda bloqueado por `rfkill`. Usa el codigo del pais donde **opera** la Pi:

```bash
sudo raspi-config nonint do_wifi_country FR   # FR, MX, US, GB, ES, ...
sudo rfkill unblock wifi
sudo nmcli radio wifi on
sudo systemctl restart NetworkManager
```

Verifica con `nmcli dev wifi list` (debe listar redes) e `iw reg get` (debe decir
`country FR`).

## 4. Permiso para conectar WiFi desde la app

`install.sh` agrega una regla sudoers acotada a `nmcli`
(`/etc/sudoers.d/rpi-youtube-stream`). Si actualizas una Pi ya instalada y quieres
la funcion de WiFi, vuelve a correr `./install.sh`.

## 5. Acceso remoto (tunel de Cloudflare)

Opcional, para abrir el panel desde internet. Pasos en **[CLOUDFLARE.md](CLOUDFLARE.md)**.

## 6. Credenciales OAuth

Van en `.env` (no en el repo). `install.sh` las pide la primera vez. Ver
**[SETUP-GOOGLE.md](SETUP-GOOGLE.md)**.

---

## Notas del despliegue actual (referencia)

- **Hardware:** Raspberry Pi 5, camara HQ (sensor IMX477), LCD SPI tactil
  480x320 a 16 bpp (queda como `/dev/fb0`).
- **SO:** Raspberry Pi OS Trixie (Debian 13). Binario de camara: `rpicam-vid`
  (la Pi 5 no tiene encoder H264 por hardware, por eso se codifica con `libav`).
- **Red:** tambien corre Tailscale (acceso remoto alternativo por IP de tailnet).
- **Acceso publico:** `streamariel.mevel.com.mx` (tunel de Cloudflare).
- **Pais de WiFi:** FR (la Pi operara en Francia).

## Resumen de archivos de estado en la Pi (NO en git)

- `.env` — credenciales OAuth y overrides.
- `.youtube_tokens.json` — tokens de la cuenta vinculada.
- `.settings.json` — ajustes (ej. "transmitir sin microfono").
- `.visitors.csv` — registro de visitantes.
- `/etc/cloudflared/config.yml` y credenciales del tunel.
- `/etc/sudoers.d/rpi-youtube-stream` — permiso de `nmcli`.
- `~/.bash_profile` — sin `startx`, con `setterm --cursor off`.
