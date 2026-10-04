"""Utilidades de voz: normalización del texto para el TTS, limpieza de silencios y motor
Gemini TTS.

Problemas que resuelve (reportados al ver el primer short con MeloTTS):
  - Voz robótica: Gemini TTS suena mucho más natural (usa la GEMINI_API_KEY que ya existe).
  - Pausas largas: MeloTTS añade ~0,9 s de silencio al final de CADA escena (~7 s de aire
    muerto por vídeo). Se recorta el silencio inicial/final de todos los motores.
  - Abreviaturas: la voz decía "cm" en vez de "centímetros". normalizar_para_voz expande
    unidades y símbolos antes de sintetizar (y el mismo texto se usa para los subtítulos).
"""
import base64
import os
import re
import subprocess
import time

import requests

# --------------------------------------------------------------------------- normalización

_UNIDADES = [
    # (patrón sobre lo que va tras el número, sustitución). Orden: de más largo a más corto.
    (r"km\s?/\s?h", "kilómetros por hora"),
    (r"km²|km2", "kilómetros cuadrados"),
    (r"m²|m2", "metros cuadrados"),
    (r"m³|m3", "metros cúbicos"),
    (r"km", "kilómetros"),
    (r"cm", "centímetros"),
    (r"mm", "milímetros"),
    (r"kg", "kilogramos"),
    (r"mg", "miligramos"),
    (r"°\s?C|º\s?C", "grados Celsius"),
    (r"°\s?F|º\s?F", "grados Fahrenheit"),
    (r"°|º", "grados"),
    (r"%", "por ciento"),
    (r"min", "minutos"),
    (r"h", "horas"),
    (r"m", "metros"),
    (r"g", "gramos"),
]

_SUELTAS = [
    (r"\bEE\.\s?UU\.?", "Estados Unidos"),
    (r"\baprox\.", "aproximadamente"),
    (r"\betc\.", "etcétera"),
    (r"\ba\.\s?C\.", "antes de Cristo"),
    (r"\bd\.\s?C\.", "después de Cristo"),
    (r"\bUTC\b", "U T C"),
]


def normalizar_para_voz(texto: str) -> str:
    t = texto
    # Miles con punto o espacio: "1.086" / "12 262" / "6 000" -> "1086" / "12262" / "6000"
    t = re.sub(r"(?<![\d.,])(\d{1,3})((?:[.\u00a0\u202f ]\d{3})+)(?![\d])",
               lambda m: m.group(1) + re.sub(r"[.\u00a0\u202f ]", "", m.group(2)), t)
    # Número + unidad abreviada
    for patron, sust in _UNIDADES:
        t = re.sub(r"(?<=\d)\s?(?:" + patron + r")(?![A-Za-zÁÉÍÓÚáéíóúñÑ²³])", " " + sust, t)
    for patron, sust in _SUELTAS:
        t = re.sub(patron, sust, t)
    return re.sub(r"\s{2,}", " ", t).strip()


# --------------------------------------------------------------------------- limpieza de audio

_FILTRO_RECORTE = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.04,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,"
    "areverse"
)


