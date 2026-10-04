"""Rellena la cola de guiones SIN producir vídeo ni gastar cuota de imágenes/TTS/YouTube.

Antes sacaba temas al azar de una lista fija de 25 (de ahí que la cola estuviese llena
de Hessdalen/Vredefort/Bloop repetidos) y generaba 18 guiones al día aunque solo se
publican 3. Ahora:
  - el modelo elige temas NUEVOS (con la lista de títulos usados y el antiduplicado);
  - solo rellena hasta --min-cola (30 por defecto = ~10 días de reserva);
  - genera como máximo N por ejecución.

Uso: python src/generar_lote.py [N] [--min-cola 30]
"""
import argparse

import dedup
from cola_guiones import contar_pendientes, guardar_pendiente
from guion_gen import GuionGenError, generar_guion

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=3, help="máximo de guiones a generar")
    ap.add_argument("--min-cola", type=int, default=30, help="no generar si ya hay tantos pendientes")
    args = ap.parse_args()

    hay = contar_pendientes()
    faltan = max(0, args.min_cola - hay)
    objetivo = min(args.n, faltan)
    print(f"Cola: {hay} pendientes (mínimo deseado {args.min_cola}) -> generando {objetivo}")

    creados = 0
    for i in range(1, objetivo + 1):
        corpus = dedup.construir_corpus()  # se recalcula: incluye los recién creados
        try:
            guion = generar_guion(corpus=corpus)
        except GuionGenError as e:
            print(f"  [{i}/{objetivo}] no se pudo generar un guion nuevo: {e}")
            continue
        print(f"  [{i}/{objetivo}] {guion['titulo']} -> {guardar_pendiente(guion)}")
        creados += 1
    print(f"Listo: {creados} guiones nuevos en content/pending/.")
