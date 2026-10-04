"""Orquesta el pipeline completo: guion (de la cola, o generado al vuelo si
está vacía) -> imágenes -> audio -> vídeo (Ken Burns + subtítulos animados)
-> subida.
Uso:
  python src/main.py [--no-upload]              # coge de la cola; si está
                                                  # vacía, genera uno nuevo
  python src/main.py [--no-upload] --tema "..."  # se salta la cola y genera
                                                  # un guion nuevo sobre ese
                                                  # tema concreto
"""
import argparse
import sys
import tempfile
from pathlib import Path

from cola_guiones import guardar_pendiente, sacar_pendiente, marcar_hecho
from guion_gen import generar_guion
from image_gen import generar_imagen
from tts_gen import generar_audio
from render import (
    renderizar_escena,
    concatenar_escenas,
    fusionar_timings,
    construir_subtitulos_ass,
    quemar_subtitulos,
)

def _conseguir_guion(tema: str | None) -> tuple[Path, dict]:
    """--tema fuerza un guion nuevo sobre ese tema. Si no, coge el siguiente de la cola
    (el más corto de los primeros pendientes); si la cola está vacía, genera uno nuevo
    (tema elegido por el modelo, sin repetir nada de pending/done/discarded)."""
    if tema:
        print(f"Tema forzado por --tema, generando guion nuevo sobre: {tema}")
        guion = generar_guion(tema)
        return guardar_pendiente(guion), guion

    pendiente = sacar_pendiente()
    if pendiente:
        ruta_guion, guion = pendiente
        print(f"Cogiendo guion pendiente de la cola: {ruta_guion.name}")
        return ruta_guion, guion

    print("Cola de guiones vacía, generando uno nuevo")
    guion = generar_guion()
    return guardar_pendiente(guion), guion


def ejecutar(tema: str | None, subir: bool) -> None:
    ruta_guion, guion = _conseguir_guion(tema)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rutas_escenas = []
        palabras_por_escena = []
        duraciones = []

        for i, escena in enumerate(guion["escenas"]):
            imagen = tmp / f"img_{i}.png"
            audio = tmp / f"audio_{i}.mp3"
            clip = tmp / f"clip_{i}.mp4"

            if not generar_imagen(escena["prompt_imagen"], str(imagen)):
                anterior = tmp / f"img_{i - 1}.png"
                if i > 0 and anterior.exists():
                    # Antes se abortaba TODO el vídeo (y se perdía el hueco del día) si una
                    # sola escena fallaba; ahora se reutiliza la imagen anterior.
                    print(f"No se pudo generar la imagen de la escena {i}, se reutiliza la anterior.")
                    imagen.write_bytes(anterior.read_bytes())
                else:
                    print(f"No se pudo generar la imagen de la escena {i}, se aborta este vídeo.")
                    sys.exit(1)

            duracion, palabras = generar_audio(escena["texto"], str(audio))
            renderizar_escena(str(imagen), str(audio), str(clip), duracion)
            rutas_escenas.append(str(clip))
            palabras_por_escena.append(palabras)
            duraciones.append(duracion)

        sin_subtitulos = tmp / "short_sin_subs.mp4"
        concatenar_escenas(rutas_escenas, str(sin_subtitulos))

        palabras_totales = fusionar_timings(palabras_por_escena, duraciones)
        ruta_ass = tmp / "subtitulos.ass"
        construir_subtitulos_ass(palabras_totales, str(ruta_ass))

        salida_final = tmp / "short_final.mp4"
        quemar_subtitulos(str(sin_subtitulos), str(ruta_ass), str(salida_final))

        if subir:
            from upload_youtube import subir_short
            url = subir_short(str(salida_final), guion["titulo"], guion["descripcion"], guion.get("tags"))
            print(f"Publicado: {url}")
            marcar_hecho(ruta_guion, guion, url)
        else:
            destino_local = Path("preview.mp4")
            destino_local.write_bytes(salida_final.read_bytes())
            print(f"Modo prueba: vídeo guardado en {destino_local.resolve()}, no se sube.")
            print(f"El guion sigue en la cola ({ruta_guion}), no se marca como hecho.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tema", default=None)
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    ejecutar(args.tema, subir=not args.no_upload)
