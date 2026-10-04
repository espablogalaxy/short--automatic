"""Generador de guiones para el canal (curiosidades verificables del planeta Tierra).

Mejoras portadas del canal de la Raspberry Pi (medidas con datos reales de ese canal):
  - Duración corta: 8 escenas de 4-7 palabras, 48-64 palabras en total (~20-25 s).
    En la Pi los shorts de 20-24 s tienen mediana ~1200 vistas; los de 40+ s, ~100.
  - Especificidad obligatoria (número, nombre propio, año) en título y gancho.
  - Gancho + hueco de curiosidad + cierre en bucle.
  - Prompts de imagen LITERALES (nada de metáforas abstractas).
  - Antiduplicados por código (src/dedup.py) y bucle de feedback con vistas
    reales del canal (src/metricas.py).
  - Red de seguridad de tildes/ñ y validación estricta con reintentos.
  - Cadena de proveedores: Gemini -> Groq -> Groq (2ª cuenta, opcional).
"""
import json
import os
import random
import re
import sys
import time

import requests

import dedup


class GuionGenError(Exception):
    pass


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

MODO_LUGAR = """Genera un guion de un Short de 20-25 segundos sobre UN lugar extremo o extraordinario REAL del planeta Tierra (un desierto, una fosa, un volcán, una cueva, un lago, una isla, un glaciar, una selva...).

1. El dato central tiene que ser VERIFICABLE y bien documentado (nada inventado, nada que suene a leyenda urbana sin confirmar).
1b. Apóyate en una CIFRA EXACTA y comprobable (profundidad en metros, temperatura, altura, año de descubrimiento, número de especies...) y en el nombre propio del lugar."""

MODO_FENOMENO = """Genera un guion de un Short de 20-25 segundos sobre UN fenómeno natural o científico REAL de la Tierra (por qué ocurre algo, cómo se formó algo, qué lo causa) explicado de forma sorprendente.

1. La explicación tiene que ser CIENTÍFICAMENTE CORRECTA y bien documentada (nada inventado, nada especulativo presentado como hecho).
1b. Apóyate en un NOMBRE propio, un AÑO o una CIFRA concreta (quién lo descubrió, cuándo, cuánto mide, cuánto dura)."""

MODO_RECORD = """Genera un guion de un Short de 20-25 segundos sobre UN récord o comparación REAL del planeta (lo más grande, profundo, antiguo, seco, caliente, frío o aislado de la Tierra) con una comparación que se entienda al instante.

1. El récord tiene que ser VERIFICABLE y estar vigente según fuentes fiables (nada dudoso).
1b. Incluye la CIFRA exacta y una comparación cotidiana (por ejemplo, cuántas veces cabría algo conocido dentro)."""

_MODOS = [MODO_LUGAR, MODO_FENOMENO, MODO_LUGAR, MODO_RECORD, MODO_FENOMENO, MODO_LUGAR]

# Categorías solo como pista de variedad (NO son temas cerrados: el modelo elige el tema).
CATEGORIAS = [
    "desiertos y lugares secos", "océanos y fosas abisales", "volcanes y lava", "cuevas y minerales",
    "glaciares y hielo", "selvas y ríos extremos", "islas aisladas", "fenómenos del cielo y la atmósfera",
    "lagos con colores o propiedades raras", "geología y placas tectónicas", "animales y plantas extremos",
    "ciudades y lugares habitados más extremos", "sonidos, luces y misterios científicos de la Tierra",
    "cráteres, meteoritos e impactos", "récords de la Tierra vistos desde el espacio",
]

