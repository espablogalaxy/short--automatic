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

TEMAS_PLANETA = [
    "el abismo de Challenger y su profundidad exacta",
    "el hongo gigante de Oregón como el ser vivo más grande del mundo",
    "el supervolcán inactivo bajo el parque de Yellowstone",
    "el punto Nemo y su lejanía extrema de cualquier masa terrestre",
    "la anomalía magnética del Atlántico Sur y su efecto en satélites",
    "el pozo superprofundo de Kola en Rusia",
    "el lago Hillier en Australia y el origen biológico de su color rosa",
    "el río hirviente de la Amazonía peruana",
    "el monte Roraima y sus especies endémicas aisladas",
    "la puerta del infierno de Darvaza ardiendo en Turkmenistán",
    "el glaciar de sangre en la Antártida",
    "las piedras navegantes que se mueven solas en el Valle de la Muerte",
    "la cueva de los cristales gigantes de Naica en México",
    "el bosque torcido de Gryfino en Polonia",
    "la cascada de fuego estacional del parque Yosemite",
    "el lago de lava permanente del monte Nyiragongo",
    "la presión extrema y las especies abisales de la fosa de las Marianas",
    "el ojo del Sahara o estructura de Richat visible desde el espacio",
    "el fenómeno inexplicado de las luces de Hessdalen en Noruega",
    "el desierto de Atacama como el lugar no polar más seco del planeta",
    "el cráter de Vredefort como el mayor impacto de meteorito registrado",
    "la isla de Socotra y su flora con apariencia alienígena",
    "el origen real del sonido de baja frecuencia 'The Bloop' en el océano",
    "la Gran Barrera de Coral como la estructura viva más grande de la Tierra",
    "el movimiento tectónico que está partiendo África en el valle del Rift",
]


def _conseguir_guion(tema: str | None) -> tuple[Path, dict]:
    """Si se pasa --tema, se salta la cola y genera un guion nuevo sobre ese
    tema. Si no, coge el guion pendiente más antiguo de la cola; si la cola
    está vacía, genera uno nuevo sobre un tema aleatorio y lo mete en la cola
    antes de usarlo (así queda registrado igual que si viniera de ella)."""
    if tema:
        print(f"Tema forzado por --tema, generando guion nuevo sobre: {tema}")
        guion = generar_guion(tema)
        return guardar_pendiente(guion), guion

    pendiente = sacar_pendiente()
    if pendiente:
        ruta_guion, guion = pendiente
        print(f"Cogiendo guion pendiente de la cola: {ruta_guion.name}")
        return ruta_guion, guion

    import random
    tema = random.choice(TEMAS_PLANETA)
    print(f"Cola de guiones vacía, generando uno nuevo sobre: {tema}")
    guion = generar_guion(tema)
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
            url = subir_short(str(salida_final), guion["titulo"], guion["descripcion"])
            print(f"Publicado: {url}")
            marcar_hecho(ruta_guion, guion)
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
