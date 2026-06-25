#!/usr/bin/env python3
"""
Network - rpi-youtube-stream
============================
Estado de conexion a internet (cable vs WiFi) y gestion de WiFi via
NetworkManager (nmcli), que es el stack de red de Raspberry Pi OS Bookworm+.

  - status(): detecta si la salida a internet va por ethernet, wifi o nada.
  - scan(): lista redes WiFi disponibles.
  - connect(ssid, password): conecta a una red WiFi.

Las operaciones que modifican la red (escaneo activo y conexion) se ejecutan con
'sudo -n nmcli'. Para que funcionen desde el servicio, install.sh agrega una
regla en /etc/sudoers.d que permite ejecutar nmcli sin contrasena.
"""

import re
import shutil
import subprocess


# ==============================================================================
# SECCION 0: HELPERS
# ==============================================================================


def _run(cmd, timeout=15):
    """Ejecuta un comando. Devuelve (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "comando no encontrado"
    except subprocess.TimeoutExpired:
        return 124, "", "tiempo de espera agotado"


def _has_nmcli():
    """Indica si nmcli esta disponible en el sistema."""
    return shutil.which("nmcli") is not None


def _split_terse(line):
    """Separa una linea de 'nmcli -t' respetando los escapes de ':' y '\\'."""
    fields = []
    current = ""
    i = 0
    while i < len(line):
        char = line[i]
        if char == "\\" and i + 1 < len(line):
            current += line[i + 1]
            i += 2
            continue
        if char == ":":
            fields.append(current)
            current = ""
            i += 1
            continue
        current += char
        i += 1
    fields.append(current)
    return fields


# ==============================================================================
# SECCION 1: ESTADO DE CONEXION
# ==============================================================================


def _default_route_iface():
    """Interfaz por la que sale el trafico a internet, o None."""
    code, out, _ = _run(["ip", "-4", "route", "get", "1.1.1.1"], timeout=3)
    if code != 0:
        return None
    match = re.search(r"\bdev\s+(\S+)", out)
    return match.group(1) if match else None


def _current_ssid():
    """SSID de la red WiFi activa, o None (lectura, sin sudo)."""
    if not _has_nmcli():
        return None
    code, out, _ = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=5)
    if code != 0:
        return None
    for line in out.splitlines():
        fields = _split_terse(line)
        if len(fields) >= 2 and fields[0] == "yes":
            return fields[1] or None
    return None


def status():
    """
    Estado de conexion a internet.

    Returns dict:
      type:           "ethernet"|"wifi"|"none"  (por donde sale el trafico a internet)
      iface, ssid:    de la ruta por defecto
      wifi_connected: bool  (True si el WiFi esta asociado, aunque NO sea la ruta
                            por defecto, p.ej. conectado por cable y WiFi a la vez)
      wifi_ssid:      str|None  (SSID del WiFi conectado)
    """
    iface = _default_route_iface()
    wifi_ssid = _current_ssid()  # SSID conectado aunque no sea la ruta por defecto
    wifi_connected = wifi_ssid is not None

    if not iface or iface.startswith("lo"):
        ptype = "none"
    elif iface.startswith(("wlan", "wlp", "wlx")):
        ptype = "wifi"
    else:
        # eth0, end0, enxXXXX, usb0, etc.
        ptype = "ethernet"

    return {
        "type": ptype,
        "iface": iface,
        "ssid": wifi_ssid if ptype == "wifi" else None,
        "wifi_connected": wifi_connected,
        "wifi_ssid": wifi_ssid,
    }


# ==============================================================================
# SECCION 2: WIFI (ESCANEO Y CONEXION)
# ==============================================================================


def scan():
    """
    Lista redes WiFi disponibles (la mas fuerte por SSID).

    Returns dict: {"networks": [{"ssid","signal","secure"}...], "error": str|None}
    """
    if not _has_nmcli():
        return {"networks": [], "error": "NetworkManager (nmcli) no esta disponible en este sistema."}

    code, out, err = _run(
        ["sudo", "-n", "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"],
        timeout=25,
    )
    if code != 0:
        detail = (err or out).strip()
        if "password is required" in detail.lower() or "sudo" in detail.lower():
            detail = "Falta el permiso sudo para nmcli. Vuelve a correr ./install.sh."
        return {"networks": [], "error": detail or "No se pudo escanear redes WiFi."}

    best = {}
    for line in out.splitlines():
        fields = _split_terse(line)
        if len(fields) < 3:
            continue
        ssid, signal_raw, security = fields[0], fields[1], fields[2]
        if not ssid:
            continue  # red oculta
        try:
            signal = int(signal_raw)
        except ValueError:
            signal = 0
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = {
                "ssid": ssid,
                "signal": signal,
                "secure": bool(security and security not in ("", "--")),
            }

    networks = sorted(best.values(), key=lambda n: n["signal"], reverse=True)
    return {"networks": networks, "error": None}


def connect(ssid, password=""):
    """
    Conecta a una red WiFi. Devuelve (ok: bool, mensaje: str).
    """
    if not _has_nmcli():
        return False, "NetworkManager (nmcli) no esta disponible en este sistema."
    if not ssid:
        return False, "Falta el nombre de la red (SSID)."

    cmd = ["sudo", "-n", "nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]

    code, out, err = _run(cmd, timeout=45)
    if code == 0:
        return True, f"Conectado a {ssid}."

    detail = (err or out).strip().lower()
    if "secrets were required" in detail or "password" in detail or "802-11" in detail:
        return False, "Contrasena incorrecta o requerida."
    if "no network with ssid" in detail:
        return False, f"No se encontro la red {ssid}."
    if "a terminal is required" in detail or "sudo" in detail:
        return False, "Falta el permiso sudo para nmcli. Vuelve a correr ./install.sh."
    return False, (err or out).strip() or "No se pudo conectar a la red."
