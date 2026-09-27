"""Monta el short final: cada imagen con su audio de narración (con efecto Ken
Burns como en el canal de la Raspberry Pi), concatenadas, y con subtítulos
animados palabra a palabra quemados encima. Usa solo FFmpeg (ya viene
instalado en los runners de GitHub Actions; el workflow instala además
fonts-dejavu-core, la fuente que usan los subtítulos .ass)."""
import subprocess
from pathlib import Path


def renderizar_escena(imagen: str, audio: str, salida: str, duracion: float,
                       width: int = 1080, height: int = 1920, fps: int = 30) -> None:
    """Imagen fija con efecto Ken Burns (zoom lento) + audio de esa escena,
    igual que en la automatización de la Raspberry Pi (antes era una imagen
    totalmente estática, sin zoom)."""
    zoom_frames = max(int(duracion * fps), 1)
    vf = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2},"
        f"zoompan=z='min(zoom+0.0006,1.25)':d={zoom_frames}:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", imagen,
            "-i", audio,
            "-vf", vf,
            "-t", str(duracion),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
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


def fusionar_timings(palabras_por_escena: list[list[dict]], duraciones: list[float]) -> list[dict]:
    """Concatena los timings de palabras de cada escena, desplazando por la
    duración acumulada de las escenas anteriores (para que el timing case con
    el vídeo final ya concatenado)."""
    offset = 0.0
    fusionado = []
    for palabras, dur in zip(palabras_por_escena, duraciones):
        for p in palabras:
            fusionado.append({
                "text": p["text"],
                "start_ms": p["start_ms"] + offset,
                "dur_ms": p["dur_ms"],
            })
        offset += dur * 1000
    return fusionado


def _fmt_ass_time(ms: float) -> str:
    ms = max(int(ms), 0)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    cs = (ms % 1000) // 10  # centésimas
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _agrupar_palabras(palabras: list[dict], max_palabras: int = 2) -> list[list[dict]]:
    grupos = []
    actual = []
    for p in palabras:
        actual.append(p)
        if len(actual) >= max_palabras or p["text"].strip().endswith((".", ",", "!", "?")):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def construir_subtitulos_ass(palabras: list[dict], ruta_ass: str, width: int = 1080,
                              height: int = 1920, fontsize: int = 72, marginv: int = 280,
                              max_palabras: int = 2, color_base: str = "&HFFFFFF&",
                              color_resaltado: str = "&H00D7FF&") -> str:
    """Genera subtítulos .ass animados palabra a palabra (estilo "caption
    viral" de Shorts/TikTok), igual que en el canal de la Raspberry Pi: grupos
    de 1-2 palabras con un pequeño "pop" de escala al entrar, y la palabra que
    se está narrando en ese instante resaltada en color mientras el resto del
    grupo queda en blanco. color_base/color_resaltado usan formato ASS
    &HAABBGGRR (BGR, no RGB)."""
    grupos = _agrupar_palabras(palabras, max_palabras=max_palabras)

    cabecera = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{fontsize},{color_base},&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = [cabecera]
    pop_ms = 90

    for grupo in grupos:
        inicio_grupo = grupo[0]["start_ms"]
        fin_grupo = grupo[-1]["start_ms"] + grupo[-1]["dur_ms"]
        for idx, palabra_activa in enumerate(grupo):
            seg_inicio = palabra_activa["start_ms"]
            seg_fin = palabra_activa["start_ms"] + palabra_activa["dur_ms"]
            if idx == len(grupo) - 1:
                seg_fin = fin_grupo

            partes = []
            for j, p in enumerate(grupo):
                limpio = p["text"].strip()
                if j == idx:
                    partes.append(f"{{\\c{color_resaltado}}}{limpio}{{\\c{color_base}}}")
                else:
                    partes.append(limpio)
            texto = " ".join(partes)

            if idx == 0:
                anim = f"{{\\fscx60\\fscy60\\t(0,{pop_ms},\\fscx115\\fscy115)\\t({pop_ms},{pop_ms * 2},\\fscx100\\fscy100)}}"
            else:
                anim = ""

            lineas.append(
                f"Dialogue: 0,{_fmt_ass_time(seg_inicio)},{_fmt_ass_time(seg_fin)},Default,,0,0,0,,{anim}{texto}\n"
            )

    Path(ruta_ass).write_text("".join(lineas), encoding="utf-8")
    return ruta_ass


def quemar_subtitulos(video_entrada: str, ruta_ass: str, video_salida: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_entrada, "-vf", f"ass={ruta_ass}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", video_salida],
        check=True,
    )
