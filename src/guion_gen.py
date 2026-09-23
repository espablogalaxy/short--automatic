"""Genera título, descripción y escenas de un short usando la API gratuita de Gemini."""
import json
import os
import sys

import google.generativeai as genai

PROMPT_SISTEMA = """
Eres guionista de un canal de YouTube Shorts en español sobre curiosidades de
informática y tecnología. Responde SOLO con un JSON válido, sin texto adicional,
con esta forma exacta:

{
  "titulo": "...",
  "descripcion": "...",
  "escenas": [
    {"texto": "...", "prompt_imagen": "..."},
    ...
  ]
}

Reglas:
1. Usa tildes y la letra ñ correctamente en "titulo", "descripcion" y "texto".
2. Entre 5 y 8 escenas, cada "texto" es una frase corta para narrar en voz alta.
3. "prompt_imagen" debe ser una descripción literal y concreta de lo que se ve,
   sin metáforas abstractas (nada de "ondas de energía" o "partículas digitales").
4. El gancho inicial (primera escena) debe incluir un dato concreto y específico
   (un número, un nombre propio o un año), no una afirmación genérica de "truco".
"""


def generar_guion(tema: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno GEMINI_API_KEY")

    genai.configure(api_key=api_key)
    modelo = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=PROMPT_SISTEMA,
    )

    try:
        respuesta = modelo.generate_content(f"Tema: {tema}")
    except Exception as e:
        # Si se agota la cuota gratuita diaria, fallamos de forma controlada
        # en vez de reintentar en bucle.
        print(f"Error llamando a Gemini (¿cuota agotada?): {e}", file=sys.stderr)
        raise

    texto = respuesta.text.strip()
    texto = texto.removeprefix("```json").removesuffix("```").strip()
    return json.loads(texto)


if __name__ == "__main__":
    tema = sys.argv[1] if len(sys.argv) > 1 else "curiosidad de historia de la informática"
    guion = generar_guion(tema)
    print(json.dumps(guion, ensure_ascii=False, indent=2))
