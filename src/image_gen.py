"""Genera imágenes gratis. Primero intenta Pollinations.ai (sin API key), y si
falla, usa Cloudflare Workers AI (free tier) como respaldo si hay credenciales."""
import os
import time
import urllib.parse

import requests


def _es_imagen_valida(datos: bytes) -> bool:
    """Descarta imágenes casi negras o vacías (fallo silencioso de moderación)."""
    return len(datos) > 5000  # comprobación mínima; se puede afinar con Pillow si hace falta


def generar_con_pollinations(prompt: str, destino: str) -> bool:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
    try:
        r = requests.get(url, timeout=60, params={"width": 1024, "height": 1820, "nologo": "true"})
        r.raise_for_status()
        if _es_imagen_valida(r.content):
            with open(destino, "wb") as f:
                f.write(r.content)
            return True
    except requests.RequestException as e:
        print(f"Pollinations falló: {e}")
    return False


def generar_con_cloudflare(prompt: str, destino: str) -> bool:
    account_id = os.environ.get("CF_ACCOUNT_ID")
    token = os.environ.get("CF_API_TOKEN")
    if not account_id or not token:
        return False

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/stabilityai/stable-diffusion-xl-base-1.0"
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": prompt},
            timeout=60,
        )
        r.raise_for_status()
        if _es_imagen_valida(r.content):
            with open(destino, "wb") as f:
                f.write(r.content)
            return True
    except requests.RequestException as e:
        print(f"Cloudflare Workers AI falló: {e}")
    return False


def generar_imagen(prompt: str, destino: str, intentos: int = 2) -> bool:
    for _ in range(intentos):
        if generar_con_pollinations(prompt, destino):
            return True
        if generar_con_cloudflare(prompt, destino):
            return True
        time.sleep(3)
    return False
