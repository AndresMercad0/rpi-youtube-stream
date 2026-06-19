#!/usr/bin/env python3
"""
Settings - rpi-youtube-stream
=============================
Ajustes editables desde la app (menu de opciones avanzadas), persistidos en un
archivo JSON local (.settings.json, no se versiona).

Solo se aceptan claves conocidas (ver DEFAULTS) para evitar inyectar datos
arbitrarios desde el frontend.
"""

import json
import os

import config


# Claves permitidas y sus valores por defecto.
DEFAULTS = {
    # Si es True, la transmision puede iniciar sin microfono (audio silencioso).
    "allow_no_mic": False,
}


def load():
    """Carga los ajustes, completando con los valores por defecto."""
    data = dict(DEFAULTS)
    if config.SETTINGS_FILE.exists():
        try:
            with open(config.SETTINGS_FILE) as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored:
                        data[key] = stored[key]
        except (OSError, json.JSONDecodeError):
            pass
    return data


def get(key, default=None):
    """Devuelve el valor de una clave conocida."""
    return load().get(key, DEFAULTS.get(key, default))


def update(patch):
    """Actualiza solo las claves conocidas y persiste. Devuelve el estado final."""
    data = load()
    if isinstance(patch, dict):
        for key, value in patch.items():
            if key in DEFAULTS:
                data[key] = value

    fd = os.open(config.SETTINGS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)

    return data
