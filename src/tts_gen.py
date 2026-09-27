"""Genera la narración en audio.

gTTS (Google Translate TTS) como motor principal: es HTTP simple y no depende
del endpoint no oficial de WebSocket de Bing, que Microsoft está cortando (403)
desde IPs de datacenter como las de los runners de GitHub Actions. Por eso la
automatización de la Raspberry Pi (que usa edge-tts como motor único, con
tiempos reales por palabra vía WordBoundary) no se puede portar tal cual aquí.

edge-tts se mantiene como fallback con reintentos, por si algún día vuelve a
funcionar de forma fiable en CI o si gTTS falla puntualmente.

Dos cambios respecto a la versión anterior:

1. VELOCIDAD: la narración con gTTS se percibía muy lenta y "pesaba" el vídeo
   comparada con la voz del canal de la Pi (edge-tts a -4%, ya de por sí
   ágil). Aquí se reencodea el audio con FFmpeg (filtro atempo) para acelerar
   el ritmo de lectura y que suene parecido.
2. TIMING POR PALABRA ESTIMADO: gTTS no expone tiempos reales por palabra.
   Para poder generar subtítulos animados palabra a palabra como en el canal
   de la Pi, se reparte la duración real del audio ya generado entre las
   palabras del texto, proporcionalmente a su longitud. No es tan preciso
   como un timing real (WordBoundary), pero da un resultado visualmente
   correcto para subtítulos tipo "caption viral".
"""
import asyncio
import os
import subprocess
import time

VOZ_EDGE = "es-ES-AlvaroNeural"
VELOCIDAD_GTTS = 1.15  # factor de aceleración aplicado con ffmpeg (atempo)


def _generar_gtts_bruto(texto: str, destino: str) -> None:
    from gtts import gTTS

    tts = gTTS(text=texto, lang="es", tld="es")
    tts.save(destino)


def _acelerar_audio(origen: str, destino: str, factor: float) -> None:
    """Reencodea el audio a `factor` veces la velocidad original con FFmpeg.
    atempo admite 0.5-2.0 en un único filtro, así que aquí basta con uno."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", origen, "-filter:a", f"atempo={factor}", destino],
        check=True, capture_output=True,
    )


def _generar_gtts(texto: str, destino: str, factor: float = VELOCIDAD_GTTS) -> None:
    bruto = destino + ".bruto.mp3"
    _generar_gtts_bruto(texto, bruto)
    try:
        _acelerar_audio(bruto, destino, factor)
    finally:
        os.remove(bruto)


async def _generar_edge(texto: str, destino: str) -> None:
    import edge_tts

    comunicador = edge_tts.Communicate(texto, VOZ_EDGE)
    await comunicador.save(destino)


def _generar_edge_con_reintentos(texto: str, destino: str, intentos: int = 3) -> None:
    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            asyncio.run(_generar_edge(texto, destino))
            return
        except Exception as e:
            ultimo_error = e
            print(f"edge-tts intento {intento}/{intentos} falló: {e}")
            if intento < intentos:
                time.sleep(2 * intento)
    raise ultimo_error


def _duracion_audio(ruta: str) -> float:
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", ruta],
        capture_output=True, text=True, check=True,
    )
    return float(resultado.stdout.strip())


def _estimar_timing_palabras(texto: str, duracion_s: float) -> list[dict]:
    """Reparte la duración total entre las palabras del texto, proporcionalmente
    a su longitud (+1 por el espacio/pausa siguiente). Devuelve la misma forma
    que el WordBoundary real de edge-tts (start_ms/dur_ms) para poder reutilizar
    el generador de subtítulos .ass del canal de la Pi."""
    palabras = texto.split()
    if not palabras:
        return []
    pesos = [len(p) + 1 for p in palabras]
    total_peso = sum(pesos)
    duracion_ms = duracion_s * 1000
    palabras_out = []
    cursor_ms = 0.0
    for palabra, peso in zip(palabras, pesos):
        dur_ms = duracion_ms * (peso / total_peso)
        palabras_out.append({"text": palabra, "start_ms": cursor_ms, "dur_ms": dur_ms})
        cursor_ms += dur_ms
    return palabras_out


def generar_audio(texto: str, destino: str) -> tuple[float, list[dict]]:
    """Genera el audio de la escena y devuelve (duracion_s, palabras) para el
    render con subtítulos. `palabras` es una lista de {"text", "start_ms",
    "dur_ms"} — ver la cabecera del módulo sobre por qué es un timing estimado
    y no real."""
    try:
        _generar_gtts(texto, destino)
    except Exception as e:
        print(f"gTTS falló ({e}), probando edge-tts como respaldo...")
        _generar_edge_con_reintentos(texto, destino)

    duracion = _duracion_audio(destino)
    palabras = _estimar_timing_palabras(texto, duracion)
    return duracion, palabras
