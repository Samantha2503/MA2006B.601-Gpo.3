from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# Cargar autenticación
gauth = GoogleAuth()
gauth.LoadCredentialsFile("mycreds.txt")
if gauth.credentials is None:
    gauth.LocalWebserverAuth()
    gauth.SaveCredentialsFile("mycreds.txt")
elif gauth.access_token_expired:
    gauth.Refresh()
else:
    gauth.Authorize()

# Obtener información del usuario autenticado
import requests

access_token = gauth.credentials.access_token
user_info = requests.get(
    "https://www.googleapis.com/oauth2/v1/userinfo",
    params={"access_token": access_token}
).json()

print("📧 Correo autenticado:", user_info.get("email"))
