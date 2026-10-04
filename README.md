# Shorts Bot Gratis — pipeline automático de YouTube Shorts sin servidor propio

Este proyecto ejecuta todo el pipeline (guion → imágenes → voz → vídeo con Ken Burns y
subtítulos animados → subida) usando **GitHub Actions** como "ordenador siempre
encendido" gratuito. No necesitas Raspberry Pi ni PC encendido 24/7.

Mismo enfoque visual que el canal de la Raspberry Pi (Soporte IT): imágenes
fotorrealistas, zoom Ken Burns por escena y subtítulos palabra a palabra tipo
"caption viral". Temática de este canal: curiosidades verificables del planeta Tierra.

## Mejoras portadas del canal de la Raspberry Pi (oct. 2026)

| Mejora | Dónde | Por qué |
|---|---|---|
| Shorts de ~20-25 s (8 escenas de 4-7 palabras, 48-64 palabras) | `guion_gen.py`, `cola_guiones.py` | En la Pi, 20-24 s ≈ 1200 vistas de mediana; 40+ s ≈ 100. La cola sube el guion más corto entre los 12 primeros |
| Especificidad obligatoria (cifra, nombre, año), gancho + hueco de curiosidad + cierre en bucle | `guion_gen.py` | Lo que separa los shorts con 1000+ vistas de los de <100 |
| Antiduplicados por código + carpeta `content/discarded/` | `dedup.py`, `limpiar_cola.py` | La cola tenía el mismo tema 5-7 veces (Hessdalen, Vredefort, Bloop...) |
| El modelo elige temas nuevos (ya no hay lista fija de 25) | `guion_gen.py`, `generar_lote.py` | La lista fija agotaba los temas y generaba repetidos |
| Cola con tope (`--min-cola 30`) | `generar_lote.py`, `rellenar_cola.yml` | Antes generaba 18 guiones/día y solo se publican 3 |
| Bucle de feedback con vistas reales | `metricas.py`, `metricas.yml` | Se inyectan en el prompt los títulos que mejor/peor rinden |
| Imagen en negro por moderación detectada + prompt suavizado + reutilizar imagen anterior en vez de abortar | `image_gen.py`, `main.py` | Un fallo en una escena tiraba el vídeo entero y el hueco del día |
| Voz neural con MeloTTS (Cloudflare) | `tts_gen.py` | StreamElements da 403 desde GitHub Actions: toda la narración caía a gTTS (robótica) |
| `containsSyntheticMedia`, tags, idioma y categoría 28 al subir | `upload_youtube.py` | Política de YouTube sobre imágenes realistas generadas con IA + SEO |
| Concurrencia única entre workflows | `.github/workflows/*.yml` | Evita carreras de push entre pipeline, cola y métricas |

## 0. Coste real: por qué es gratis

| Etapa | Herramienta | Coste |
|---|---|---|
| Orquestación / cron | GitHub Actions | Gratis (repo público = minutos ilimitados; repo privado = 2.000 min/mes gratis) |
| Guion (LLM) | Google Gemini API (free tier), con Groq (GPT-OSS 120B) como respaldo si se agota la cuota | Gratis |
| Imágenes | Cloudflare Workers AI (Stable Diffusion XL, free tier), con una segunda cuenta como respaldo | Gratis |
| Voz (TTS) | MeloTTS en Cloudflare Workers AI (voz neural en español, mismas credenciales que las imágenes), con StreamElements, gTTS+FFmpeg y edge-tts como fallback | Gratis (free tier) |
| Render de vídeo | FFmpeg (viene preinstalado en los runners de GitHub) | Gratis |
| Subida | YouTube Data API v3 | Gratis (cuota diaria de 10.000 unidades; cada subida cuesta 1.600 → hasta 6 vídeos/día) |

No hace falta tarjeta de crédito en ningún paso de esta lista.

## 1. Crear el repositorio

1. Crea un repo nuevo en GitHub. **Si puede ser público, mejor**: minutos de Actions
   ilimitados. Si necesita ser privado (por ejemplo para no exponer los guiones), los
   2.000 min/mes gratis son de sobra para 1-2 shorts diarios.
2. Sube esta carpeta tal cual (mantén la estructura de `.github/workflows/`, `src/` y
   `content/`).

## 2. Crear las cuentas gratuitas necesarias

