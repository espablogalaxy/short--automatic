"""Cola de guiones pendientes/hechos, igual que en la automatización de la
Raspberry Pi: un guion se puede generar al vuelo (si la cola está vacía) o
coger de una reserva ya generada de antemano con `generar_lote.py`.

Cada guion se guarda como un .json en content/pending/, con nombre
`{timestamp}_{slug-del-titulo}.json` (el timestamp ordena por antigüedad sin
tener que leer metadata). Al publicarse, el archivo se mueve tal cual a
content/done/, así queda un histórico de lo ya publicado y nunca se repite.
"""
import json
import re
import time
from pathlib import Path

DIR_PENDING = Path("content/pending")
DIR_DONE = Path("content/done")


def _slug(texto: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return slug[:max_len] or "guion"


def guardar_pendiente(guion: dict) -> Path:
    """Guarda un guion recién generado en la cola de pendientes."""
    DIR_PENDING.mkdir(parents=True, exist_ok=True)
    nombre = f"{int(time.time())}_{_slug(guion['titulo'])}.json"
    ruta = DIR_PENDING / nombre
    ruta.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def sacar_pendiente() -> tuple[Path, dict] | None:
    """Coge el guion pendiente más antiguo de la cola (None si está vacía)."""
    if not DIR_PENDING.exists():
        return None
    candidatos = sorted(DIR_PENDING.glob("*.json"))
    if not candidatos:
        return None
    ruta = candidatos[0]
    guion = json.loads(ruta.read_text(encoding="utf-8"))
    return ruta, guion


def marcar_hecho(ruta_guion: Path, guion: dict) -> None:
    """Archiva el guion ya publicado en content/done/. Si venía de la cola de
    pendientes lo mueve tal cual (git ve un rename, no un delete+create); si
    se generó al vuelo (cola vacía) lo escribe directamente en done/."""
    DIR_DONE.mkdir(parents=True, exist_ok=True)
    destino = DIR_DONE / ruta_guion.name
    if ruta_guion.exists() and ruta_guion.parent == DIR_PENDING:
        ruta_guion.rename(destino)
    else:
        destino.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
