# Acceso remoto con Cloudflare Tunnel

Guia para exponer el panel de la app (que corre en `localhost:8082`) en un
subdominio publico, vía un Cloudflare Tunnel. Sirve para abrir el panel desde
cualquier lugar (telefono, etc.) sin abrir puertos en el router.

Requisitos:
- Estar en la Pi por SSH.
- Una cuenta de Cloudflare con tu dominio (ej. `mevel.com.mx`) ya agregado.

> El tunel es solo para acceder al panel. La vinculacion de YouTube (Device Flow)
> no depende del dominio, asi que esto no la afecta.

---

## 0. Elige nombre del tunel y subdominio

Define estos dos valores una vez (cambialos a tu gusto). El resto de comandos los
reutilizan. **Manten la misma sesion SSH abierta** para que las variables sigan
disponibles en los pasos siguientes.

```bash
TUNNEL_NAME=streamariel
HOSTNAME=streamariel.mevel.com.mx
```

## 1. Instalar cloudflared

```bash
ARCH=$(dpkg --print-architecture)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

## 2. Iniciar sesion en Cloudflare (interactivo)

```bash
cloudflared tunnel login
```

Imprime una URL: abrela en un navegador, inicia sesion y **selecciona la zona de
tu dominio** (ej. `mevel.com.mx`). Guarda un certificado en `~/.cloudflared/cert.pem`.

## 3. Crear el tunel

```bash
cloudflared tunnel create "$TUNNEL_NAME"
```

Muestra un **Tunnel ID** (UUID) y crea el archivo de credenciales en
`~/.cloudflared/<ID>.json`.

## 4. Crear el registro DNS

```bash
cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME"
```

Crea automaticamente el CNAME en Cloudflare apuntando el subdominio al tunel.

## 5. Crear el archivo de configuracion

```bash
sudo mkdir -p /etc/cloudflared
TUNNEL_ID=$(cloudflared tunnel list | awk -v n="$TUNNEL_NAME" '$2==n{print $1}')
echo "Tunnel ID: $TUNNEL_ID"
sudo cp ~/.cloudflared/${TUNNEL_ID}.json /etc/cloudflared/
sudo tee /etc/cloudflared/config.yml >/dev/null <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: /etc/cloudflared/${TUNNEL_ID}.json

ingress:
  - hostname: ${HOSTNAME}
    service: http://localhost:8082
  - service: http_status:404
EOF
cat /etc/cloudflared/config.yml
```

## 6. Instalar y arrancar el servicio

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared --no-pager
```

## 7. Probar

```bash
echo "Abre en el navegador: https://$HOSTNAME"
# Desde la Pi tambien puedes probar (tras unos segundos de propagacion):
curl -sI "https://$HOSTNAME" | head -5
```

---

## Comandos utiles

```bash
# Ver logs del tunel en vivo
sudo journalctl -u cloudflared -f

# Reiniciar / estado del tunel
sudo systemctl restart cloudflared
sudo systemctl status cloudflared --no-pager

# Listar tuneles de tu cuenta
cloudflared tunnel list
```

## Problemas comunes

- **El subdominio no abre (error 1033 o de DNS):** espera 1 a 2 minutos a que
  propague el DNS y verifica que `cloudflared` este `active (running)` (paso 6).
- **Error 502 / 1016:** la app no esta escuchando en `localhost:8082`. Revisa
  `sudo systemctl status rpi-youtube-stream`.
- **`TUNNEL_ID` sale vacio en el paso 5:** confirma con `cloudflared tunnel list`
  que el nombre coincide con `$TUNNEL_NAME`.
