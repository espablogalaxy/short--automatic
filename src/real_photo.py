"""Busca una foto REAL (no generada por IA) de un lugar identificable en Wikimedia
Commons, para la escena principal de cada short.

Porta la idea del canal de la Raspberry Pi (src/real_photo.py, usada allí para
dispositivos históricos concretos) a este canal, donde el tema central de cada short
SIEMPRE es un lugar real con nombre propio (un lago, una cueva, un volcán, un cráter,
un desierto...): cuando hay una foto real disponible, da más autenticidad y credibilidad
que una imagen generada por IA, en un canal que precisamente presume de datos verificables.

Usa el endpoint de búsqueda de Commons (sin API key, sin autenticación) y pide el
thumbnail (iiurlwidth), nunca la imagen original: Commons devuelve 429 en descargas
repetidas del tamaño original hechas por bots. Si no encuentra nada adecuado, el
llamador (main.py) cae a la generación por IA de image_gen.py, como hacía siempre.

2026-10-31: se actualiza con las dos mejoras que el equivalente de la Raspberry Pi
ya tenía y aquí faltaban: (1) reintentos con backoff ante 429 en las TRES llamadas a
Commons (búsqueda, metadatos y descarga) -- antes solo se reintentaba la descarga, así
que un 429 en la búsqueda hacía caer el short entero a IA aunque Commons sí tuviera una
foto válida; (2) coincidencia de título estricta (el fichero de Commons debe contener
la mayoría de las palabras significativas del nombre buscado) para no usar como "el
lugar" la foto de otra cosa.
"""
import time

import requests

API = "https://commons.wikimedia.org/w/api.php"
ANCHO_THUMB = 1200
CABECERAS = {"User-Agent": "short-automatic-bot/1.0 (uso educativo, canal de YouTube Shorts)"}

_GENERICAS = {"lake", "mount", "mountain", "valley", "desert", "cave", "island", "glacier",
              "crater", "the", "and", "with", "for", "national", "park", "falls", "river"}


def _titulo_coincide(titulo: str, nombre_lugar: str, minimo: float = 0.5) -> bool:
    """El título del fichero de Commons debe contener al menos la mitad de las palabras
    significativas del nombre buscado, para no quedarse con la foto de otro lugar
    distinto con un nombre parecido."""
    toks = [t for t in nombre_lugar.lower().replace("-", " ").split()
            if len(t) >= 3 and t not in _GENERICAS]
    if not toks:
        return True
    t = titulo.lower()
    return sum(1 for x in toks if x in t) / len(toks) >= minimo


def _get_con_reintentos(url, params=None, timeout=15, intentos=3):
    """GET con reintentos y backoff ante 429 (Commons limita por ráfagas desde una
    misma IP); se usa para las 3 llamadas a Commons (búsqueda, metadatos y descarga)."""
    resp = None
    for intento in range(intentos):
        resp = requests.get(url, params=params, headers=CABECERAS, timeout=timeout)
        if resp.status_code != 429:
            return resp
        time.sleep(2 * (intento + 1))
    return resp


def _buscar_candidatos(nombre_lugar: str, limite: int = 8) -> list[str]:
    r = _get_con_reintentos(
        API,
        params={
            "action": "query", "list": "search", "srnamespace": 6,
            "srsearch": f"{nombre_lugar} filetype:bitmap", "srlimit": limite,
            "format": "json",
        },
        timeout=15,
    )
    r.raise_for_status()
    resultados = r.json().get("query", {}).get("search", [])
    return [res["title"] for res in resultados if res.get("title", "").lower().endswith((".jpg", ".jpeg", ".png"))]


def _thumb_url(titulo_fichero: str) -> str | None:
    r = _get_con_reintentos(
        API,
        params={
            "action": "query", "titles": titulo_fichero, "prop": "imageinfo",
            "iiprop": "url|size", "iiurlwidth": ANCHO_THUMB, "format": "json",
        },
        timeout=15,
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


def buscar_foto_real(nombre_lugar: str, destino: str, usadas: set | None = None) -> bool:
    """Intenta descargar una foto real de `nombre_lugar` (nombre propio, en inglés o
    español, tal y como aparecería en Wikipedia/Commons). True si lo consigue y la
    guarda en `destino`; False si no encuentra nada adecuado (el llamador debe caer
    a la generación por IA). No requiere PIL: el pipeline reencuadra cualquier
    imagen a vertical con el mismo zoompan de FFmpeg que usa para las generadas.
    `usadas`, si se pasa, es un set de títulos de Commons ya usados en este mismo
    vídeo: nunca se repite la misma foto en dos escenas."""
    if not nombre_lugar or not nombre_lugar.strip():
        return False
    if usadas is None:
        usadas = set()
    try:
        candidatos = _buscar_candidatos(nombre_lugar)
    except Exception as e:
        print(f"[real_photo] fallo buscando '{nombre_lugar}' en Wikimedia Commons, se usará IA: {e}")
        return False
    for titulo in candidatos:
        if titulo in usadas:
            continue
        if not _titulo_coincide(titulo, nombre_lugar):
            continue
        try:
            url = _thumb_url(titulo)
            if not url:
                continue
            r = _get_con_reintentos(url, timeout=30, intentos=3)
            r.raise_for_status()
            if len(r.content) < 15000:  # demasiado pequeña para ser una foto real útil
                continue
            with open(destino, "wb") as f:
                f.write(r.content)
            usadas.add(titulo)
            return True
        except Exception as e:
            print(f"[real_photo] fallo con {titulo!r}, se prueba siguiente candidato: {e}")
            continue
    return False
