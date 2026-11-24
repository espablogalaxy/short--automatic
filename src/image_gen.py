"""Genera imágenes gratis con Cloudflare Workers AI (free tier).

Antes también se probaba Pollinations.ai como primer proveedor, pero se ha
quitado: metía una marca de agua/logo en las imágenes (el parámetro "nologo"
de su API no la elimina de forma fiable).

Hay dos cuentas de Cloudflare configuradas como cadena de respaldo
(CF_ACCOUNT_ID/CF_API_TOKEN como principal, CF_ACCOUNT_ID_2/CF_API_TOKEN_2
como segunda cuenta por si la principal se queda sin cuota o cae): si la
principal falla por límite de cuota o Neurons agotados (402/429), se salta
directamente a la segunda sin gastar reintentos en la primera; para otros
errores puntuales (red, 5xx) se reintenta la misma cuenta antes de pasar a la
siguiente.

2026-11-24: los dos modelos SDXL (lightning y base) que se usaban antes
fueron retirados por Cloudflare (stable-diffusion-xl-base-1.0 tenía fecha de
retirada planificada el 20/11/2026) y devuelven 410 Gone en todas las
cuentas. Se sustituyen por flux-1-schnell, que sigue activo en el catálogo
de Workers AI. A diferencia de los modelos SDXL (que devuelven el PNG en
crudo en el cuerpo de la respuesta), flux-1-schnell devuelve JSON con la
imagen codificada en base64 bajo result.image, así que _try_cloudflare ahora
detecta el content-type de la respuesta y decodifica cuando hace falta.

Todas las imágenes llevan añadido el mismo sufijo de estilo fotorrealista que
usa la automatización de la Raspberry Pi (canal Soporte IT), para que las
imágenes de este canal tengan el mismo aspecto realista en vez de parecer una
ilustración digital."""
import base64
import os
import re
import time
from io import BytesIO

import requests

try:
    from PIL import Image
except ImportError:  # sin Pillow solo se comprueba el tamaño
    Image = None

ESTILO_REALISTA = (
    "fotografia hiperrealista, estilo reportaje cinematografico, iluminacion "
    "natural dramatica, texturas realistas, sin aspecto de ilustracion ni de "
    "render 3D, sin texto en la imagen, composicion vertical, sujeto centrado "
    "en el encuadre, formato retrato"
)

# (nombre, endpoint del modelo, timeout en segundos). Se prueban en orden por
# cada cuenta. Antes había un modelo "lightning" rápido con fallback a un
# SDXL "base" más lento; ambos fueron retirados por Cloudflare (410 Gone,
# ver nota arriba), así que de momento solo queda flux-1-schnell.
MODELOS = (
    ("flux-schnell", "@cf/black-forest-labs/flux-1-schnell", 30),
)


class _CuotaAgotada(Exception):
    pass


def _con_estilo(prompt: str) -> str:
    return f"{prompt}. {ESTILO_REALISTA}"


def _es_imagen_valida(datos: bytes, umbral_varianza: int = 8) -> bool:
    """Descarta imágenes vacías o SÓLIDAS (normalmente negras) devueltas con HTTP 200 por
    el filtro silencioso de moderación de Cloudflare (portado de la Pi): comprueba el
    rango de cada canal RGB; una foto real nunca tiene un rango tan estrecho."""
    if len(datos) <= 5000:
        return False
    if Image is None:
        return True
    try:
        with Image.open(BytesIO(datos)) as im:
            extrema = im.convert("RGB").getextrema()
    except Exception:
        return False
    return not all((mx - mn) <= umbral_varianza for mn, mx in extrema)


# Palabras que disparan filtros de moderación (p. ej. "glaciar de sangre"). Solo se usan
# en un segundo intento tras un rechazo, nunca en el primero.
_PALABRAS_DRAMATICAS = {
    "sangre": "óxido rojo", "sangriento": "intenso", "infierno": "fuego", "muerte": "final",
    "muerto": "vacío", "matar": "vencer", "guerra": "conflicto", "arma": "objeto",
}


def _suavizar_prompt(prompt: str) -> str:
    for palabra, sustituto in _PALABRAS_DRAMATICAS.items():
        prompt = re.sub(palabra, sustituto, prompt, flags=re.IGNORECASE)
    return prompt


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


def _extraer_imagen(r: requests.Response) -> bytes:
    """Algunos modelos (SDXL) devuelven el PNG en crudo en el cuerpo; otros
    (flux-1-schnell) devuelven JSON con la imagen en base64 bajo result.image."""
    content_type = r.headers.get("content-type", "")
    if content_type.startswith("image/"):
        return r.content
    datos = r.json()
    imagen_b64 = (datos.get("result") or {}).get("image")
    if not imagen_b64:
        raise _CuotaAgotada(f"Respuesta de Cloudflare sin campo result.image: {r.text[:200]}")
    return base64.b64decode(imagen_b64)


def _try_cloudflare(prompt: str, account_id: str, token: str, modelo: str, timeout: int) -> bytes:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{modelo}"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt},
        timeout=timeout,
    )
    if r.status_code in (402, 429):
        raise _CuotaAgotada(f"Cloudflare sin cuota/Neurons: {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    imagen = _extraer_imagen(r)
    if not _es_imagen_valida(imagen):
        raise _CuotaAgotada("Cloudflare devolvió una imagen en blanco/vacía (posible filtro silencioso)")
    return imagen


def generar_imagen(prompt: str, destino: str, intentos_por_modelo: int = 1) -> bool:
    cuentas = _cuentas_cloudflare()
    for suavizado in (False, True):  # 2º pase: prompt suavizado si todo falló (moderación)
        base = _suavizar_prompt(prompt) if suavizado else prompt
        prompt_final = _con_estilo(base)
        for nombre_cuenta, account_id, token in cuentas:
            cuota_agotada_en_cuenta = False
            for nombre_modelo, modelo, timeout in MODELOS:
                if cuota_agotada_en_cuenta:
                    break
                for intento in range(1, intentos_por_modelo + 1):
                    try:
                        imagen = _try_cloudflare(prompt_final, account_id, token, modelo, timeout)
                        with open(destino, "wb") as f:
                            f.write(imagen)
                        return True
                    except _CuotaAgotada as e:
                        print(f"[image_gen] cuenta '{nombre_cuenta}' sin cuota o imagen bloqueada, paso a la siguiente cuenta: {e}")
                        cuota_agotada_en_cuenta = True
                        break
                    except requests.RequestException as e:
                        print(f"[image_gen] cuenta '{nombre_cuenta}' modelo '{nombre_modelo}' intento {intento}/{intentos_por_modelo} falló: {e}")
                        if intento < intentos_por_modelo:
                            time.sleep(2 * intento)
        if not suavizado:
            print("[image_gen] todas las cuentas y modelos fallaron, reintento con prompt suavizado")
    return False
