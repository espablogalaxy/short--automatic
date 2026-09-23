# Shorts Bot Gratis — pipeline automático de YouTube Shorts sin servidor propio

Este proyecto ejecuta todo el pipeline (guion → imágenes → voz → vídeo → subida) usando
**GitHub Actions** como "ordenador siempre encendido" gratuito. No necesitas Raspberry Pi
ni PC encendido 24/7.

## 0. Coste real: por qué es gratis

| Etapa | Herramienta | Coste |
|---|---|---|
| Orquestación / cron | GitHub Actions | Gratis (repo público = minutos ilimitados; repo privado = 2.000 min/mes gratis) |
| Guion (LLM) | Google Gemini API (free tier) | Gratis dentro de cuota diaria |
| Imágenes | Pollinations.ai (sin cuenta) + Cloudflare Workers AI (free tier) como opción extra | Gratis |
| Voz (TTS) | edge-tts | Gratis, sin cuenta |
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
- **Cloudflare** (opcional, solo si quiere Workers AI además de Pollinations) →
  necesitarás `CF_ACCOUNT_ID` y `CF_API_TOKEN`.
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
- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`
- `CF_ACCOUNT_ID` (opcional)
- `CF_API_TOKEN` (opcional)

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

- Ejecutarse automáticamente cada día a las 09:00 y 18:00 UTC.
- Poder lanzarse a mano desde la pestaña **Actions → Run workflow** (útil para probar).
- Instalar Python, FFmpeg y las dependencias, ejecutar `src/main.py`, y hacer commit
  de vuelta al repo del guion ya usado (para no repetirlo) y de cualquier log.

No tienes que tocar nada más: en cuanto el repo esté en GitHub con los secrets puestos,
ya funciona solo.

## 7. Límites a tener en cuenta (para que no falle silenciosamente)

- **Cron de GitHub Actions**: en repos poco activos puede haber unos minutos de
  retraso respecto a la hora exacta. Si el repo lleva 60 días sin actividad, GitHub
  puede desactivar los workflows programados — un commit ocasional lo evita.
- **Cuota de Gemini free tier**: si se agota el día, el script debe manejar el error
  y no reintentar en bucle (el `guion_gen.py` incluido ya controla esto).
- **Cuota de subida de YouTube**: 10.000 unidades/día, ~6 subidas/día máximo. Para 1-2
  shorts diarios no hay problema.
- **Repo público**: el código es visible, pero los *secrets* nunca se exponen. Aun así,
  no metas guiones o contenido que no quieras público en un repo público.

## 8. Estructura de archivos

```
.github/workflows/daily_run.yml   # el "cron" que sustituye a la Raspberry Pi
src/guion_gen.py                  # genera título/descripción/escenas con Gemini
src/image_gen.py                  # genera imágenes (Pollinations + Cloudflare opcional)
src/tts_gen.py                    # narración con edge-tts
src/render.py                     # monta el vídeo final con FFmpeg
src/upload_youtube.py             # sube el corto a YouTube
src/main.py                       # orquesta todo el pipeline
src/generar_refresh_token.py      # script de un solo uso (paso 3)
content/pending/                  # guiones generados, pendientes de producir
content/done/                     # guiones ya publicados
requirements.txt
```
