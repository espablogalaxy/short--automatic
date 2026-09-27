"""Genera imágenes gratis con Cloudflare Workers AI (free tier).

Antes también se probaba Pollinations.ai como primer proveedor, pero se ha
quitado: metía una marca de agua/logo en las imágenes (el parámetro "nologo"
de su API no la elimina de forma fiable), así que ahora Cloudflare es el
único proveedor. Como ya no hay un segundo proveedor de respaldo, aquí se
reintenta más veces sobre el propio Cloudflare antes de rendirse.

Todas las imágenes llevan añadido el mismo sufijo de estilo fotorrealista que
usa la automatización de la Raspberry Pi (canal Soporte IT), para que las
imágenes de este canal tengan el mismo aspecto realista en vez de parecer una
ilustración digital."""
import os
import time

import requests

ESTILO_REALISTA = (
    "fotografia hiperrealista, estilo reportaje cinematografico, iluminacion "
    "natural dramatica, texturas realistas, sin aspecto de ilustracion ni de "
    "render 3D, sin texto en la imagen, composicion vertical, sujeto centrado "
    "en el encuadre, formato retrato"
)


def _con_estilo(prompt: str) -> str:
    return f"{prompt}. {ESTILO_REALISTA}"


def _es_imagen_valida(datos: bytes) -> bool:
    """Descarta imágenes casi negras o vacías (fallo silencioso de moderación)."""
    return len(datos) > 5000  # comprobación mínima; se puede afinar con Pillow si hace falta


def generar_con_cloudflare(prompt: str, destino: str) -> bool:
    account_id = os.environ.get("CF_ACCOUNT_ID")
    token = os.environ.get("CF_API_TOKEN")
    if not account_id or not token:
        raise RuntimeError(
            "Faltan los secrets CF_ACCOUNT_ID/CF_API_TOKEN: son obligatorios ahora que "
            "Cloudflare es el único proveedor de imágenes."
        )

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


def generar_imagen(prompt: str, destino: str, intentos: int = 4) -> bool:
    prompt_final = _con_estilo(prompt)
    for intento in range(1, intentos + 1):
        if generar_con_cloudflare(prompt_final, destino):
            return True
        if intento < intentos:
            time.sleep(3 * intento)
    return False
