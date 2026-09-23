"""Sube el short a YouTube usando las credenciales OAuth guardadas como secrets.
No requiere abrir navegador: usa el refresh_token generado una sola vez en local."""
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def _credenciales() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )


def subir_short(ruta_video: str, titulo: str, descripcion: str) -> str:
    youtube = build("youtube", "v3", credentials=_credenciales())

    cuerpo = {
        "snippet": {
            "title": titulo,
            "description": descripcion,
            "categoryId": "28",  # Ciencia y tecnología
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }

    media = MediaFileUpload(ruta_video, chunksize=-1, resumable=True)
    peticion = youtube.videos().insert(part="snippet,status", body=cuerpo, media_body=media)
    respuesta = peticion.execute()
    video_id = respuesta["id"]
    return f"https://youtube.com/shorts/{video_id}"