PROMPT_SISTEMA = """Eres un guionista experto en curiosidades del planeta Tierra para YouTube Shorts en español de España, y también experto en retención de audiencia y crecimiento en Shorts.

{modo_instruccion}
{pista_categoria}
2. NO repitas ninguno de estos temas ya usados (ni los reformules con otro título): {temas_usados}
3. Exactamente 8 escenas (más escenas y más cortas = más cortes de imagen por segundo, lo que mejora la retención).
4. GANCHO OBLIGATORIO: el "texto" de la escena 1 tiene que retener al espectador en el primer segundo: una pregunta intrigante o una afirmación sorprendente con un dato concreto. PROHIBIDO empezar con "Hoy te cuento...", "Sabías que..." o "Esta es la historia de...".
4b. HUECO DE CURIOSIDAD: el gancho plantea una intriga que NO se resuelve del todo hasta las últimas 2 escenas. No reveles el dato más sorprendente en las escenas 1-2.
4c. CIERRE EN BUCLE: la última escena debe conectar con el gancho inicial (retomar la misma pregunta o imagen) para que el vídeo se pueda volver a ver sin sensación de corte. Nunca cierres con un "Y así es como funciona" plano.
4d. ESPECIFICIDAD OBLIGATORIA: título y gancho deben apoyarse en un elemento MUY concreto y verificable (cifra exacta, nombre propio, año). PROHIBIDO títulos genéricos tipo "El misterio de los océanos" o "Un lugar increíble".
5. Cada escena: "texto" (voz en off, entre 4 y 7 palabras: frases CORTAS y directas) y "prompt_imagen". LONGITUD TOTAL OBLIGATORIA: entre 48 y 64 palabras sumando las 8 escenas (unos 20-25 segundos). Los datos reales de nuestros canales muestran que la duración es el factor más fuerte: los shorts de 20-24 s rinden varias veces más que los de 40+ s. Elimina todo relleno: cada frase aporta un dato.
   El "prompt_imagen" debe representar LITERALMENTE lo que dice el "texto" de esa escena (si habla del lago Hillier, el prompt describe un lago de agua rosa visto desde el aire). PROHIBIDO metáforas visuales abstractas (orbes de luz, ondas de energía, partículas, hologramas, engranajes...). Estilo: FOTOGRAFÍA HIPERREALISTA de reportaje/cine con lugares, paisajes y objetos reconocibles, iluminación dramática, profundidad de campo realista, sin texto ni logotipos, sin personas famosas.
5b. En el "texto" hablado NUNCA pongas códigos, URLs ni símbolos raros: la voz sintética los deletrea y descuadra la duración. Escribe los números de forma natural.
6. El "titulo" (máximo 60 caracteres) en formato de PREGUNTA DIRECTA o EXCLAMACIÓN de impacto con el dato concreto, no descriptivo ni neutro, sin clickbait falso ni exagerar el dato.
7. La "descripcion" lleva 1-2 frases de contexto y entre 5 y 8 hashtags: los fijos #shorts #curiosidades #planeta más 2-5 específicos de ESTE tema.
8. "tags": entre 8 y 12 palabras clave de SEO relevantes para ESTE short (mezcla genéricas y específicas).
9. Ortografía española correcta: tildes (á, é, í, ó, ú) y ñ donde corresponda en "titulo", "descripcion" y "texto".
10. Responde EXCLUSIVAMENTE con un JSON válido, sin texto antes ni después, con este formato exacto:

{{
  "titulo": "...",
  "descripcion": "Descripción corta con hashtags.",
  "tags": ["...", "..."],
  "escenas": [
    {{"texto": "...", "prompt_imagen": "..."}}
  ]
}}
"""

# Palabras sin ambigüedad que el modelo a veces escribe sin tilde/ñ (solo titulo/descripcion/texto).
_CORRECCIONES_ACENTOS = {
    "anos": "años", "ano": "año", "dia": "día", "dias": "días",
    "tecnologia": "tecnología", "numero": "número", "numeros": "números",
    "codigo": "código", "basico": "básico", "unico": "único", "unica": "única",
    "espanol": "español", "pequeno": "pequeño", "pequena": "pequeña",
    "diseno": "diseño", "extrano": "extraño", "extrana": "extraña",
    "maquina": "máquina", "ocean": "océano", "oceano": "océano", "oceanos": "océanos",
    "volcan": "volcán", "crater": "cráter", "magnetico": "magnético", "magnetica": "magnética",
    "atlantico": "Atlántico", "pacifico": "Pacífico", "ultimo": "último", "ultima": "última",
}
_PATRON_CORRECCIONES = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in _CORRECCIONES_ACENTOS) + r")\b", re.IGNORECASE
)


def _corregir_acentos(texto):
    def _r(m):
        original = m.group(0)
        c = _CORRECCIONES_ACENTOS[original.lower()]
        if original.isupper() and len(original) > 1:
            return c.upper()
        if original[0].isupper():
            return c[0].upper() + c[1:]
        return c
    return _PATRON_CORRECCIONES.sub(_r, texto)


def _corregir_acentos_guion(guion):
    guion["titulo"] = _corregir_acentos(guion["titulo"])
    guion["descripcion"] = _corregir_acentos(guion["descripcion"])
    for e in guion["escenas"]:
        e["texto"] = _corregir_acentos(e["texto"])
    return guion


def _llamar_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GuionGenError("Falta GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    r = requests.post(
        url, params={"key": key},
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.9}},
        timeout=60,
    )
    if r.status_code != 200:
        raise GuionGenError(f"Gemini error {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise GuionGenError(f"Respuesta de Gemini sin texto útil: {str(r.json())[:200]}")


def _llamar_groq_con(env_key):
    def _f(prompt):
        key = os.environ.get(env_key)
        if not key:
            raise GuionGenError(f"Falta {env_key}")
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.9},
            timeout=60,
        )
        if r.status_code != 200:
            raise GuionGenError(f"Groq ({env_key}) error {r.status_code}: {r.text[:200]}")
        try:
            return r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise GuionGenError(f"Respuesta de Groq sin texto útil: {str(r.json())[:200]}")
    return _f


