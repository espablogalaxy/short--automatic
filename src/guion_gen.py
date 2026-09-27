"""Genera título, descripción y escenas de un short. Intenta primero con la API
gratuita de Gemini, y si falla (por ejemplo, cuota diaria agotada), usa Groq
(Llama 3.3 70B) como respaldo automático."""
import json
import os
import sys

import requests
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


def _limpiar_json(texto: str) -> dict:
    texto = texto.strip()
    texto = texto.removeprefix("```json").removesuffix("```").strip()
    return json.loads(texto)


def _generar_con_gemini(tema: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno GEMINI_API_KEY")

    genai.configure(api_key=api_key)
    modelo = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=PROMPT_SISTEMA,
    )
    respuesta = modelo.generate_content(f"Tema: {tema}")
    return _limpiar_json(respuesta.text)


def _generar_con_groq(tema: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno GROQ_API_KEY")

    respuesta = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": f"Tema: {tema}"},
            ],
        },
        timeout=60,
    )
    respuesta.raise_for_status()
    texto = respuesta.json()["choices"][0]["message"]["content"]
    return _limpiar_json(texto)


def generar_guion(tema: str) -> dict:
    """Prueba primero Gemini; si falla por cualquier motivo (cuota agotada,
    error de red, etc.), reintenta con Groq como respaldo antes de rendirse."""
    try:
        return _generar_con_gemini(tema)
    except Exception as e:
        print(f"Gemini falló (¿cuota agotada?): {e}. Probando con Groq...", file=sys.stderr)

    try:
        return _generar_con_groq(tema)
    except Exception as e:
        print(f"Groq también falló: {e}", file=sys.stderr)
        raise RuntimeError("No se pudo generar el guion: fallaron Gemini y Groq")


if __name__ == "__main__":
    tema = sys.argv[1] if len(sys.argv) > 1 else "curiosidad de historia de la informática"
    guion = generar_guion(tema)
    print(json.dumps(guion, ensure_ascii=False, indent=2))
