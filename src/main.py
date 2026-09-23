"""Orquesta el pipeline completo: guion -> imágenes -> audio -> vídeo -> subida.
Uso: python src/main.py [--no-upload] [--tema "..."]
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

from guion_gen import generar_guion
from image_gen import generar_imagen
from tts_gen import generar_audio
from render import renderizar_escena, concatenar_escenas

TEMAS_POR_DEFECTO = [
    "un fallo o bug histórico de la informática",
    "un dato curioso sobre un lenguaje de programación",
    "un truco de teclado poco conocido",
    "un hito de la historia de internet",
]


def ejecutar(tema: str, subir: bool) -> None:
    print(f"Generando guion sobre: {tema}")
    guion = generar_guion(tema)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rutas_escenas = []

        for i, escena in enumerate(guion["escenas"]):
            imagen = tmp / f"img_{i}.png"
            audio = tmp / f"audio_{i}.mp3"
            clip = tmp / f"clip_{i}.mp4"

            if not generar_imagen(escena["prompt_imagen"], str(imagen)):
                print(f"No se pudo generar la imagen de la escena {i}, se aborta este vídeo.")
                sys.exit(1)

            generar_audio(escena["texto"], str(audio))
            renderizar_escena(str(imagen), str(audio), str(clip))
            rutas_escenas.append(str(clip))

        salida_final = tmp / "short_final.mp4"
        concatenar_escenas(rutas_escenas, str(salida_final))

        if subir:
            from upload_youtube import subir_short
            url = subir_short(str(salida_final), guion["titulo"], guion["descripcion"])
            print(f"Publicado: {url}")
        else:
            destino_local = Path("preview.mp4")
            destino_local.write_bytes(salida_final.read_bytes())
            print(f"Modo prueba: vídeo guardado en {destino_local.resolve()}, no se sube.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tema", default=None)
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    import random
    tema = args.tema or random.choice(TEMAS_POR_DEFECTO)
    ejecutar(tema, subir=not args.no_upload)
