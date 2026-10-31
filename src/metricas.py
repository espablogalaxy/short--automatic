"""Bucle de feedback con datos REALES del canal (portado de la Raspberry Pi).

Lee las vistas de los últimos vídeos desde el feed RSS público del canal (sin
autenticación, funciona desde GitHub Actions; devuelve los 15 más recientes, así
que se ejecuta a diario y acumula el histórico en content/metricas.json).
guion_gen.py inyecta en cada prompt los títulos que MEJOR y PEOR rinden.

Además, pesos_modo() cruza las vistas reales con el "modo" (lugar/fenómeno/récord)
que guardó cada guion en content/done/*.json, para que guion_gen.py elija el
siguiente ángulo ponderado por lo que de verdad funciona en este canal, en vez
de una rotación fija.
"""
import json
import os
import re
import statistics
import html
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

RUTA = os.path.join("content", "metricas.json")
DIR_DONE = Path("content/done")
CHANNEL_ID = os.environ.get("YT_CHANNEL_ID", "UCep5zLNn_tccIjquFD4aeCQ")
UMBRAL_EXITO = 500
MODOS = ("lugar", "fenomeno", "record")


def cargar():
    try:
        with open(RUTA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"actualizado": None, "videos": {}}


def _feed(intentos=3):
    """El feed RSS público de YouTube a veces da un 404/5xx puntual (visto el
    2026-10-15); reintenta con backoff antes de rendirse, para que un hipo
    transitorio no tumbe todo el cron de métricas del día."""
    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            r = requests.get(
                "https://www.youtube.com/feeds/videos.xml", params={"channel_id": CHANNEL_ID}, timeout=30
            )
            r.raise_for_status()
            break
        except requests.RequestException as e:
            ultimo_error = e
            print(f"[metricas] feed intento {intento}/{intentos} falló: {e}")
            if intento < intentos:
                time.sleep(5 * intento)
    else:
        raise ultimo_error
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


def _modo_por_titulo():
    """Mapa titulo->modo a partir de los guiones ya publicados en content/done/
    (cada guion guarda su "modo" desde que guion_gen.py lo añadió). Los
    publicados antes de ese cambio simplemente no aparecen en el mapa."""
    mapa = {}
    if not DIR_DONE.exists():
        return mapa
    for ruta in DIR_DONE.glob("*.json"):
        try:
            g = json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            continue
        modo = g.get("modo")
        titulo = g.get("titulo")
        if modo and titulo:
            mapa[titulo] = modo
    return mapa


def pesos_modo(minimo_por_modo=5, piso=0.12):
    """Pondera cada modo (lugar/fenómeno/récord) por su mediana de vistas reales,
    para que guion_gen.py elija el siguiente ángulo con más probabilidad cuanto
    mejor rinda, en vez de una rotación fija. Devuelve {} (sin cambios, se usa la
    rotación fría) mientras no haya al menos `minimo_por_modo` shorts maduros de
    CADA modo con el campo "modo" ya guardado. `piso` evita que un modo se quede
    a 0% de probabilidad (mantiene algo de exploración)."""
    mapa_modos = _modo_por_titulo()
    if not mapa_modos:
        return {}
    maduros = [v for v in cargar().get("videos", {}).values() if _edad_dias(v) >= 2]
    agrupado = {m: [] for m in MODOS}
    for v in maduros:
        modo = mapa_modos.get(v["titulo"])
        if modo in agrupado:
            agrupado[modo].append(v["vistas"])
    if any(len(agrupado[m]) < minimo_por_modo for m in MODOS):
        return {}
    medianas = {m: statistics.median(agrupado[m]) for m in MODOS}
    total = sum(medianas.values()) or 1
    return {m: max(medianas[m] / total, piso) for m in MODOS}


def informe():
    datos_cargados = cargar()
    maduros = [v for v in datos_cargados.get("videos", {}).values() if _edad_dias(v) >= 2]
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
    mapa_modos = _modo_por_titulo()
    if mapa_modos:
        print("Por modo (lugar/fenomeno/record):")
        for m in MODOS:
            vs_modo = [v["vistas"] for v in maduros if mapa_modos.get(v["titulo"]) == m]
            if vs_modo:
                print(f"  {m}: n={len(vs_modo)} mediana={statistics.median(vs_modo):.0f}")


if __name__ == "__main__":
    import sys
    if "--informe" in sys.argv:
        informe()
    else:
        d = actualizar()
        print(f"[metricas] {len(d['videos'])} vídeos registrados")
