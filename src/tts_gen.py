"""Genera la narración en audio.

gTTS (Google Translate TTS) como motor principal: es HTTP simple y no depende
del endpoint no oficial de WebSocket de Bing, que Microsoft está cortando (403)
desde IPs de datacenter como las de los runners de GitHub Actions.

edge-tts se mantiene como fallback con reintentos, por si algún día vuelve a
funcionar de forma fiable en CI o si gTTS falla puntualmente.
"""
import asyncio
import time

VOZ_EDGE = "es-ES-AlvaroNeural"


def _generar_gtts(texto: str, destino: str) -> None:
    from gtts import gTTS

    tts = gTTS(text=texto, lang="es", tld="es")
    tts.save(destino)


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


def generar_audio(texto: str, destino: str) -> None:
    try:
        _generar_gtts(texto, destino)
        return
    except Exception as e:
        print(f"gTTS falló ({e}), probando edge-tts como respaldo...")

    _generar_edge_con_reintentos(texto, destino)