def _proveedores():
    prov = [("gemini", _llamar_gemini)]
    if os.environ.get("GROQ_API_KEY"):
        prov.append(("groq", _llamar_groq_con("GROQ_API_KEY")))
    if os.environ.get("GROQ_API_KEY_2"):
        prov.append(("groq2", _llamar_groq_con("GROQ_API_KEY_2")))
    return prov


def _extraer_json(texto):
    m = re.search(r"\{.*\}", texto.strip(), re.DOTALL)
    if not m:
        raise GuionGenError(f"No se encontró JSON: {texto[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise GuionGenError(f"JSON inválido: {e}")


def palabras_totales(guion):
    return sum(len(e["texto"].split()) for e in guion["escenas"])


def _validar_guion(guion):
    for c in ("titulo", "descripcion", "tags", "escenas"):
        if c not in guion:
            raise GuionGenError(f"Falta el campo {c}")
    if not isinstance(guion["escenas"], list) or len(guion["escenas"]) != 8:
        raise GuionGenError(f"Se esperaban 8 escenas, hay {len(guion.get('escenas', []))}")
    for i, e in enumerate(guion["escenas"]):
        if not e.get("texto") or not e.get("prompt_imagen"):
            raise GuionGenError(f"Escena {i} incompleta")
        if re.search(r"https?://|www\.|[{}_<>]", e["texto"]):
            raise GuionGenError(f"Escena {i}: el texto hablado contiene código/URL")
    n = palabras_totales(guion)
    # segundos ~ 4.5 + 0.31 * palabras (medido en la Pi): >70 palabras supera ~26 s.
    if n > 70 or n < 38:
        raise GuionGenError(f"{n} palabras en total (debe haber entre 38 y 70 para ~20-26 s)")
    if not isinstance(guion["tags"], list) or not guion["tags"]:
        guion["tags"] = []
    if len(guion["titulo"]) > 100:
        raise GuionGenError("Título de más de 100 caracteres")


def _temas_usados(corpus, limite=120):
    titulos = [e["titulo"] for e in corpus]
    return titulos[-limite:]


def generar_guion(tema=None, max_intentos=3, corpus=None):
    """Genera un guion válido y NO duplicado. `tema` es opcional (si se omite, el modelo
    elige un tema nuevo de una categoría aleatoria). Lanza GuionGenError si no lo logra."""
    if corpus is None:
        corpus = dedup.construir_corpus()
    usados = _temas_usados(corpus)
    modo = _MODOS[len(corpus) % len(_MODOS)]
    try:
        import metricas
        modo += metricas.bloque_prompt()
    except Exception as e:  # sin datos o sin red: se genera igualmente
        print(f"[guion_gen] sin métricas ({e})", file=sys.stderr)

    if tema:
        pista = f"TEMA OBLIGATORIO: {tema}"
    else:
        pista = f"Categoría de partida para variar (elige tú un tema NUEVO dentro de ella): {random.choice(CATEGORIAS)}"

    extra_prohibidos = []
    ultimo_error = None
    for ronda in range(1, 4):  # rondas anti-duplicado
        prompt = PROMPT_SISTEMA.format(
            modo_instruccion=modo,
            pista_categoria=pista,
            temas_usados="; ".join(usados + extra_prohibidos) if (usados or extra_prohibidos) else "(ninguno todavía)",
        )
        guion = None
        for nombre, llamar in _proveedores():
            for intento in range(1, max_intentos + 1):
                try:
                    g = _extraer_json(llamar(prompt))
                    _validar_guion(g)
                    guion = _corregir_acentos_guion(g)
                    if nombre != "gemini":
                        print(f"[guion_gen] generado con proveedor de respaldo: {nombre}")
                    break
                except GuionGenError as e:
                    ultimo_error = e
                    print(f"[guion_gen] {nombre} intento {intento}/{max_intentos} falló: {e}", file=sys.stderr)
                    if "503" in str(e) or "429" in str(e):
                        time.sleep(4 * intento)
                except requests.RequestException as e:
                    ultimo_error = e
                    print(f"[guion_gen] {nombre} error de red: {e}", file=sys.stderr)
                    break
            if guion:
                break
        if not guion:
            raise GuionGenError(f"Ningún proveedor generó un guion válido: {ultimo_error}")
        dup = dedup.buscar_duplicado(guion, corpus)
        if not dup:
            return guion
        print(f"[guion_gen] ronda {ronda}: repite tema ({dup[1]}), regenerando", file=sys.stderr)
        extra_prohibidos.append(guion["titulo"])
        if tema:
            tema = None
            pista = f"Categoría de partida para variar: {random.choice(CATEGORIAS)}"
    raise GuionGenError("No se consiguió un tema nuevo tras 3 rondas anti-duplicado")


if __name__ == "__main__":
    g = generar_guion(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(g, ensure_ascii=False, indent=2))
