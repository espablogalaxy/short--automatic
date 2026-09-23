"""Ejecutar UNA VEZ en tu propio ordenador (no en GitHub Actions).
Abre el navegador, pide autorizar el canal, e imprime el refresh_token
que hay que guardar como secret YT_REFRESH_TOKEN en GitHub."""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

if __name__ == "__main__":
    # client_secret.json es el archivo descargado en Google Cloud Console (paso 2 del README)
    flujo = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    credenciales = flujo.run_local_server(port=0)
    print("\nGuarda estos valores como Secrets en GitHub:\n")
    print(f"YT_CLIENT_ID={credenciales.client_id}")
    print(f"YT_CLIENT_SECRET={credenciales.client_secret}")
    print(f"YT_REFRESH_TOKEN={credenciales.refresh_token}")
