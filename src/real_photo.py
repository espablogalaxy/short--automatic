"""Busca una foto REAL (no generada por IA) de un lugar identificable en Wikimedia
Commons, para la escena principal de cada short.

Porta la idea del canal de la Raspberry Pi (src/real_photo.py, usada allí para
dispositivos históricos concretos) a este canal, donde el tema central de cada short
SIEMPRE es un lugar real con nombre propio (un lago, una cueva, un volcán, un cráter,
un desierto...): cuando hay una foto real disponible, da más autenticidad y credibilidad
que una imagen generada por IA, en un canal que precisamente presume de datos verificables.

Usa el endpoint de búsqueda de Commons (sin API key, sin autenticación) y pide el
thumbnail (iiurlwidth), nunca la imagen original: Commons devuelve 429 en descargas
repetidas del tamaño original hechas por bots (mismo problema que ya documentó el
canal de la Pi). Si no encuentra nada adecuado, el llamador (main.py) cae a la
generación por IA de image_gen.py, como hacía siempre.
"""
import requests

API = "https://commons.wikimedia.org/w/api.php"
ANCHO_THUMB = 1200
CABECERAS = {"User-Agent": "short-automatic-bot/1.0 (uso educativo, canal de YouTube Shorts)"}


def _buscar_titulo(nombre_lugar: str) -> str | None:
    r = requests.get(
        API,
        params={
            "action": "query", "list": "search", "srnamespace": 6,
            "srsearch": f"{nombre_lugar} filetype:bitmap", "srlimit": 5,
            "format": "json",
        },
        headers=CABECERAS, timeout=20,
    )
    r.raise_for_status()
    resultados = r.json().get("query", {}).get("search", [])
    for res in resultados:
        titulo = res.get("title", "")
        if titulo.lower().endswith((".jpg", ".jpeg", ".png")):
            return titulo
    return None


def _thumb_url(titulo_fichero: str) -> str | None:
    r = requests.get(
        API,
        params={
            "action": "query", "titles": titulo_fichero, "prop": "imageinfo",
            "iiprop": "url|size", "iiurlwidth": ANCHO_THUMB, "format": "json",
        },
        headers=CABECERAS, timeout=20,
    )
    r.raise_for_status()
    paginas = r.json().get("query", {}).get("pages", {})
    for pagina in paginas.values():
        info = (pagina.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        ancho = info.get("thumbwidth") or info.get("width") or 0
        alto = info.get("thumbheight") or info.get("height") or 0
        # Descartamos miniaturas/iconos pequeños (mapas, escudos, diagramas suelen ser chicos).
        if url and ancho >= 500 and alto >= 400:
            return url
    return None


def buscar_foto_real(nombre_lugar: str, destino: str) -> bool:
    """Intenta descargar una foto real de `nombre_lugar` (nombre propio, en inglés o
    español, tal y como aparecería en Wikipedia/Commons). True si lo consigue y la
    guarda en `destino`; False si no encuentra nada adecuado (el llamador debe caer
    a la generación por IA). No requiere PIL: el pipeline reencuadra cualquier
    imagen a vertical con el mismo zoompan de FFmpeg que usa para las generadas."""
    if not nombre_lugar or not nombre_lugar.strip():
        return False
    try:
        titulo = _buscar_titulo(nombre_lugar)
        if not titulo:
            return False
        url = _thumb_url(titulo)
        if not url:
            return False
        r = requests.get(url, headers=CABECERAS, timeout=30)
        r.raise_for_status()
        if len(r.content) < 15000:  # demasiado pequeña para ser una foto real útil
            return False
        with open(destino, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"[real_photo] no se pudo conseguir foto real de '{nombre_lugar}': {e}")
        return False
