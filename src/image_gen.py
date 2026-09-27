"""Genera imágenes gratis con Cloudflare Workers AI (free tier).

Antes también se probaba Pollinations.ai como primer proveedor, pero se ha
quitado: metía una marca de agua/logo en las imágenes (el parámetro "nologo"
de su API no la elimina de forma fiable).

Ahora hay dos cuentas de Cloudflare configuradas como cadena de respaldo
(CF_ACCOUNT_ID/CF_API_TOKEN como principal, CF_ACCOUNT_ID_2/CF_API_TOKEN_2
como segunda cuenta por si la principal se queda sin cuota o cae): si la
principal falla por límite de cuota o Neurons agotados (402/429), se salta
directamente a la segunda sin gastar reintentos en la primera; para otros
errores puntuales (red, 5xx) se reintenta la misma cuenta antes de pasar a la
siguiente.

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


class _CuotaAgotada(Exception):
    pass


def _con_estilo(prompt: str) -> str:
    return f"{prompt}. {ESTILO_REALISTA}"


def _es_imagen_valida(datos: bytes) -> bool:
    """Descarta imágenes casi negras o vacías (fallo silencioso de moderación)."""
    return len(datos) > 5000  # comprobación mínima; se puede afinar con Pillow si hace falta


def _cuentas_cloudflare() -> list[tuple[str, str, str]]:
    """Devuelve las cuentas de Cloudflare configuradas como (nombre, account_id,
    token), en orden de prioridad. La segunda cuenta es opcional: si no están
    puestos sus secrets, simplemente no entra en la lista."""
    cuentas = []
    principal_id = os.environ.get("CF_ACCOUNT_ID")
    principal_token = os.environ.get("CF_API_TOKEN")
    if principal_id and principal_token:
        cuentas.append(("principal", principal_id, principal_token))

    secundaria_id = os.environ.get("CF_ACCOUNT_ID_2")
    secundaria_token = os.environ.get("CF_API_TOKEN_2")
    if secundaria_id and secundaria_token:
        cuentas.append(("secundaria", secundaria_id, secundaria_token))

    if not cuentas:
        raise RuntimeError(
            "Faltan los secrets de Cloudflare: hace falta al menos CF_ACCOUNT_ID/"
            "CF_API_TOKEN (Cloudflare es el único proveedor de imágenes)."
        )
    return cuentas


def _try_cloudflare(prompt: str, account_id: str, token: str) -> bytes:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/stabilityai/stable-diffusion-xl-base-1.0"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt},
        timeout=60,
    )
    if r.status_code in (402, 429):
        raise _CuotaAgotada(f"Cloudflare sin cuota/Neurons: {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    if not _es_imagen_valida(r.content):
        raise _CuotaAgotada("Cloudflare devolvió una imagen en blanco/vacía (posible filtro silencioso)")
    return r.content


def generar_imagen(prompt: str, destino: str, intentos_por_cuenta: int = 2) -> bool:
    prompt_final = _con_estilo(prompt)
    cuentas = _cuentas_cloudflare()

    for nombre, account_id, token in cuentas:
        for intento in range(1, intentos_por_cuenta + 1):
            try:
                imagen = _try_cloudflare(prompt_final, account_id, token)
                with open(destino, "wb") as f:
                    f.write(imagen)
                return True
            except _CuotaAgotada as e:
                print(f"[image_gen] cuenta Cloudflare '{nombre}' sin cuota, paso a la siguiente: {e}")
                break  # no malgastar reintentos en una cuenta sin cuota
            except requests.RequestException as e:
                print(f"[image_gen] cuenta Cloudflare '{nombre}' intento {intento}/{intentos_por_cuenta} falló: {e}")
                if intento < intentos_por_cuenta:
                    time.sleep(3 * intento)

    return False
