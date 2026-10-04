"""Mueve a content/discarded/ los guiones PENDIENTES que repiten el tema de uno ya
publicado/descartado o de otro pendiente más antiguo. No borra nada (el antiduplicado
sigue teniéndolos en cuenta). Uso: python src/limpiar_cola.py [--aplicar]"""
import json
import sys

import dedup
from cola_guiones import DIR_PENDING, descartar

if __name__ == "__main__":
    aplicar = "--aplicar" in sys.argv
    corpus = dedup.construir_corpus()
    pendientes = sorted(p.name for p in DIR_PENDING.glob("*.json"))
    base = [e for e in corpus if e["nombre"] not in pendientes]  # done + discarded
    quitar = []
    for nombre in pendientes:
        guion = json.loads((DIR_PENDING / nombre).read_text(encoding="utf-8"))
        dup = dedup.buscar_duplicado(guion, base)
        if dup:
            quitar.append(nombre)
            print(f"DUP  {guion['titulo']}  <-  {dup[1]}")
        else:
            base.append(next(e for e in corpus if e["nombre"] == nombre))  # se conserva
    print(f"\n{len(quitar)} de {len(pendientes)} pendientes repiten tema; quedarían {len(pendientes) - len(quitar)}")
    if aplicar:
        for n in quitar:
            descartar(DIR_PENDING / n)
        print("movidos a content/discarded/")
