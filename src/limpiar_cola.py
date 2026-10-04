"""Mueve a content/discarded/ los guiones PENDIENTES que repiten el tema de uno ya
publicado o de otro pendiente más antiguo. No borra nada (el antiduplicado al generar
sigue teniendo en cuenta los descartados). Es idempotente: una segunda pasada no
descarta nada más. Uso: python src/limpiar_cola.py [--aplicar]"""
import json
import sys

import dedup
from cola_guiones import DIR_DONE, DIR_PENDING, descartar

if __name__ == "__main__":
    aplicar = "--aplicar" in sys.argv
    corpus = dedup.construir_corpus()
    pendientes = sorted(p.name for p in DIR_PENDING.glob("*.json"))
    # Solo se compara contra lo ya PUBLICADO y contra pendientes anteriores. Los descartados
    # NO cuentan aquí: son copias de los guiones que se conservaron, y si contasen, una
    # segunda pasada descartaría también el original y el tema se perdería.
    publicados = {p.name for p in DIR_DONE.glob("*.json")}
    base = [e for e in corpus if e["nombre"] in publicados]
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
