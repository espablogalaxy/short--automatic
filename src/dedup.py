"""Detección de guiones duplicados (portado del canal de la Raspberry Pi).

Motivo: la cola tenía el mismo tema una y otra vez (Hessdalen x7, Vredefort x6,
Bloop x6, Glaciar de sangre x5...) porque el modelo reformula el título y elude
la lista de temas usados. Ahora se comprueba POR CÓDIGO tras generar.

Dos señales (basta una):
  1. Solapamiento de vocabulario (Jaccard >= 0.30) entre título + 2 primeras
     escenas del guion nuevo y cualquiera ya existente.
  2. Nombre propio raro compartido en el TÍTULO (palabra con mayúscula inicial,
     no la primera de la frase, que en los títulos del corpus solo aparece en UN
     guion existente): Hessdalen, Vredefort, Darvaza... -> mismo tema casi seguro.

Auditoría:  python src/dedup.py --auditar
"""
import glob
import json
import os
import re
import sys
import unicodedata

UMBRAL_JACCARD = 0.30
CARPETAS = ("pending", "done", "discarded")

_STOP = set(
    "el la los las un una unos unas de del al en y o que por para con sin se su sus "
    "es fue era como mas muy tu tus este esta esto estos estas a lo le les ya si no "
    "mi me te ha han hay ser sobre entre pero cuando donde cada todo toda todos todas "
    "tiene tienen hace hizo solo sabias cual cuales porque tambien".split()
)


# Palabras geográficas genéricas que van con mayúscula en los títulos ("Valle", "Monte",
# "Bosque"...) y NO identifican un tema: darían falsos positivos entre temas distintos.
_NP_GENERICOS = set(
    "valle monte lago cráter crater isla puerta bosque pozo fosa punto desierto parque rio río "
    "tierra planeta océano oceano mar gran glaciar volcán volcan cueva cueva misterio secreto "
    "secretos lugar mundo".split()
)


def _norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _tokens(texto):
    return {w for w in re.findall(r"[a-z0-9]+", _norm(texto)) if w not in _STOP and len(w) > 2}


def _contexto(guion):
    escenas = guion.get("escenas", [])[:2]
    return guion.get("titulo", "") + " " + " ".join(e.get("texto", "") for e in escenas)


def _nombres_propios(titulo):
    out = set()
    for frase in re.split(r"[.!?¿¡:\n]+", titulo):
        palabras = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ0-9]+", frase)
        for p in palabras[1:]:
            if len(p) >= 4 and p[0].isupper() and not p.isupper() and not p.isdigit():
                if _norm(p) not in {_norm(g) for g in _NP_GENERICOS}:
                    out.add(_norm(p))
    return out


def _entrada(nombre, guion):
    return {
        "nombre": nombre,
        "titulo": guion.get("titulo", ""),
        "tok": _tokens(_contexto(guion)),
        "np": _nombres_propios(guion.get("titulo", "")),
    }


def construir_corpus(base="content"):
    corpus = []
    for carpeta in CARPETAS:
        for path in glob.glob(os.path.join(base, carpeta, "*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    g = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(g, dict) and g.get("titulo"):
                corpus.append(_entrada(os.path.basename(path), g))
    return corpus


def _df_nombres(corpus):
    df = {}
    for e in corpus:
        for p in e["np"]:
            df[p] = df.get(p, 0) + 1
    return df


def buscar_duplicado(guion, corpus):
    """(nombre_existente, motivo) si el guion parece repetir un tema, o None."""
    nuevo = _entrada("(nuevo)", guion)
    df = _df_nombres(corpus)
    for e in corpus:
        if nuevo["tok"] and e["tok"]:
            j = len(nuevo["tok"] & e["tok"]) / len(nuevo["tok"] | e["tok"])
            if j >= UMBRAL_JACCARD:
                return e["nombre"], f"solapamiento {j:.2f} con \"{e['titulo']}\""
        for p in nuevo["np"] & e["np"]:
            if df.get(p, 0) == 1:
                return e["nombre"], f"nombre propio raro '{p}' ya en \"{e['titulo']}\""
    return None


def pares_duplicados(corpus):
    """Pares (a, b) sospechosos dentro del propio corpus (para auditar/limpiar)."""
    df = _df_nombres(corpus)
    out = []
    for i, a in enumerate(corpus):
        for b in corpus[i + 1:]:
            motivo = None
            if a["tok"] and b["tok"]:
                j = len(a["tok"] & b["tok"]) / len(a["tok"] | b["tok"])
                if j >= UMBRAL_JACCARD:
                    motivo = f"jaccard {j:.2f}"
            if not motivo:
                comp = [p for p in a["np"] & b["np"] if df.get(p, 0) == 2]
                if comp:
                    motivo = "nombre raro: " + ", ".join(comp)
            if motivo:
                out.append((motivo, a, b))
    return out


if __name__ == "__main__":
    corpus = construir_corpus()
    pares = pares_duplicados(corpus)
    print(f"{len(corpus)} guiones, {len(pares)} pares sospechosos")
    for motivo, a, b in pares:
        print(f"- [{motivo}]\n    {a['nombre'][:55]} | {a['titulo']}\n    {b['nombre'][:55]} | {b['titulo']}")