- **Google AI Studio** (https://aistudio.google.com) → genera una API key gratuita de
  Gemini. Guárdala para el paso 4.
- **Groq Console** (https://console.groq.com) → API key gratuita, respaldo del guion si
  Gemini se queda sin cuota diaria.
- **Cloudflare** → necesitarás `CF_ACCOUNT_ID` y `CF_API_TOKEN` (cuenta con Workers AI
  activado). Una segunda cuenta (`CF_ACCOUNT_ID_2`/`CF_API_TOKEN_2`) es opcional pero
  recomendada como respaldo si la principal se queda sin Neurons.
- **Google Cloud Console** → crea un proyecto, activa "YouTube Data API v3", crea
  credenciales OAuth 2.0 de tipo "Aplicación de escritorio". Descarga el
  `client_secret.json`.

## 3. Generar el refresh token de YouTube (solo se hace una vez, en tu propio PC)

GitHub Actions no puede abrir un navegador para el login de Google, así que este paso
se hace una vez en local y el resultado (el *refresh token*) se guarda como secreto.

```bash
pip install google-auth-oauthlib
python src/generar_refresh_token.py   # abrirá el navegador para autorizar tu canal
```

Al terminar, el script imprime un `refresh_token`. Guárdalo, junto con el `client_id`
y `client_secret` del JSON descargado en el paso 2.

## 4. Configurar los "Secrets" del repo

En GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
Crea estos secretos (nunca se ven en los logs ni aunque el repo sea público):

- `GEMINI_API_KEY`
- `GROQ_API_KEY` (respaldo del guion)
- `GROQ_API_KEY_2` (opcional, segunda cuenta de Groq como tercer respaldo)
- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`
- `CF_ACCOUNT_ID` / `CF_API_TOKEN` (obligatorios: Cloudflare es el único proveedor de imágenes)
- `CF_ACCOUNT_ID_2` / `CF_API_TOKEN_2` (opcionales, segunda cuenta de respaldo)

## 5. Probar en local (opcional pero recomendado)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=...   # exporta las mismas variables que en los secrets
python src/main.py --no-upload   # genera un vídeo de prueba sin subirlo
```

## 6. Activar el workflow

El archivo `.github/workflows/daily_run.yml` ya está configurado para:

- Ejecutarse automáticamente cada día a las 06:00, 09:00 y 18:00 UTC (la franja de las 12:00 UTC se retiró: mediana ~200 vistas frente a ~1000 en las otras; se revisa con `python src/metricas.py --informe`).
- Poder lanzarse a mano desde la pestaña **Actions → Run workflow** (útil para probar).
- Instalar Python, FFmpeg y las dependencias, ejecutar `src/main.py`, y hacer commit
  de vuelta al repo del guion ya usado (para no repetirlo) y de cualquier log.

No tienes que tocar nada más: en cuanto el repo esté en GitHub con los secrets puestos,
ya funciona solo.

## 7. Cola de guiones (`content/pending/` → `content/done/`)

Igual que el canal de la Pi, `main.py` no genera el guion siempre al vuelo:

- Si hay algún `.json` en `content/pending/`, coge el más corto de los 12 más antiguos
  (evitando repetir el formato de título de los 2 últimos subidos).
- Si la cola está vacía, genera uno nuevo con el LLM sobre un tema nuevo elegido por el
  modelo (sin repetir nada de `pending/`, `done/` ni `discarded/`).
- Al publicarse con éxito, el guion usado se mueve a `content/done/` (histórico,
  nunca se repite).
- `--tema "..."` se salta la cola y fuerza un guion nuevo sobre ese tema concreto.

Para tener una reserva de guiones ya escritos sin gastar cuota de imágenes/TTS/YouTube:

```bash
python src/generar_lote.py 10 --min-cola 30   # genera hasta 10 (solo si hay <30 pendientes)
python src/limpiar_cola.py [--aplicar]        # mueve a content/discarded/ los pendientes que repiten tema
python src/dedup.py --auditar                 # lista pares de guiones sospechosos de repetir tema
```

## 8. Límites a tener en cuenta (para que no falle silenciosamente)

- **Cron de GitHub Actions**: en repos poco activos puede haber unos minutos de
  retraso respecto a la hora exacta. Si el repo lleva 60 días sin actividad, GitHub
  puede desactivar los workflows programados — un commit ocasional lo evita.
- **Cuota de Gemini free tier**: si se agota el día, cae a Groq automáticamente.
- **Cuota/Neurons de Cloudflare Workers AI**: si la cuenta principal se queda sin
  cuota (402/429), cae a la segunda cuenta si está configurada.
- **Cuota de subida de YouTube**: 10.000 unidades/día, ~6 subidas/día máximo. Para 1-2
  shorts diarios no hay problema.
- **Repo público**: el código es visible, pero los *secrets* nunca se exponen. Aun así,
  no metas guiones o contenido que no quieras público en un repo público.

## 9. Estructura de archivos

```
.github/workflows/daily_run.yml   # el "cron" que sustituye a la Raspberry Pi
.github/workflows/rellenar_cola.yml  # mantiene la cola de guiones (tope 30)
.github/workflows/metricas.yml    # lee las vistas a diario y acumula el histórico
src/guion_gen.py                  # genera título/descripción/tags/escenas (Gemini, fallback Groq x2)
src/cola_guiones.py               # cola: pending/ -> done/ (y discarded/), elige el guion más corto
src/dedup.py                      # detecta temas repetidos por código
src/limpiar_cola.py               # descarta duplicados de la cola
src/metricas.py                   # vistas reales del canal (feed RSS) -> content/metricas.json
src/generar_lote.py               # prellena la cola de guiones sin producir vídeo
src/image_gen.py                  # genera imágenes fotorrealistas (Cloudflare Workers AI)
src/tts_gen.py                    # narración con MeloTTS/Cloudflare (fallback StreamElements, gTTS, edge-tts)
src/render.py                     # monta el vídeo final: Ken Burns + subtítulos .ass
src/upload_youtube.py             # sube el corto a YouTube
src/main.py                       # orquesta todo el pipeline
src/generar_refresh_token.py      # script de un solo uso (paso 3)
content/pending/                  # guiones generados, pendientes de producir
content/done/                     # guiones ya publicados
content/discarded/                # duplicados descartados (cuentan para el antiduplicado)
requirements.txt
```
