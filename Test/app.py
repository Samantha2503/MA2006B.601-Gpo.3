import streamlit as st
from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import tempfile


# Cargar variables de entorno
load_dotenv()

# Configuración
UPLOAD_FOLDER = tempfile.gettempdir()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Obtener la clave de encriptación desde las variables de entorno
key = os.getenv("ENCRYPTION_KEY").encode()
fernet = Fernet(key)

# Función para encriptar el archivo
def encrypt_file(file_bytes, filename):
    encrypted = fernet.encrypt(file_bytes)
    encrypted_path = os.path.join(UPLOAD_FOLDER, filename + ".enc")
    with open(encrypted_path, "wb") as f:
        f.write(encrypted)
    return encrypted_path

# Función para enviar el correo con el archivo adjunto
def send_email_smtp(attachment_path):
    # Obtener las credenciales del archivo .env
    from_addr = 'equipocripto2@gmail.com'
    to_addr = 'josedavidbanda8@gmail.com'
    password = 'cpps wggr xixm nins'
    smtp_server = 'smtp.gmail.com'
    smtp_port_str = 587

   

    # Crear el mensaje de correo
    msg = MIMEMultipart()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = "📧 Archivo Encriptado desde Streamlit"

    part = MIMEBase('application', "octet-stream")
    with open(attachment_path, "rb") as file:
        part.set_payload(file.read())

    encoders.encode_base64(part)
    part.add_header('Content-Disposition',
                    f'attachment; filename="{os.path.basename(attachment_path)}"')
    msg.attach(part)

    try:
        # Conectar al servidor SMTP y enviar el correo
        with smtplib.SMTP(smtp_server, smtp_port_str) as server:
            server.starttls()  # Conexión segura
            server.login(from_addr, password)  # Iniciar sesión
            server.send_message(msg)  # Enviar mensaje
            print("Correo enviado con éxito.")
    except Exception as e:
        raise Exception(f"Error al enviar el correo: {e}")

# Streamlit UI
st.set_page_config(page_title="Drop & Send", page_icon="📨")
st.title("📂 Drop & Send")
st.markdown("Subí un archivo. Se encriptará y se enviará automáticamente por correo.")

uploaded_file = st.file_uploader("Arrastrá tu archivo aquí", type=None)

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name

    st.success(f"Archivo recibido: `{filename}`")

    encrypted_path = encrypt_file(file_bytes, filename)
    st.info("🔐 Archivo encriptado correctamente.")

    try:
        send_email_smtp(encrypted_path)
        st.success("📨 ¡Correo enviado exitosamente!")
    except Exception as e:
        st.error(f"❌ Error al enviar el correo: {e}")
