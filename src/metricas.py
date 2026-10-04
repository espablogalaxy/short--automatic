"""Bucle de feedback con datos REALES del canal (portado de la Raspberry Pi).

Lee las vistas de los últimos vídeos desde el feed RSS público del canal (sin
autenticación, funciona desde GitHub Actions; devuelve los 15 más recientes, así
que se ejecuta a diario y acumula el histórico en content/metricas.json).
guion_gen.py inyecta en cada prompt los títulos que MEJOR y PEOR rinden.
"""
import json
import os
import re
import statistics
import html
from datetime import datetime, timezone

import requests

RUTA = os.path.join("content", "metricas.json")
CHANNEL_ID = os.environ.get("YT_CHANNEL_ID", "UCep5zLNn_tccIjquFD4aeCQ")
UMBRAL_EXITO = 500


def cargar():
    try:
        with open(RUTA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"actualizado": None, "videos": {}}


def _feed():
    r = requests.get(
        "https://www.youtube.com/feeds/videos.xml", params={"channel_id": CHANNEL_ID}, timeout=30
    )
    r.raise_for_status()
    out = {}
    for e in re.findall(r"<entry>.*?</entry>", r.text, re.S):
        vid = re.search(r"<yt:videoId>(.*?)</yt:videoId>", e).group(1)
        titulo = html.unescape(re.search(r"<title>(.*?)</title>", e).group(1))
        pub = re.search(r"<published>(.*?)</published>", e).group(1)
        vistas = re.search(r'<media:statistics views="(\d+)"', e)
        out[vid] = {"titulo": titulo, "subida": pub, "vistas": int(vistas.group(1)) if vistas else 0}
    return out


def actualizar():
    datos = cargar()
    vids = datos.get("videos", {})
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for vid, info in _feed().items():
        hist = vids.get(vid, {}).get("historial", [])
        hist = [h for h in hist if h[0] != hoy] + [[hoy, info["vistas"]]]
        info["historial"] = hist[-30:]
        vids[vid] = info
    datos["videos"] = vids
    datos["actualizado"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(RUTA), exist_ok=True)
    with open(RUTA, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    return datos


def _edad_dias(info):
    try:
        d = datetime.fromisoformat(info["subida"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - d).total_seconds() / 86400
    except Exception:
        return 99


def bloque_prompt(n_ganadores=6, n_perdedores=5, minimo=10):
    """Texto para el prompt de generación; cadena vacía si aún no hay datos suficientes."""
    vids = list(cargar().get("videos", {}).values())
    maduros = [v for v in vids if _edad_dias(v) >= 2]
    if len(maduros) < minimo:
        return ""
    maduros.sort(key=lambda v: v["vistas"], reverse=True)
    ganadores = maduros[:n_ganadores]
    perdedores = sorted([v for v in maduros if _edad_dias(v) >= 4], key=lambda v: v["vistas"])[:n_perdedores]
    aciertos = sum(1 for v in maduros if v["vistas"] >= UMBRAL_EXITO)
    lin = [
        "",
        f"DATOS REALES DE ESTE CANAL ({len(maduros)} shorts, {aciertos} superan las {UMBRAL_EXITO} vistas; el objetivo es subir ese porcentaje).",
        "Títulos que MEJOR han funcionado (imita el TIPO de ángulo, de lugar y de formulación, pero NUNCA repitas su tema):",
    ]
    lin += [f'- "{v["titulo"]}" ({v["vistas"]} vistas)' for v in ganadores]
    lin.append("Los que PEOR han funcionado pese a llevar días publicados (evita ese tipo de tema y de formulación):")
    lin += [f'- "{v["titulo"]}" ({v["vistas"]} vistas)' for v in perdedores]
    lin.append("Elige un tema NUEVO 'hermano' de los ganadores y NO de los perdedores.")
    return "\n".join(lin)


def informe():
    maduros = [v for v in cargar().get("videos", {}).values() if _edad_dias(v) >= 2]
    if not maduros:
        print("Sin datos todavía")
        return
    vs = [v["vistas"] for v in maduros]
    print(f"{len(maduros)} shorts | mediana {statistics.median(vs):.0f} | media {statistics.mean(vs):.0f} | aciertos>={UMBRAL_EXITO}: {sum(x >= UMBRAL_EXITO for x in vs)}")
    por_hora = {}
    for v in maduros:
        h = v["subida"][11:13]  # hora UTC
        por_hora.setdefault(h, []).append(v["vistas"])
    for h, l in sorted(por_hora.items()):
        print(f"  hora {h} UTC: n={len(l)} mediana={statistics.median(l):.0f}")


if __name__ == "__main__":
    import sys
    if "--informe" in sys.argv:
        informe()
    else:
        d = actualizar()
        print(f"[metricas] {len(d['videos'])} vídeos registrados")
