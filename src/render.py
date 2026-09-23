"""Monta el short final: cada imagen con su audio de narración, concatenadas.
Usa solo FFmpeg (ya viene instalado en los runners de GitHub Actions)."""
import subprocess
from pathlib import Path


def _duracion_audio(ruta_audio: str) -> float:
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", ruta_audio],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())


def renderizar_escena(imagen: str, audio: str, salida: str) -> None:
    duracion = _duracion_audio(audio)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", imagen,
            "-i", audio,
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-t", str(duracion),
            "-pix_fmt", "yuv420p",
            salida,
        ],
        check=True,
    )


def concatenar_escenas(rutas_escenas: list[str], salida_final: str) -> None:
    lista_txt = Path(salida_final).with_suffix(".txt")
    lista_txt.write_text("\n".join(f"file '{r}'" for r in rutas_escenas))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista_txt),
         "-c", "copy", salida_final],
        check=True,
    )
    lista_txt.unlink()
