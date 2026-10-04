"""Genera la narración en audio.

ACTUALIZACIÓN (oct. 2026): el motor principal es ahora MeloTTS (Cloudflare Workers
AI, voz neural en español, mismas credenciales CF_* que las imágenes).
StreamElements devuelve 403 desde las IPs de los runners de GitHub, así que toda la
narración caía a gTTS (síntesis robótica). Orden actual: MeloTTS -> StreamElements
(1 intento) -> gTTS -> edge-tts. El resto de este texto describe el diseño original.

MOTOR PRINCIPAL ORIGINAL — StreamElements TTS (voz neural de Amazon Polly, gratis, sin
API key, HTTP simple, funciona igual desde cualquier IP incluida la de los
runners de GitHub Actions). Es una API no oficial pero muy usada y estable en
la práctica; usa una voz neural real (no la síntesis robótica de gTTS), así
que soluciona tanto el problema de sonar "robótica" como, en gran parte, el de
ir demasiado lenta (las voces neurales de Polly ya narran a un ritmo natural,
sin las pausas largas que mete gTTS entre frases).

Como es una API no oficial y gratuita, puede fallar puntualmente por timeout,
429 o un simple hipo de red — antes NO tenía reintentos (a diferencia de
image_gen.py o del fallback de edge-tts), así que cualquier fallo puntual
caía en silencio a gTTS, que es la síntesis robótica que se quería evitar.
Ahora reintenta antes de rendirse.

FALLBACKS, en este orden, por si StreamElements sigue fallando tras reintentar:
1. gTTS (Google Translate TTS) + aceleración con FFmpeg — motor anterior,
   sigue disponible como red de seguridad.
2. edge-tts con la voz de la Raspberry Pi (es-ES-AlvaroNeural) — motor de
   mejor calidad, pero su endpoint de WebSocket está bloqueado (403) desde
   las IPs de datacenter de los runners de GitHub Actions, así que casi
   nunca llega a usarse aquí; se deja solo por si algún día deja de estarlo.

El motor que termina generando el audio se imprime siempre por stdout (se ve
en el log de la Action) para poder diagnosticar sin adivinar si algún día
vuelve a sonar raro.

TIMING POR PALABRA: ninguno de estos motores expone tiempos reales por
palabra en este entorno (edge-tts sí lo haría vía WordBoundary, pero rara vez
se llega a usar). Para poder generar subtítulos animados palabra a palabra
como en el canal de la Pi, se reparte la duración real del audio ya generado
entre las palabras del texto, proporcionalmente a su longitud. No es tan
preciso como un timing real, pero da un resultado visualmente correcto para
subtítulos tipo "caption viral".
"""
import asyncio
import base64
import os
import subprocess
import time
import urllib.parse

import requests

VOZ_STREAMELEMENTS = "Sergio"  # voz neural masculina es-ES (Amazon Polly), ritmo natural
VOZ_EDGE = "es-ES-AlvaroNeural"
VELOCIDAD_GTTS = 1.3  # factor de aceleración aplicado con ffmpeg (atempo) al motor de respaldo


def _generar_streamelements_una_vez(texto: str, destino: str) -> None:
    url = (
        "https://api.streamelements.com/kappa/v2/speech"
        f"?voice={VOZ_STREAMELEMENTS}&text={urllib.parse.quote(texto)}"
    )
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "")
    if not content_type.startswith("audio/") or len(r.content) < 2000:
        raise RuntimeError(
            f"StreamElements no devolvió audio válido (content-type={content_type!r}, "
            f"tamaño={len(r.content)} bytes)"
        )
    with open(destino, "wb") as f:
        f.write(r.content)


def _generar_streamelements(texto: str, destino: str, intentos: int = 3) -> None:
    """Antes esta llamada no reintentaba nada: un solo timeout o 429 puntual
    de esta API no oficial hacía caer todo el vídeo a gTTS (la voz "robótica"
    que se quería evitar). Ahora reintenta con backoff antes de rendirse."""
    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            _generar_streamelements_una_vez(texto, destino)
            return
        except Exception as e:
            ultimo_error = e
            print(f"[tts_gen] StreamElements intento {intento}/{intentos} falló: {e}")
            if intento < intentos:
                time.sleep(2 * intento)
    raise ultimo_error


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


