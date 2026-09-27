"""Genera N guiones de golpe con el LLM y los deja en content/pending/, sin
producir vídeo ni gastar cuota de imágenes/TTS/YouTube — solo para tener una
reserva de guiones ya escritos, igual que la cola del canal de la Pi.

Pensado para lanzarlo a mano de vez en cuando (o añadir un workflow_dispatch
aparte), no como parte del cron diario.

Uso: python src/generar_lote.py [N]   (N=5 por defecto)
"""
import random
import sys

from cola_guiones import guardar_pendiente
from guion_gen import generar_guion
from main import TEMAS_PLANETA

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    temas = random.sample(TEMAS_PLANETA, k=min(n, len(TEMAS_PLANETA)))

    for i, tema in enumerate(temas, start=1):
        print(f"[{i}/{len(temas)}] Generando guion sobre: {tema}")
        guion = generar_guion(tema)
        ruta = guardar_pendiente(guion)
        print(f"  -> guardado en {ruta}")

    print(f"\nListo: {len(temas)} guiones nuevos en content/pending/.")
