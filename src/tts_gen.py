"""Genera la narración en audio con edge-tts (gratis, sin API key)."""
import asyncio

import edge_tts

VOZ = "es-ES-AlvaroNeural"


async def _generar(texto: str, destino: str) -> None:
    comunicador = edge_tts.Communicate(texto, VOZ)
    await comunicador.save(destino)


def generar_audio(texto: str, destino: str) -> None:
    asyncio.run(_generar(texto, destino))