def _generar_edge_con_reintentos(texto: str, destino: str, intentos: int = 2) -> None:
    ultimo_error: Exception | None = None
    for intento in range(1, intentos + 1):
        try:
            asyncio.run(_generar_edge(texto, destino))
            return
        except Exception as e:
            ultimo_error = e
            print(f"[tts_gen] edge-tts intento {intento}/{intentos} falló: {e}")
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



def _generar_melotts(texto: str, destino: str) -> None:
    """MeloTTS de Cloudflare Workers AI (voz neural en español, ~2 s por frase, coste
    despreciable y mismas credenciales CF_* que las imágenes). Es el motor principal desde
    que StreamElements responde 403 desde las IPs de los runners de GitHub: sin él TODAS las
    narraciones caían a gTTS (robótica). Devuelve WAV en base64 -> se convierte a mp3."""
    cuentas = []
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        cuentas.append((os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]))
    if os.environ.get("CF_ACCOUNT_ID_2") and os.environ.get("CF_API_TOKEN_2"):
        cuentas.append((os.environ["CF_ACCOUNT_ID_2"], os.environ["CF_API_TOKEN_2"]))
    if not cuentas:
        raise RuntimeError("Sin credenciales de Cloudflare para MeloTTS")
    ultimo: Exception | None = None
    for account_id, token in cuentas:
        for intento in (1, 2):
            try:
                r = requests.post(
                    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/myshell-ai/melotts",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"prompt": texto, "lang": "es"},
                    timeout=45,
                )
                if r.status_code in (402, 429):
                    raise RuntimeError(f"MeloTTS sin cuota: {r.status_code}")
                r.raise_for_status()
                audio = (r.json().get("result") or {}).get("audio")
                if not audio:
                    raise RuntimeError("MeloTTS no devolvió audio")
                wav = destino + ".melo.wav"
                with open(wav, "wb") as f:
                    f.write(base64.b64decode(audio))
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", wav, "-codec:a", "libmp3lame", "-q:a", "3", destino],
                        check=True, capture_output=True,
                    )
                finally:
                    os.remove(wav)
                return
            except Exception as e:
                ultimo = e
                print(f"[tts_gen] MeloTTS intento {intento} falló: {e}")
                if "sin cuota" in str(e):
                    break
                time.sleep(2 * intento)
    raise ultimo


def generar_audio(texto: str, destino: str) -> tuple[float, list[dict]]:
    """Genera el audio de la escena y devuelve (duracion_s, palabras) para el
    render con subtítulos. `palabras` es una lista de {"text", "start_ms",
    "dur_ms"} — ver la cabecera del módulo sobre por qué es un timing estimado
    y no real."""
    try:
        _generar_melotts(texto, destino)
        print("[tts_gen] motor usado: melotts (Cloudflare, voz neural es)")
    except Exception as e0:
        print(f"[tts_gen] MeloTTS falló ({e0}), probando StreamElements...")
        try:
            _generar_streamelements(texto, destino, intentos=1)
            print("[tts_gen] motor usado: streamelements (voz neural Sergio)")
        except Exception as e:
            print(f"[tts_gen] StreamElements falló ({e}), probando gTTS como respaldo...")
            try:
                _generar_gtts(texto, destino)
                print("[tts_gen] motor usado: gtts (respaldo, síntesis no neural)")
            except Exception as e2:
                print(f"[tts_gen] gTTS también falló ({e2}), probando edge-tts como último respaldo...")
                _generar_edge_con_reintentos(texto, destino)
                print("[tts_gen] motor usado: edge-tts (último respaldo)")

    duracion = _duracion_audio(destino)
    palabras = _estimar_timing_palabras(texto, duracion)
    return duracion, palabras