def _duracion(ruta: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", ruta],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def recortar_silencios(ruta_mp3: str) -> None:
    """Quita el silencio del principio y del final (NO toca las pausas internas)."""
    tmp = ruta_mp3 + ".trim.mp3"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", ruta_mp3, "-af", _FILTRO_RECORTE,
             "-codec:a", "libmp3lame", "-q:a", "3", tmp],
            check=True, capture_output=True,
        )
        if _duracion(tmp) >= 0.5:  # si recortó de más, se conserva el original
            os.replace(tmp, ruta_mp3)
    except Exception as e:
        print(f"[voz_utils] no se pudo recortar silencios ({e}); se deja el audio tal cual")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def compactar_pausas(ruta_mp3: str, max_pausa: float = 0.3, dejar: float = 0.2) -> None:
    """Acorta las pausas INTERNAS largas: todo silencio mayor que `max_pausa` se reduce a
    `dejar` segundos quitándole el tramo central (ritmo ágil de Shorts; las pausas de ~0,5 s
    entre frases se sentían lentas). Se hace a mano porque el filtro silenceremove de ffmpeg
    apenas acorta silencios internos."""
    import array
    import wave

    wav_in = ruta_mp3 + ".in.wav"
    wav_out = ruta_mp3 + ".out.wav"
    tmp = ruta_mp3 + ".pausas.mp3"
    try:
        subprocess.run(["ffmpeg", "-y", "-i", ruta_mp3, "-ar", "44100", "-ac", "1", wav_in],
                       check=True, capture_output=True)
        log = subprocess.run(
            ["ffmpeg", "-i", wav_in, "-af", f"silencedetect=noise=-35dB:d={max_pausa}", "-f", "null", "-"],
            capture_output=True, text=True,
        ).stderr
        inicios = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
        fines = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
        with wave.open(wav_in, "rb") as w:
            sr, canales, ancho = w.getframerate(), w.getnchannels(), w.getsampwidth()
            datos = array.array("h")
            datos.frombytes(w.readframes(w.getnframes()))
        if ancho != 2 or canales != 1 or not inicios:
            return
        mitad = dejar / 2
        salida = array.array("h")
        cursor = 0
        for ini, fin in zip(inicios, fines):
            if fin - ini <= max_pausa:
                continue
            a = int(max(ini, 0) * sr)
            corta_desde = a + int(mitad * sr)          # conserva el principio de la pausa
            corta_hasta = int(fin * sr) - int(mitad * sr)  # y el final; quita lo del medio
            if corta_hasta <= corta_desde or corta_desde < cursor:
                continue
            salida.extend(datos[cursor:corta_desde])
            cursor = corta_hasta
        salida.extend(datos[cursor:])
        with wave.open(wav_out, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes(salida.tobytes())
        subprocess.run(["ffmpeg", "-y", "-i", wav_out, "-codec:a", "libmp3lame", "-q:a", "3", tmp],
                       check=True, capture_output=True)
        if _duracion(tmp) >= 0.7 * _duracion(ruta_mp3):  # salvaguarda: no comerse el audio
            os.replace(tmp, ruta_mp3)
    except Exception as e:
        print(f"[voz_utils] no se pudieron compactar pausas ({e}); se deja el audio tal cual")
    finally:
        for f in (wav_in, wav_out, tmp):
            if os.path.exists(f):
                os.remove(f)


# --------------------------------------------------------------------------- Gemini TTS

GEMINI_TTS_MODELOS = [
    m.strip() for m in os.environ.get(
        "GEMINI_TTS_MODELS", "gemini-2.5-flash-preview-tts,gemini-3.8-flash-tts"
    ).split(",") if m.strip()
]
GEMINI_TTS_VOZ = os.environ.get("GEMINI_TTS_VOICE", "Charon")  # alternativas: Puck, Fenrir, Orus...
_INSTRUCCION = "Narra en español de España con ritmo ágil y natural, sin pausas largas: "


def _claves_gemini() -> list[str]:
    return [k for k in (os.environ.get("GEMINI_API_KEY"), os.environ.get("GEMINI_API_KEY_2")) if k]


def _espera_429(respuesta, intento: int) -> float:
    """Segundos a esperar tras un 429: usa el retryDelay que indica la API; si no, backoff."""
    try:
        for d in respuesta.json()["error"].get("details", []):
            m = re.match(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")))
            if m:
                return min(float(m.group(1)) + 1, 45)
    except Exception:
        pass
    return min(10 * intento, 40)


def generar_gemini_tts(texto: str, destino_mp3: str) -> None:
    claves = _claves_gemini()
    if not claves:
        raise RuntimeError("Falta GEMINI_API_KEY para Gemini TTS")
    palabras = max(1, len(texto.split()))
    ultimo: Exception | None = None
    for modelo in GEMINI_TTS_MODELOS:
        for clave in claves:
            for intento in (1, 2, 3, 4):
                try:
                    r = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                        params={"key": clave},
                        json={
                            "contents": [{"parts": [{"text": _INSTRUCCION + texto}]}],
                            "generationConfig": {
                                "responseModalities": ["AUDIO"],
                                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOZ}}},
                            },
                        },
                        timeout=90,
                    )
                    if r.status_code == 429 and "PerDay" in r.text:
                        # Cupo DIARIO del tier gratuito agotado para este modelo/proyecto: esperar no sirve.
                        raise RuntimeError(f"{modelo}: cupo diario agotado")
                    if r.status_code in (429, 503):
                        espera = _espera_429(r, intento)
                        print(f"[voz_utils] Gemini TTS ({modelo}) HTTP {r.status_code}: espero {espera:.0f} s y reintento")
                        time.sleep(espera)
                        raise RuntimeError(f"__reintentar__ {modelo} HTTP {r.status_code}")
                    if r.status_code != 200:
                        raise RuntimeError(f"{modelo} HTTP {r.status_code}: {r.text[:160]}")
                    parte = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                    datos = base64.b64decode(parte["data"])
                    mime = parte.get("mimeType", "")
                    bruto = destino_mp3 + ".gem"
                    with open(bruto, "wb") as f:
                        f.write(datos)
                    try:
                        if "wav" in mime:
                            entrada = ["-i", bruto]
                        else:  # PCM crudo, p. ej. "audio/L16;codec=pcm;rate=24000"
                            m = re.search(r"rate=(\d+)", mime)
                            entrada = ["-f", "s16le", "-ar", m.group(1) if m else "24000", "-ac", "1", "-i", bruto]
                        subprocess.run(["ffmpeg", "-y", *entrada, "-codec:a", "libmp3lame", "-q:a", "3", destino_mp3],
                                       check=True, capture_output=True)
                    finally:
                        os.remove(bruto)
                    seg = _duracion(destino_mp3)
                    # Protección: si el modelo lee la instrucción o se atasca, la duración se dispara.
                    if not (0.18 <= seg / palabras <= 0.75):
                        raise RuntimeError(f"{modelo}: duración anómala ({seg:.1f} s para {palabras} palabras)")
                    return
                except Exception as e:
                    ultimo = e
                    if str(e).startswith("__reintentar__"):
                        continue  # ya se esperó; se vuelve a intentar el MISMO modelo
                    print(f"[voz_utils] Gemini TTS ({modelo}) intento {intento} falló: {e}")
                    break
    raise ultimo or RuntimeError("Gemini TTS no disponible")
