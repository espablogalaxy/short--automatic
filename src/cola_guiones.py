"""Cola de guiones pendientes/hechos/descartados con selección inteligente.

content/pending/    guiones por publicar
content/done/       publicados (histórico, nunca se repiten)
content/discarded/  duplicados movidos (no se borran; cuentan para el antiduplicado)

Selección (portada del canal de la Pi): entre los 12 primeros pendientes se sube
el MÁS CORTO en palabras (los shorts de ~20-25 s rinden mucho más que los de 40+ s)
evitando repetir el mismo "formato" de título que alguno de los 2 últimos subidos.
"""
import json
import re
import time
import unicodedata
from pathlib import Path

DIR_PENDING = Path("content/pending")
DIR_DONE = Path("content/done")
DIR_DISCARDED = Path("content/discarded")


def _slug(texto: str, max_len: int = 40) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return slug[:max_len] or "guion"


def _leer(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return None


def _palabras(ruta: Path) -> int:
    g = _leer(ruta)
    if not g:
        return 999
    return sum(len(e.get("texto", "").split()) for e in g.get("escenas", []))


def _huella(ruta: Path) -> str:
    g = _leer(ruta)
    if not g:
        return ""
    t = unicodedata.normalize("NFD", g.get("titulo", "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w ]", " ", t).strip()
    for clave in ("por que", "que ", "cuanto", "cual ", "como "):
        if t.startswith(clave):
            return clave.strip()
    return t.split(" ")[0] if t else ""


def contar_pendientes() -> int:
    return len(list(DIR_PENDING.glob("*.json"))) if DIR_PENDING.exists() else 0


def guardar_pendiente(guion: dict) -> Path:
    DIR_PENDING.mkdir(parents=True, exist_ok=True)
    ruta = DIR_PENDING / f"{int(time.time())}_{_slug(guion['titulo'])}.json"
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def sacar_pendiente():
    """Siguiente guion a publicar (None si la cola está vacía)."""
    if not DIR_PENDING.exists():
        return None
    pendientes = sorted(DIR_PENDING.glob("*.json"))
    if not pendientes:
        return None
    recientes = sorted(DIR_DONE.glob("*.json"))[-2:] if DIR_DONE.exists() else []
    huellas = {_huella(p) for p in recientes}
    elegibles = [p for p in pendientes if _huella(p) not in huellas] or pendientes
    ruta = min(elegibles[:12], key=_palabras)
    return ruta, json.loads(ruta.read_text(encoding="utf-8"))


def marcar_hecho(ruta_guion: Path, guion: dict, url: str | None = None) -> None:
    DIR_DONE.mkdir(parents=True, exist_ok=True)
    if url:
        guion["youtube_url"] = url
    destino = DIR_DONE / ruta_guion.name
    destino.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    if ruta_guion.exists() and ruta_guion.parent == DIR_PENDING:
        ruta_guion.unlink()


def descartar(ruta_guion: Path) -> None:
    DIR_DISCARDED.mkdir(parents=True, exist_ok=True)
    ruta_guion.rename(DIR_DISCARDED / ruta_guion.name)
