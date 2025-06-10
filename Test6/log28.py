import streamlit as st
import gnupg
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import os
import tempfile
import re
import mimetypes # For better file type detection
import sqlite3 # Import sqlite3
import platform 
import pandas as pd
import time

# Detecta el sistema operativo
system = platform.system()

# -------- GPG Setup --------
if system == "Windows":
    gpg_home_dir = os.path.expandvars(r"%APPDATA%\gnupg")
else:
    gpg_home_dir = os.path.expanduser("~/.gnupg")

if not os.path.exists(gpg_home_dir):
    try:
        os.makedirs(gpg_home_dir, mode=0o700, exist_ok=True)
        st.info(f"GPG homedir created at {gpg_home_dir}.")
    except Exception as e:
        st.error(f"Could not create GPG homedir at {gpg_home_dir}: {e}. Please create it manually with read/write permissions for your user.")
        st.stop()

try:
    gpg = gnupg.GPG(gnupghome=gpg_home_dir)
    st.sidebar.markdown("---")
    st.sidebar.subheader("GPG Debug Info")
    try:
        st.sidebar.write(f"GPG Binary Path: {gpg.gpgbinary}")
        st.sidebar.write(f"GPG Version: {gpg.version}")
        private_keys_count = len(gpg.list_keys(True))
        public_keys_count = len(gpg.list_keys())
        st.sidebar.write(f"Private Keys in keyring: {private_keys_count}")
        st.sidebar.write(f"Public Keys in keyring: {public_keys_count}")
    except Exception as e:
        st.sidebar.error(f"Error getting GPG info: {e}")
        st.error(f"Error initializing GPG or getting info: {e}. Ensure GnuPG is installed and 'gpg' is in your system's PATH, or specify 'gpgbinary' parameter.")
        st.stop()
    st.sidebar.markdown("---")

except Exception as e:
    st.error(f"Error initializing GPG: {e}. Please ensure GnuPG is installed and its executable is in your system's PATH, or provide the full path to 'gpg' executable in gnupg.GPG(gpgbinary='/path/to/gpg').")
    st.stop()


def is_valid_key(key):
    """Checks if a key is not expired."""
    now = datetime.now(timezone.utc).timestamp()
    return not key['expires'] or (key['expires'] and int(key['expires']) > now)

# -------- Google Drive setup --------
def init_drive():
    """Initializes Google Drive authentication."""
    gauth = GoogleAuth()
    try:
        gauth.LoadCredentialsFile("mycreds.txt")
    except Exception as e:
        pass

    if gauth.credentials is None:
        try:
            st.info("Necesitas autenticarte con Google Drive. Se abrirá una ventana del navegador.")
            gauth.LocalWebserverAuth()
        except Exception as e:
            st.error(f"Error durante la autenticación de Google Drive: {e}. Asegúrate de tener 'client_secrets.json' configurado correctamente.")
            st.stop()
    elif gauth.access_token_expired:
        try:
            gauth.Refresh()
        except Exception as e:
            st.error(f"Error al refrescar el token de Google Drive: {e}. Es posible que necesites reautenticar.")
            st.stop()
    else:
        gauth.Authorize()
    
    gauth.SaveCredentialsFile("mycreds.txt")
    return GoogleDrive(gauth)

def get_or_create_folder(drive, title, parent_id=None):
    """Gets a folder by title, or creates it if it doesn't exist."""
    query = f"title='{title}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    folders = drive.ListFile({'q': query}).GetList()
    if folders:
        return folders[0]['id']
    folder_metadata = {'title': title, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        folder_metadata['parents'] = [{'id': parent_id}]
    folder = drive.CreateFile(folder_metadata)
    folder.Upload()
    return folder['id']

def save_log_to_drive(drive, filename, content, area_destino, aceptado=True):
    """Saves a log file to a structured folder in Google Drive."""
    root_folder = "GPG_Email_Logs"
    area_folder = area_destino
    status_folder = "aceptado" if aceptado else "rechazado"

    try:
        root_id = get_or_create_folder(drive, root_folder)
        area_id = get_or_create_folder(drive, area_folder, root_id)
        status_id = get_or_create_folder(drive, status_folder, area_id)

        file = drive.CreateFile({'title': filename, 'parents': [{'id': status_id}]})
        file.SetContentString(content)
        file.Upload()
        return file['alternateLink']
    except Exception as e:
        st.error(f"Error al guardar el log en Google Drive: {e}")
        return None

# Initialize Google Drive if not already in session state
if "drive" not in st.session_state:
    st.session_state.drive = init_drive()

# -------- Email functions --------
def send_email_with_attachment(subject, body_text, from_addr, password, recipient_email, attachment_path=None, attachment_name=None):
    """Sends an email with optional attachment."""
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587

    msg = MIMEMultipart()
    msg['From'] = from_addr
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_text, "plain"))

    if attachment_path and os.path.exists(attachment_path):
        try:
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {attachment_name or os.path.basename(attachment_path)}",
            )
            msg.attach(part)
            st.info(f"Archivo '{attachment_name or os.path.basename(attachment_path)}' adjuntado al correo.")
        except Exception as e:
            st.warning(f"No se pudo adjuntar el archivo {attachment_name or attachment_path}: {e}. El correo se enviará sin adjunto.")
    else:
        st.info("No hay archivo adjunto o el archivo no existe en la ruta especificada.")


    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_addr, password)
            server.send_message(msg)
        return True, "✅ Correo enviado con éxito."
    except Exception as e:
        return False, f"❌ Error al enviar el correo: {e}"


# Renamed and modified function: No longer signs the email body
def forward_status_and_document(original_sender_email, body, subject, from_addr, password, attachment_path=None, attachment_name=None):
    """Forwards a message to the original sender with a status and an optional attachment.
    The email body itself is sent as plain text (not signed)."""
    
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587

    msg = MIMEMultipart()
    msg['From'] = from_addr
    msg['To'] = original_sender_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, "plain")) # Send body as plain text, no GPG signing here

    if attachment_path and os.path.exists(attachment_path):
        try:
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {attachment_name or os.path.basename(attachment_path)}",
            )
            msg.attach(part)
            st.info(f"Archivo '{attachment_name or os.path.basename(attachment_path)}' adjuntado al reenvío.")
        except Exception as e:
            st.warning(f"No se pudo adjuntar el archivo {attachment_name or attachment_path}: {e}. El correo se enviará sin adjunto.")

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_addr, password)
            server.send_message(msg)
        return True, f"✉️ Mensaje con estado reenviado a {original_sender_email}"
    except Exception as e:
        return False, f"❌ Error al reenviar: {e}"

# -------- Database functions --------
def crear_base_si_no_existe(db_path="firmas.db"):
    """Creates the SQLite database and tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        email TEXT UNIQUE NOT NULL,
        rol TEXT NOT NULL,
        area TEXT,
        contraseña TEXT,
        fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS claves_gpg (
        id_clave INTEGER PRIMARY KEY AUTOINCREMENT,
        id_usuario INTEGER NOT NULL,
        fingerprint TEXT NOT NULL,
        tipo TEXT CHECK(tipo IN ('publica', 'privada')) NOT NULL,
        FOREIGN KEY(id_usuario) REFERENCES usuarios(id_usuario)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interacciones (
        id_interaccion INTEGER PRIMARY KEY AUTOINCREMENT,
        id_emisor INTEGER NOT NULL,
        id_receptor INTEGER NOT NULL,
        asunto TEXT,
        mensaje TEXT,
        archivo_adjunto TEXT,
        area_destino TEXT,
        fecha_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
        aceptado BOOLEAN,
        fecha_respuesta DATETIME,
        FOREIGN KEY(id_emisor) REFERENCES usuarios(id_usuario),
        FOREIGN KEY(id_receptor) REFERENCES usuarios(id_usuario)
    );
    """)

    conn.commit()
    conn.close()


def obtener_id_usuario_por_email(email, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        # CORRECTED: Changed 'id' to 'id_usuario'
        cursor.execute("SELECT id_usuario FROM usuarios WHERE email = ?", (email,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        conn.close()

def obtener_datos_completos_por_nombre(nombre, db_path="firmas.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.email, c.fingerprint, u.area
        FROM usuarios u
        JOIN claves_gpg c ON u.id_usuario = c.id_usuario
        WHERE u.nombre = ? AND c.tipo = 'publica'
    """, (nombre,))
    result = cursor.fetchone()
    conn.close()
    return result if result else (None, None, None)

def registrar_usuario_si_no_existe(email, nombre="Usuario Auto", rol="usuario", area="Desconocida", contraseña="1234", db_path="firmas.db"):
    """Registers a user if they don't exist, or returns their ID."""
    usuario_id = obtener_id_usuario_por_email(email, db_path)
    if usuario_id is not None:
        return usuario_id

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO usuarios (nombre, email, rol, area, contraseña)
        VALUES (?, ?, ?, ?, ?)
    """, (nombre, email, rol, area, contraseña))
    conn.commit()

    cursor.execute("SELECT id_usuario FROM usuarios WHERE email = ?", (email,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def guardar_interaccion(db_path, id_emisor, id_receptor, asunto, mensaje_cifrado, link_archivo, area_destino, aceptado=None, fecha_respuesta=None):
    """Saves an interaction log to the database."""
    if id_emisor is None:
        raise ValueError("❌ id_emisor es None. Asegúrate de que el correo esté registrado.")
    if id_receptor is None:
        raise ValueError("❌ id_receptor es None. Asegúrate de que el destinatario esté registrado.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO interacciones (
            id_emisor, id_receptor, asunto, mensaje,
            archivo_adjunto, area_destino, fecha_envio, aceptado, fecha_respuesta
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        id_emisor, id_receptor, asunto, mensaje_cifrado,
        link_archivo, area_destino, datetime.now(), aceptado, fecha_respuesta
    ))
    conn.commit()
    conn.close()
    
TEMPLATES = {
    "Selecciona una plantilla": {"asunto": "", "cuerpo": ""},
    "Confirmación de entrega": {
        "asunto": "Confirmación de entrega de documentos",
        "cuerpo": "Hola {nombre},\n\nTe confirmamos que tu documento fue entregado el día {fecha} a las {hora}.\n\nSaludos,\nEquipo"
    },
    "Recordatorio de reunión": {
        "asunto": "Recordatorio de reunión",
        "cuerpo": "Hola {nombre},\n\nTe recordamos que tienes una reunión programada para el día {fecha} a las {hora}.\n\nGracias,\nCoordinación"
    }
}

# Initialize database if it doesn't exist
crear_base_si_no_existe()

# -------- Streamlit App Logic --------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'email' not in st.session_state:
    st.session_state.email = ""
if 'password' not in st.session_state:
    st.session_state.password = ""
if 'drive' not in st.session_state:
    st.session_state.drive = None
if 'gpg_passphrase' not in st.session_state:
    st.session_state.gpg_passphrase = ""

# New states for passing data between tabs
if 'decrypted_content_for_tab3' not in st.session_state:
    st.session_state.decrypted_content_for_tab3 = None
if 'decrypted_file_path_for_tab3' not in st.session_state:
    st.session_state.decrypted_file_path_for_tab3 = None
if 'decrypted_file_name_for_tab3' not in st.session_state:
    st.session_state.decrypted_file_name_for_tab3 = None
if 'original_sender_email_for_tab3' not in st.session_state:
    st.session_state.original_sender_email_for_tab3 = ""
if 'decryption_status_for_tab3' not in st.session_state:
    st.session_state.decryption_status_for_tab3 = ""
if 'verification_status_for_tab3' not in st.session_state:
    st.session_state.verification_status_for_tab3 = ""
if 'verified_sender_uid_for_tab3' not in st.session_state:
    st.session_state.verified_sender_uid_for_tab3 = "Desconocido"
if 'original_subject_for_tab3' not in st.session_state:
    st.session_state.original_subject_for_tab3 = ""


if not st.session_state.logged_in:
    st.title("📧 Login - Email Credentials")

    provider = st.selectbox("Email Provider", ["Gmail", "Outlook"])
    email = st.text_input("Email Address")
    password = st.text_input("App Password", type="password", help="Para Gmail, necesitas una contraseña de aplicación. Busca 'contraseña de aplicación' en la configuración de seguridad de tu cuenta de Google.")

    if st.button("Login"):
        try:
            if provider == "Gmail":
                smtp_server = "smtp.gmail.com"
                port = 587
            elif provider == "Outlook":
                smtp_server = "smtp.office365.com"
                port = 587
            else:
                st.error("Proveedor no soportado.")
                st.stop()

            with smtplib.SMTP(smtp_server, port) as server:
                server.starttls()
                server.login(email, password)

            st.success(f"✅ {provider} login exitoso. ¡Bienvenido!")
            st.session_state.logged_in = True
            st.session_state.email = email
            st.session_state.password = password
            st.session_state.drive = init_drive()
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error de login: {e}. Asegúrate de que la dirección de correo y la contraseña de aplicación son correctas, y que tu proveedor de correo permite conexiones SMTP.")

else: # User is logged in
    st.title("🔐 Secure GPG Email Tool")
    st.sidebar.text(f"Logged in as: {st.session_state.email}")

    tab1, tab2, tab3, tab4, tab_admin = st.tabs(["📤 Enviar mensaje cifrado", "📥 Desencriptar y verificar", "✅ Responder y reenviar", "⬇️ Descargar y ver documento", "⚙️ Administración"])

    def borrar_si_se_puede(ruta):
        time.sleep(0.5)
        try:
            os.remove(ruta)
        except PermissionError:
            st.warning(f"⚠️ No se pudo borrar el archivo temporal: {ruta}")


    with tab1:
        st.header("Enviar correo cifrado y firmado")

        all_private_keys = gpg.list_keys(True)
        valid_private_keys = [k for k in all_private_keys if is_valid_key(k)]
        all_public_keys = gpg.list_keys()
        valid_public_keys = [k for k in all_public_keys if is_valid_key(k)]

        if not valid_private_keys:
            st.warning("No hay **claves privadas** GPG válidas importadas. Necesitas una para firmar.")
            st.info("Para importar una clave privada, usa el comando `gpg --import tu_clave_privada.asc` en tu terminal.")
        if not valid_public_keys:
            st.warning("No hay **claves públicas** GPG válidas importadas. Necesitas una para cifrar.")
            st.info("Para importar una clave pública, usa el comando `gpg --import clave_publica_destinatario.asc` en tu terminal.")

        if valid_private_keys and valid_public_keys:
            signer_options = [f"{k['uids'][0]} [{k['fingerprint'][:8]}]" for k in valid_private_keys]
            recipient_options = [f"{k['uids'][0]} [{k['fingerprint'][:8]}]" for k in valid_public_keys]

            #signer_selection = st.selectbox("Firmar como (clave privada):", signer_options, help="Selecciona la clave privada GPG que usarás para firmar el mensaje y el archivo.")
            #recipient_selection = st.selectbox("Cifrar para (clave pública):", recipient_options, help="Selecciona la clave pública GPG del destinatario para cifrar el mensaje y el archivo.")

            # -------- INICIO DE SESIÓN --------
            signer_fpr = None
            for k in gpg.list_keys(True):  # True = claves privadas
                if any(st.session_state.email in uid for uid in k['uids']):
                    signer_fpr = k['fingerprint']
                    break

            if not signer_fpr:
                st.error("No se encontró una clave privada GPG vinculada a tu correo en GPG. Verifica que esté importada en tu sistema.")
                st.stop()

            gpg.default_key = signer_fpr

            gpg.default_key = signer_fpr

            
            gpg_passphrase = st.text_input(
                "Contraseña de tu clave GPG (si aplica):",
                type="password",
                help="Ingresa la contraseña de tu clave privada GPG. Si tu clave no tiene contraseña, déjalo en blanco. Si tu gpg-agent gestiona la contraseña, también puedes dejarlo en blanco."
            )
            st.session_state.gpg_passphrase = gpg_passphrase # Store passphrase in session state

            subject = st.text_input("Asunto")
            
            # -------- AUTOCOMPLETADO POR NOMBRE --------
            conn = sqlite3.connect("firmas.db")
            cursor = conn.cursor()
            cursor.execute("SELECT nombre FROM usuarios")
            nombres_disponibles = [r[0] for r in cursor.fetchall()]
            conn.close()

            nombres_seleccionados = st.multiselect("Selecciona destinatarios por nombre:", nombres_disponibles)

            def obtener_datos_completos(nombre):
                conn = sqlite3.connect("firmas.db")
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT u.email, u.area, cg.fingerprint
                    FROM usuarios u
                    LEFT JOIN claves_gpg cg ON u.id_usuario = cg.id_usuario AND cg.tipo = 'publica'
                    WHERE u.nombre = ?
                    LIMIT 1
                """, (nombre,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return row[0], row[1], row[2]
                return None, None, None

            datos_destinatarios = []
            for nombre in nombres_seleccionados:
                correo, area, fpr = obtener_datos_completos(nombre)
                if correo and area and fpr:
                    datos_destinatarios.append({
                        "nombre": nombre,
                        "correo": correo,
                        "area": area,
                        "fingerprint": fpr
            })
            recipients_fprs = [d["fingerprint"] for d in datos_destinatarios]



            # Mostrar datos autocompletados
            if datos_destinatarios:
                st.markdown("### ✉️ Destinatarios seleccionados:")
                for d in datos_destinatarios:
                    st.markdown(f"- **{d['nombre']}** ({d['correo']}) – Área: {d['area']}")


            #area_destino = st.selectbox("Área destino", ["Marketing", "Finanzas", "TI", "Recursos Humanos", "Legal", "Desconocida"])
            body = st.text_area("Cuerpo del mensaje")
            #recipient_email = st.text_input("Email destinatario")
            archivo = st.file_uploader("Sube un archivo")

            attachment_handling_choice = st.radio(
                "Manejo de Archivo Adjunto:",
                ("Cifrar y Firmar (privado)", "Solo Firmar (visible, autenticado)")
            )


            archivo_to_attach_path = None
            file_title_on_drive = None
            link_archivo = ""
            
            if st.button("Encrypt, Sign and Send"):
                if not subject or not body:
                    st.error("El asunto y el cuerpo del mensaje son obligatorios.")
                    st.stop()

                if not datos_destinatarios:
                    st.error("Selecciona al menos un destinatario válido con correo, área y clave pública.")
                    st.stop()

                else:
                    #signer_fpr = next((k['fingerprint'] for k in valid_private_keys if signer_selection.startswith(k['uids'][0])), None)
                    #recipient_fpr = next((k['fingerprint'] for k in valid_public_keys if recipient_selection.startswith(k['uids'][0])), None)

                    if not signer_fpr:
                        st.error("No se pudo encontrar la clave privada seleccionada para firmar.")
                        st.stop()
                    if not recipients_fprs:
                        st.error("No se pudo encontrar la clave pública seleccionada para cifrar.")
                        st.stop()

                    gpg.default_key = signer_fpr

                    encrypt_sign_kwargs = {
                        "recipients": recipients_fprs,
                        "sign": signer_fpr,
                        "always_trust": True,
                        "armor": True
                        #"encoding": "utf-8" # Ensure UTF-8 encoding for message body
                    }
                    if gpg_passphrase:
                        encrypt_sign_kwargs["passphrase"] = gpg_passphrase

                    encrypted_signed_body = gpg.encrypt(
                        body,
                        **encrypt_sign_kwargs
                    )

                    if not encrypted_signed_body.ok:
                        st.error(f"❌ Error al cifrar/firmar el cuerpo del mensaje: {encrypted_signed_body.stderr}")
                        if "bad passphrase" in encrypted_signed_body.stderr.lower():
                            st.info("La contraseña de GPG ingresada es incorrecta o es necesaria y no se proporcionó.")
                        st.stop()
                    else:
                        st.success("Cuerpo del mensaje cifrado y firmado.")

                        if archivo:
                            st.info("Procesando archivo adjunto...")
                            tmp_original_file_path = None
                            try:
                                with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp_file:
                                    tmp_file.write(archivo.getvalue())
                                    tmp_original_file_path = tmp_file.name

                                if attachment_handling_choice == "Cifrar y Firmar (privado)":
                                    file_sign_kwargs = {"keyid": signer_fpr, "detach": False} # Added encoding (, "encoding": "utf-8")
                                    if gpg_passphrase:
                                        file_sign_kwargs["passphrase"] = gpg_passphrase
                                    
                                    with open(tmp_original_file_path, "rb") as f_to_sign:
                                        signed_file_result = gpg.sign_file(f_to_sign, **file_sign_kwargs)

                                        if signed_file_result.status == 'signature created':
                                            encrypted_signed_result = gpg.encrypt(
                                                str(signed_file_result),
                                                recipients=recipients_fprs,
                                                sign=signer_fpr,
                                                always_trust=True,
                                                armor=True,
                                                passphrase=gpg_passphrase if gpg_passphrase else None
                                                #encoding="utf-8" # Added encoding
                                            )

                                            if encrypted_signed_result.ok:
                                                st.success("Archivo firmado y cifrado exitosamente.")
                                                archivo_to_attach_path = tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".asc", encoding="utf-8").name
                                                with open(archivo_to_attach_path, "w", encoding="utf-8") as sf:
                                                    sf.write(str(encrypted_signed_result))
                                                file_title_on_drive = archivo.name + ".gpg.asc" # Indicate encrypted
                                            else:
                                                st.error(f"❌ Error al cifrar el archivo firmado: {encrypted_signed_result.stderr}")
                                                st.stop()
                                        else:
                                            error_message = f"❌ Error al firmar el archivo: {signed_file_result.status}"
                                            if signed_file_result.stderr:
                                                error_message += f" - {signed_file_result.stderr}"
                                            st.error(error_message)
                                            st.stop()
                                
                                elif attachment_handling_choice == "Solo Firmar (visible, autenticado)":
                                    mime_type, _ = mimetypes.guess_type(tmp_original_file_path)
                                    is_text_file = mime_type and mime_type.startswith('text/')

                                    if is_text_file:
                                        # Clearsign for text files
                                        with open(tmp_original_file_path, "r", encoding="utf-8") as f_to_sign:
                                            signed_file_result = gpg.sign(
                                                f_to_sign.read(),
                                                keyid=signer_fpr,
                                                clearsign=True,
                                                passphrase=gpg_passphrase,
                                                encoding="utf-8" # Added encoding
                                            )
                                        if signed_file_result.status == 'signature created': # Check status for Sign object
                                            st.success("Archivo de texto clearsignado exitosamente.")
                                            archivo_to_attach_path = tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".asc", encoding="utf-8").name
                                            with open(archivo_to_attach_path, "w", encoding="utf-8") as sf:
                                                sf.write(str(signed_file_result))
                                            file_title_on_drive = archivo.name + ".asc"
                                            # Link to Drive will be for the .asc file
                                        else:
                                            st.error(f"❌ Error al clearsignar el archivo de texto: {signed_file_result.status} - {signed_file_result.stderr}")
                                            st.stop()
                                    else:
                                        # Detached signature for binary files
                                        with open(tmp_original_file_path, "rb") as f_to_sign:
                                            signed_file_result = gpg.sign_file(
                                                f_to_sign,
                                                keyid=signer_fpr,
                                                detach=True,
                                                passphrase=gpg_passphrase
                                            )
                                        if signed_file_result.status == 'signature created': # Check status for Sign object
                                            st.success("Archivo binario firmado (firma separada) exitosamente.")
                                            sig_file_path = tempfile.NamedTemporaryFile(delete=False, suffix=".sig").name
                                            with open(sig_file_path, "wb") as sf:
                                                sf.write(signed_file_result.data)

                                            # Upload original file
                                            if st.session_state.drive:
                                                original_file_drive = st.session_state.drive.CreateFile({'title': archivo.name})
                                                original_file_drive.SetContentFile(tmp_original_file_path)
                                                original_file_drive.Upload()
                                                link_original_file = original_file_drive['alternateLink']
                                                st.success(f"Archivo original subido a Google Drive: {link_original_file}")
                                            else:
                                                st.warning("No se pudo conectar con Google Drive para subir el archivo original.")
                                                link_original_file = "N/A"

                                            # Upload signature file
                                            if st.session_state.drive:
                                                sig_file_drive = st.session_state.drive.CreateFile({'title': archivo.name + ".sig"})
                                                sig_file_drive.SetContentFile(sig_file_path)
                                                sig_file_drive.Upload()
                                                link_signature_file = sig_file_drive['alternateLink']
                                                st.success(f"Archivo de firma (.sig) subido a Google Drive: {link_signature_file}")
                                            else:
                                                st.warning("No se pudo conectar con Google Drive para subir el archivo de firma.")
                                                link_signature_file = "N/A"
                                            
                                            # Update email body with links and attach original file
                                            link_archivo = f"Archivo Original: {link_original_file}\nFirma: {link_signature_file}"
                                            archivo_to_attach_path = tmp_original_file_path
                                            file_title_on_drive = archivo.name # Use original name as attachment name
                                        else:
                                            st.error(f"❌ Error al generar la firma detached del archivo binario: {signed_file_result.status} - {signed_file_result.stderr}")
                                            st.stop()

                                # Common logic for uploading to Drive for "Encrypt & Sign" and "Solo Firmar" (text)
                                if st.session_state.drive and archivo_to_attach_path and (attachment_handling_choice != "Solo Firmar (visible, autenticado)" or is_text_file):
                                    if not file_title_on_drive: # ensure it's set if not already from binary handling
                                        file_title_on_drive = archivo.name + (".asc" if is_text_file else "") 

                                    file = st.session_state.drive.CreateFile({'title': file_title_on_drive})
                                    file.SetContentFile(archivo_to_attach_path)
                                    file.Upload()
                                    link_archivo = file['alternateLink']
                                    st.success(f"Archivo procesado y subido a Google Drive: {link_archivo}")
                                else:
                                    if attachment_handling_choice == "Solo Firmar (visible, autenticado)" and not is_text_file:
                                        # Links are already handled for detached binary files
                                        pass
                                    else:
                                        st.warning("No se pudo conectar con Google Drive o el archivo procesado no se generó. El archivo no se subirá.")

                            except Exception as e:
                                st.error(f"❌ Error al procesar o subir el archivo adjunto: {e}. Por favor, revisa tu configuración de GPG y asegúrate de que la clave privada no tenga una contraseña o que esta sea proporcionada.")
                                st.stop()
                            finally:
                                if tmp_original_file_path and os.path.exists(tmp_original_file_path):
                                    borrar_si_se_puede(tmp_original_file_path)
                                if 'sig_file_path' in locals() and os.path.exists(sig_file_path):
                                    borrar_si_se_puede(sig_file_path)


                        final_body_for_email = str(encrypted_signed_body)
                        if attachment_handling_choice == "Solo Firmar (visible, autenticado)" and 'link_original_file' in locals():
                            final_body_for_email += f"\n\n--- Archivo Adjunto Solo Firmado ---\n{link_archivo}"

                        id_emisor = registrar_usuario_si_no_existe(st.session_state.email)

                        for d in datos_destinatarios:
                            success_email, msg_email = send_email_with_attachment(
                                subject=subject,
                                body_text=final_body_for_email,
                                from_addr=st.session_state.email,
                                password=st.session_state.password,
                                recipient_email=d["correo"],
                                attachment_path=archivo_to_attach_path,
                                attachment_name=file_title_on_drive
                            )

                            if success_email:
                                st.success(f"✅ Correo enviado a {d['correo']}")
                                id_receptor = registrar_usuario_si_no_existe(d["correo"])
                                guardar_interaccion(
                                    db_path="firmas.db",
                                    id_emisor=id_emisor,
                                    id_receptor=id_receptor,
                                    asunto=subject,
                                    mensaje_cifrado=str(encrypted_signed_body),
                                    link_archivo=link_archivo,
                                    area_destino=d["area"]
                                )
                            else:
                                st.error(f"❌ Error al enviar a {d['correo']}: {msg_email}")

                        
                            if st.session_state.drive:
                                log_text = (
                                    f"{datetime.utcnow().isoformat()} - Enviado a {d['correo']} - Asunto: {subject}\n"
                                    f"Área destino: {d['area']}\n"
                                    f"Mensaje original:\n{body}\n\n"
                                    f"Mensaje PGP:\n{str(encrypted_signed_body)}\n"
                                    f"Link Archivo Firmado en Drive: {link_archivo if link_archivo else 'N/A'}"
                                )

                                save_log_to_drive(
                                    st.session_state.drive,
                                    f"log_envio_{d['correo']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt",
                                    log_text,
                                    area_destino=d["area"],
                                    aceptado=True
                                )
                            else:
                                st.warning("No se pudo guardar el log de envío en Google Drive porque Drive no está inicializado.")
                        else:
                            st.error(msg_email)

                        # Clean up temporary attachment file if created
                        if archivo_to_attach_path and os.path.exists(archivo_to_attach_path):
                            borrar_si_se_puede(archivo_to_attach_path)

        else:
            st.warning("No puedes enviar mensajes cifrados/firmados hasta que tengas al menos una clave privada para firmar y una clave pública para cifrar.")

    with tab2:
        st.header("Desencriptar y verificar")
        encrypted_text = st.text_area("Pega el mensaje cifrado y firmado (PGP):", height=300, help="Pega el texto completo del mensaje PGP (incluyendo '-----BEGIN PGP MESSAGE-----' y '-----END PGP MESSAGE-----').")
        
        uploaded_pgp_text_file = st.file_uploader("O sube un archivo de texto PGP (.asc, .txt):", type=["asc", "txt"], help="Sube un archivo que contenga un mensaje PGP en formato ASCII-armored.")
        uploaded_encrypted_binary_file = st.file_uploader("🔐 Sube un archivo cifrado binario para desencriptar (.gpg, .pgp):", type=["gpg", "pgp"], help="Sube un archivo binario que haya sido cifrado con GPG.")

        if st.button("Decrypt and Verify"):
            st.session_state.decrypted_content_for_tab3 = None
            st.session_state.decrypted_file_path_for_tab3 = None
            st.session_state.decrypted_file_name_for_tab3 = None
            st.session_state.original_sender_email_for_tab3 = ""
            st.session_state.decryption_status_for_tab3 = ""
            st.session_state.verification_status_for_tab3 = ""
            st.session_state.verified_sender_uid_for_tab3 = "Desconocido"
            st.session_state.original_subject_for_tab3 = "" # Reset subject as well

            decrypted_result = None
            content_source_description = "N/A"
            temp_decrypted_file_path = None
            signer_email_for_forward = ""

            if encrypted_text:
                st.info("Attempting to decrypt and verify pasted text...")
                decrypted_result = gpg.decrypt(encrypted_text, always_trust=True)
                content_source_description = "Pasted Text"
                st.session_state.original_subject_for_tab3 = "Mensaje Cifrado Original" # Default for pasted text
            elif uploaded_pgp_text_file:
                st.info(f"Attempting to decrypt and verify uploaded text file: {uploaded_pgp_text_file.name}...")
                with tempfile.NamedTemporaryFile(delete=False, mode="wb") as temp_pgp_file:
                    temp_pgp_file.write(uploaded_pgp_text_file.getvalue())
                    temp_pgp_file_path = temp_pgp_file.name
                
                with open(temp_pgp_file_path, "rb") as f:
                    decrypted_result = gpg.decrypt(f.read(), always_trust=True)
                os.remove(temp_pgp_file_path)
                content_source_description = f"Uploaded PGP Text File ({uploaded_pgp_text_file.name})"
                st.session_state.original_subject_for_tab3 = f"FW: {uploaded_pgp_text_file.name}"
            elif uploaded_encrypted_binary_file:
                st.info(f"Attempting to decrypt uploaded binary file: {uploaded_encrypted_binary_file.name}...")
                with tempfile.NamedTemporaryFile(delete=False, mode="wb") as temp_binary_file:
                    temp_binary_file.write(uploaded_encrypted_binary_file.getvalue())
                    temp_binary_file_path = temp_binary_file.name
                
                decrypted_result = gpg.decrypt_file(temp_binary_file_path, always_trust=True)
                os.remove(temp_binary_file_path)
                content_source_description = f"Uploaded Binary File ({uploaded_encrypted_binary_file.name})"
                st.session_state.original_subject_for_tab3 = f"FW: {uploaded_encrypted_binary_file.name}"
            else:
                st.warning("Please paste encrypted text or upload an encrypted file to decrypt.")
                st.stop()

            if decrypted_result and decrypted_result.ok:
                st.success("✅ Descifrado exitoso.")
                st.session_state.decryption_status_for_tab3 = "Descifrado exitoso."

                # Now, check signature validity *specifically*
                if decrypted_result.valid:
                    signer_uid = decrypted_result.username
                    signer_fpr = decrypted_result.fingerprint
                    st.success(f"🔏 Firma válida de: {signer_uid} (FPR: {signer_fpr})")
                    st.session_state.verified_sender_uid_for_tab3 = signer_uid
                    st.session_state.verification_status_for_tab3 = f"✅ Firma Válida de: {signer_uid} (FPR: {signer_fpr})"
                    
                    # Extract email from username
                    if signer_uid:
                        email_match = re.search(r"<(.+@.+\..+)>", signer_uid)
                        if email_match:
                            signer_email_for_forward = email_match.group(1).strip()
                        else:
                            # Fallback if no email in angle brackets, but username exists
                            signer_email_for_forward = signer_uid.split(" ")[-1] # Take last part as potential email
                            if "@" not in signer_email_for_forward:
                                signer_email_for_forward = "" # Clear if it doesn't look like an email
                    
                else:
                    st.warning(f"⚠️ **Advertencia de Firma:** La firma es **INVÁLIDA**. El estado es: `{decrypted_result.status}`. "
                                f"El mensaje puede haber sido alterado o la firma está dañada. **NO CONFÍE en este mensaje.**")
                    if decrypted_result.stderr:
                            st.info(f"Detalles de GnuPG: {decrypted_result.stderr}")
                    st.session_state.verification_status_for_tab3 = f"❌ Firma INVÁLIDA: {decrypted_result.status}"
                    st.session_state.verified_sender_uid_for_tab3 = "Desconocido (Firma Inválida)"
                    signer_email_for_forward = "" # Default if signature is invalid or unknown
                
                st.session_state.original_sender_email_for_tab3 = signer_email_for_forward
                if signer_email_for_forward:
                    st.info(f"Email del firmante detectado: {signer_email_for_forward}")
                else:
                    st.info("No se pudo detectar el email del firmante automáticamente. Por favor, ingrésalo manualmente para reenviar.")


                # Handle decrypted content (text or binary)
                try:
                    decrypted_data_text = decrypted_result.data.decode('utf-8', errors='replace') # Use 'replace' for display
                    st.session_state.decrypted_content_for_tab3 = decrypted_data_text
                    st.subheader("Contenido Desencriptado (Texto):")
                    st.text_area("Mensaje desencriptado", decrypted_data_text, height=300, disabled=True)

                except UnicodeDecodeError:
                    st.info("El contenido desencriptado es binario. Intenta descargarlo para verlo.")
                    st.session_state.decrypted_content_for_tab3 = "Binary content - refer to file download" # Placeholder
                    
                    # Save binary content to a temporary file for download/preview
                    original_file_name_for_binary = (uploaded_encrypted_binary_file.name if uploaded_encrypted_binary_file
                                                    else "decrypted_file")
                    original_ext = os.path.splitext(original_file_name_for_binary)[1]
                    temp_decrypted_file_path = tempfile.NamedTemporaryFile(delete=False, suffix=original_ext).name
                    with open(temp_decrypted_file_path, "wb") as f_out:
                        f_out.write(decrypted_result.data)
                    
                    st.session_state.decrypted_file_path_for_tab3 = temp_decrypted_file_path
                    st.session_state.decrypted_file_name_for_tab3 = original_file_name_for_binary

                    st.subheader("Vista Previa y Descarga de Archivo Desencriptado:")
                    # Try to display common image types
                    mime_type, _ = mimetypes.guess_type(original_file_name_for_binary)
                    if mime_type and mime_type.startswith('image'):
                        st.image(temp_decrypted_file_path, caption="Decrypted Image Preview", use_column_width=True)
                    elif mime_type == 'application/pdf':
                        st.info("Este es un archivo PDF. Puedes descargarlo para visualizarlo.")
                    else:
                        st.info("No se puede previsualizar este tipo de archivo. Descárgalo para abrirlo.")

                    with open(temp_decrypted_file_path, "rb") as file:
                        st.download_button(
                            label=f"Descargar {original_file_name_for_binary}",
                            data=file,
                            file_name=original_file_name_for_binary,
                            mime=mime_type or 'application/octet-stream'
                        )
                    st.success(f"Archivo desencriptado guardado temporalmente para descarga/envío: {temp_decrypted_file_path}")

                except Exception as e:
                    st.error(f"❌ Ocurrió un error inesperado al mostrar el contenido: {e}. Descargando el archivo original.")
                    # Fallback to binary download if any other error occurs during text display
                    original_file_name_for_binary = (uploaded_encrypted_binary_file.name if uploaded_encrypted_binary_file
                                                    else "decrypted_file_error")
                    original_ext = os.path.splitext(original_file_name_for_binary)[1]
                    temp_decrypted_file_path = tempfile.NamedTemporaryFile(delete=False, suffix=original_ext).name
                    with open(temp_decrypted_file_path, "wb") as f_out:
                        f_out.write(decrypted_result.data)
                    st.download_button("Descargar archivo desencriptado (binario)", decrypted_result.data, file_name=original_file_name_for_binary, mime='application/octet-stream')
                    st.session_state.decrypted_content_for_tab3 = "Binary content - refer to file download"
                    st.session_state.decrypted_file_path_for_tab3 = temp_decrypted_file_path
                    st.session_state.decrypted_file_name_for_tab3 = original_file_name_for_binary
                
                st.info("Puedes ir a la pestaña 'Responder y reenviar' para enviar el estado y reenviar el mensaje/archivo.")

            else:
                st.error(f"❌ Error al descifrar o verificar: {decrypted_result.stderr if decrypted_result else 'No se pudo procesar el resultado.'}")
                st.info("Asegúrate de que tienes la clave privada correcta y que el mensaje está correctamente formateado.")
                st.session_state.decryption_status_for_tab3 = f"Error: {decrypted_result.stderr if decrypted_result else 'No se pudo procesar el resultado.'}"
                st.session_state.verification_status_for_tab3 = "Firma no válida o no encontrada."
                st.session_state.original_sender_email_for_tab3 = "" # Clear email on decryption failure
                
                # Log failure
                id_emisor_app = registrar_usuario_si_no_existe(st.session_state.email)
                temp_original_sender_email_for_log = "Desconocido"
                if encrypted_text:
                    sender_match_fail = re.search(r"From: (.+@.+\..+)", encrypted_text)
                    if sender_match_fail:
                        temp_original_sender_email_for_log = sender_match_fail.group(1).strip()
                elif uploaded_pgp_text_file:
                    temp_original_sender_email_for_log = f"Archivo Texto PGP ({uploaded_pgp_text_file.name})"
                elif uploaded_encrypted_binary_file:
                    temp_original_sender_email_for_log = f"Archivo Binario ({uploaded_encrypted_binary_file.name})"

                id_original_sender_fail = registrar_usuario_si_no_existe(temp_original_sender_email_for_log, rol="emisor_original")

                guardar_interaccion(
                    db_path="firmas.db",
                    id_emisor=id_emisor_app,
                    id_receptor=id_original_sender_fail,
                    asunto=st.session_state.original_subject_for_tab3 if st.session_state.original_subject_for_tab3 else "Mensaje Cifrado Fallido",
                    mensaje_cifrado=encrypted_text[:500] if encrypted_text else (uploaded_pgp_text_file.name if uploaded_pgp_text_file else (uploaded_encrypted_binary_file.name if uploaded_encrypted_binary_file else "No Content")),
                    link_archivo=None,
                    area_destino="Desconocida",
                    aceptado=False,
                    fecha_respuesta=datetime.now()
                )
                if st.session_state.drive:
                    log_text_rejected = (
                        f"{datetime.utcnow().isoformat()} - Mensaje RECHAZADO (Error de Desencriptación/Verificación).\n"
                        f"Fuente del Contenido: {content_source_description}\n"
                        f"Mensaje Cifrado Original (Primeras 500 chars):\n{(encrypted_text[:500] if encrypted_text else (uploaded_pgp_text_file.name if uploaded_pgp_text_file else (uploaded_encrypted_binary_file.name if uploaded_encrypted_binary_file else 'N/A')))}\n"
                        f"Error: {decrypted_result.stderr if decrypted_result else 'No se pudo procesar.'}"
                    )
                    save_log_to_drive(
                        st.session_state.drive,
                        f"log_desencriptado_rechazado_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt",
                        log_text_rejected,
                        area_destino="Desencriptado",
                        aceptado=False
                    )
                else:
                    st.warning("No se pudo guardar el log de rechazo en Google Drive porque Drive no está inicializado.")

    with tab3:
        st.header("Responder y reenviar el estado")

        if st.session_state.decrypted_content_for_tab3 or st.session_state.decrypted_file_path_for_tab3:
            st.info("Información del mensaje desencriptado y verificado:")
            st.write(f"**Remitente Original (UID GPG):** {st.session_state.verified_sender_uid_for_tab3}")
            
            # Display based on whether email was automatically detected
            if st.session_state.original_sender_email_for_tab3:
                st.write(f"**Remitente Original (Email detectado):** {st.session_state.original_sender_email_for_tab3}")
            else:
                st.write(f"**Remitente Original (Email detectado):** (No detectado automáticamente, por favor ingrésalo manualmente)")
            
            st.write(f"**Receptor (Tú):** {st.session_state.email}")
            st.write(f"**Estado de Descifrado:** {st.session_state.decryption_status_for_tab3}")
            st.write(f"**Estado de Firma:** {st.session_state.verification_status_for_tab3}")
            

            if st.session_state.decrypted_content_for_tab3 and st.session_state.decrypted_content_for_tab3 != "Binary content - refer to file download":
                st.subheader("Contenido del Mensaje:")
                st.text_area("Vista previa del mensaje", st.session_state.decrypted_content_for_tab3, height=200, disabled=True)
            
            if st.session_state.decrypted_file_path_for_tab3:
                st.subheader("Archivo Desencriptado Adjunto:")
                mime_type, _ = mimetypes.guess_type(st.session_state.decrypted_file_name_for_tab3)
                if mime_type and mime_type.startswith('image'):
                    st.image(st.session_state.decrypted_file_path_for_tab3, caption=f"Preview: {st.session_state.decrypted_file_name_for_tab3}", use_column_width=True)
                elif mime_type == 'application/pdf':
                    st.info(f"Este es un archivo PDF ({st.session_state.decrypted_file_name_for_tab3}). No se puede previsualizar directamente aquí, pero se adjuntará al reenvío.")
                else:
                    st.info(f"No se puede previsualizar el archivo '{st.session_state.decrypted_file_name_for_tab3}'. Se adjuntará al reenvío.")
                
                with open(st.session_state.decrypted_file_path_for_tab3, "rb") as file:
                    st.download_button(
                        label=f"Descargar Archivo: {st.session_state.decrypted_file_name_for_tab3}",
                        data=file,
                        file_name=st.session_state.decrypted_file_name_for_tab3,
                        mime=mime_type or 'application/octet-stream',
                        key="download_button_tab3"
                    )

            forward_recipient_email = st.text_input(
                "Email del destinatario para reenviar (remitente original):", 
                value=st.session_state.original_sender_email_for_tab3,
                help="El email al que se reenviará el mensaje. Se prellena con el remitente original si se detectó."
            )
            
            forward_subject = st.text_input(
                "Asunto para reenviar:", 
                value=f"FW: {st.session_state.original_subject_for_tab3}", 
                help="El asunto del correo reenviado. Se prellena con 'FW:' más el asunto original."
            )
            
            # Removed signer selection as email body will not be signed
            # all_private_keys = gpg.list_keys(True)
            # valid_private_keys = [k for k in all_private_keys if is_valid_key(k)]
            
            # forward_signer_options = ["Selecciona una clave para firmar el reenvío"] + [f"{k['uids'][0]} [{k['fingerprint'][:8]}]" for k in valid_private_keys]
            
            # # Determine default index for signer selection
            # default_signer_index = 0 # Default to "Selecciona una clave..."
            # if valid_private_keys:
            #     default_signer_index = 1 # Select the first valid private key by default

            # forward_signer_selection = st.selectbox(
            #     "Firmar el reenvío como (clave privada):", 
            #     forward_signer_options, 
            #     index=default_signer_index, # Set default selection
            #     help="Selecciona la clave privada GPG para firmar el mensaje antes de reenviarlo."
            # )
            
            acceptance_status = st.radio("Estado de la solicitud:", ("Aprobado", "Rechazado"))

            if st.button("Forward Status and Document"): # Changed button text
                if forward_recipient_email: # Removed signer selection check
                    # Removed signer_fpr and signer_uid as email body will not be signed
                    # selected_key_info = next((k for k in valid_private_keys if forward_signer_selection.startswith(k['uids'][0])), None)
                    # forward_signer_fpr = selected_key_info['fingerprint'] if selected_key_info else None
                    # forward_signer_uid = selected_key_info['uids'][0] if selected_key_info and selected_key_info['uids'] else "Desconocido"

                    # if forward_signer_fpr: # This check is no longer needed
                    st.info(f"Reenviando estado y documento a {forward_recipient_email}...")
                    
                    forward_body_content = ""
                    if st.session_state.decrypted_content_for_tab3 and st.session_state.decrypted_content_for_tab3 != "Binary content - refer to file download":
                        forward_body_content = f"Original Message Content:\n\n{st.session_state.decrypted_content_for_tab3}\n\n"
                    else:
                        forward_body_content = "Original content was a binary file, please see attachment.\n\n"
                    
                    # Simplified status message for better aesthetic as per log6 feedback
                    status_message = f"Su solicitud: **{acceptance_status}**.\n\n"
                    
                    final_forward_body = status_message + forward_body_content

                    success_forward, msg_forward = forward_status_and_document( # Changed function call
                        original_sender_email=forward_recipient_email,
                        body=final_forward_body, # This will be plain text
                        subject=forward_subject,
                        from_addr=st.session_state.email,
                        password=st.session_state.password,
                        # Removed signer_fpr, signer_uid, approval_status, gpg_passphrase
                        attachment_path=st.session_state.decrypted_file_path_for_tab3,
                        attachment_name=st.session_state.decrypted_file_name_for_tab3
                    )
                    
                    if success_forward:
                        st.success(msg_forward)
                        id_emisor_app = registrar_usuario_si_no_existe(st.session_state.email)
                        id_original_sender = registrar_usuario_si_no_existe(forward_recipient_email, rol="emisor_original")
                        
                        guardar_interaccion(
                            db_path="firmas.db",
                            id_emisor=id_emisor_app,
                            id_receptor=id_original_sender,
                            asunto=forward_subject,
                            mensaje_cifrado=final_forward_body,
                            link_archivo=st.session_state.decrypted_file_path_for_tab3, # Link to temporary decrypted file for logging
                            area_destino="Desencriptado",
                            aceptado=(acceptance_status == "Aprobado"),
                            fecha_respuesta=datetime.now()
                        )
                        if st.session_state.drive:
                            log_text_accepted = (
                                f"{datetime.utcnow().isoformat()} - Mensaje DESENCRIPTADO y RESUELTO ({acceptance_status}).\n"
                                f"Enviado por (Detectado/Reenviado a): {forward_recipient_email}\n"
                                f"Asunto Reenviado: {forward_subject}\n"
                                f"Contenido Desencriptado (Primeras 500 chars):\n{st.session_state.decrypted_content_for_tab3[:500] if st.session_state.decrypted_content_for_tab3 and st.session_state.decrypted_content_for_tab3 != 'Binary content - refer to file download' else 'Binary file content (see attachment)'}...\n"
                                f"Estado de Verificación: {st.session_state.verification_status_for_tab3}\n"
                                f"Reenviado A: {forward_recipient_email}\n"
                                f"Estado de Solicitud: {acceptance_status}\n"
                                f"Archivo Desencriptado Adjunto (si aplica): {st.session_state.decrypted_file_path_for_tab3 or 'N/A'}"
                            )
                            save_log_to_drive(
                                st.session_state.drive,
                                f"log_desencriptado_{acceptance_status.lower()}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt",
                                log_text_accepted,
                                area_destino="Desencriptado",
                                aceptado=(acceptance_status == "Aprobado")
                            )
                        else:
                            st.warning("No se pudo guardar el log de resolución en Google Drive porque Drive no está inicializado.")
                        
                        # Clean up temporary decrypted file after successful forward
                        if st.session_state.decrypted_file_path_for_tab3 and os.path.exists(st.session_state.decrypted_file_path_for_tab3):
                            os.remove(st.session_state.decrypted_file_path_for_tab3)
                            st.session_state.decrypted_file_path_for_tab3 = None
                            st.session_state.decrypted_file_name_for_tab3 = None

                    else:
                        st.error(msg_forward)
                else: # This block now handles only missing recipient email
                    st.warning("Por favor, introduce el email del destinatario para reenviar.")
        else:
            st.info("Por favor, desencripta y verifica un mensaje en la pestaña 'Desencriptar y verificar' primero para habilitar esta sección.")

    with tab4:
        st.header("Descargar y ver documento .asc")
        st.info("Sube un archivo .asc (texto firmado o cifrado y firmado) para ver su contenido y verificar la firma.")

        uploaded_asc_file_for_tab4 = st.file_uploader("Sube un archivo .asc", type=["asc", "txt"], key="tab4_uploader")

        # Add a text input for user to manually specify original filename
        manual_original_filename = st.text_input(
            "Opcional: Si el archivo desencriptado es binario, especifica su nombre original (e.g., 'document.pdf', 'image.jpg')",
            key="tab4_manual_filename_input"
        )

        if uploaded_asc_file_for_tab4:
            if st.button("Process .asc File", key="tab4_process_button"):
                st.subheader("Resultados del procesamiento:")
                temp_asc_file_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, mode="wb", suffix=".asc") as tmp_file:
                        tmp_file.write(uploaded_asc_file_for_tab4.getvalue())
                        temp_asc_file_path = tmp_file.name

                    # Try to decrypt and verify
                    decrypted_result_tab4 = gpg.decrypt(open(temp_asc_file_path, 'rb').read(), always_trust=True)

                    if decrypted_result_tab4.ok:
                        st.success("✅ Descifrado exitoso.")
                        
                        # Determine the filename for download
                        download_file_name = uploaded_asc_file_for_tab4.name
                        if manual_original_filename:
                            download_file_name = manual_original_filename
                        else:
                            # Heuristic: Remove common PGP suffixes
                            if download_file_name.lower().endswith(".asc"):
                                download_file_name = download_file_name[:-4]
                            if download_file_name.lower().endswith(".gpg"):
                                download_file_name = download_file_name[:-4]
                            elif download_file_name.lower().endswith(".pgp"):
                                download_file_name = download_file_name[:-4]
                            
                            # Add a generic extension if none is left after heuristic (e.g., from 'message.asc' to 'message.bin')
                            if '.' not in download_file_name:
                                download_file_name += ".bin" # Default for unknown binary

                        try:
                            # Attempt to decode as UTF-8. If successful, it's text.
                            decrypted_data_text_tab4 = decrypted_result_tab4.data.decode('utf-8', errors='strict') # Use 'strict' to force UnicodeDecodeError on binary
                            st.subheader("Contenido Original (Texto):")
                            st.text_area("Contenido Desencriptado", decrypted_data_text_tab4, height=300, disabled=True, key="tab4_decrypted_text")
                            
                            # Provide download for the decrypted text
                            # For text, always suggest .txt unless manually overridden with a text-like extension
                            if not manual_original_filename or not any(manual_original_filename.lower().endswith(ext) for ext in ['.txt', '.md', '.log', '.csv']):
                                download_file_name = download_file_name.replace(".bin", ".txt") # Ensure text download has .txt
                                if not download_file_name.lower().endswith(".txt"): # In case it was .pdf.asc, make it .pdf.txt
                                     download_file_name += ".txt"

                            st.download_button(
                                label=f"Descargar {download_file_name}",
                                data=decrypted_data_text_tab4.encode('utf-8'),
                                file_name=download_file_name,
                                mime="text/plain",
                                key="tab4_download_txt"
                            )

                        except UnicodeDecodeError:
                            # If decoding failed, it's binary content
                            st.info("El contenido desencriptado es binario. Puedes descargarlo con su extensión original.")
                            
                            # Save binary content to a temporary file with the determined download_file_name's extension
                            temp_binary_output_path_tab4 = tempfile.NamedTemporaryFile(delete=False, suffix=f".{download_file_name.split('.')[-1]}").name
                            with open(temp_binary_output_path_tab4, "wb") as f_out:
                                f_out.write(decrypted_result_tab4.data)
                            
                            mime_type, _ = mimetypes.guess_type(temp_binary_output_path_tab4)

                            # Preview for common binary types
                            if mime_type and mime_type.startswith('image'):
                                st.image(temp_binary_output_path_tab4, caption=f"Decrypted Image Preview: {download_file_name}", use_column_width=True)
                            elif mime_type == 'application/pdf':
                                st.info(f"Este es un archivo PDF ({download_file_name}). Descárgalo para visualizarlo.")
                            else:
                                st.info(f"No se puede previsualizar este tipo de archivo ({mime_type or 'desconocido'}). Descárgalo para abrirlo.")

                            with open(temp_binary_output_path_tab4, "rb") as file_to_download:
                                st.download_button(
                                    label=f"Descargar {download_file_name}",
                                    data=file_to_download.read(),
                                    file_name=download_file_name,
                                    mime=mime_type or 'application/octet-stream',
                                    key="tab4_download_binary"
                                )
                            os.remove(temp_binary_output_path_tab4)

                    else:
                        st.warning(f"⚠️ No se pudo descifrar el contenido. Mensaje de GPG: {decrypted_result_tab4.stderr}")
                        st.info("Esto puede significar que el archivo no está cifrado para tu clave o está corrupto. Intentando verificar la firma si es clearsigned...")
                        
                        clearsigned_content = open(temp_asc_file_path, 'r', encoding='utf-8', errors='ignore').read()
                        verified_result_tab4 = gpg.verify(clearsigned_content)

                        if verified_result_tab4.valid:
                            st.success("✅ El archivo es un mensaje clearsigned válido.")
                            st.subheader("Contenido Original (Clearsigned):")
                            st.text_area("Contenido Verificado", verified_result_tab4.data.decode('utf-8', errors='replace'), height=300, disabled=True, key="tab4_clearsigned_text")
                            
                            # For clearsigned text, the original file is usually the text content
                            original_clearsigned_name = uploaded_asc_file_for_tab4.name
                            if original_clearsigned_name.lower().endswith(".asc"):
                                original_clearsigned_name = original_clearsigned_name[:-4] + ".txt"
                            else:
                                original_clearsigned_name += ".txt" # Ensure a .txt extension

                            st.download_button(
                                label=f"Descargar {original_clearsigned_name}",
                                data=verified_result_tab4.data,
                                file_name=original_clearsigned_name,
                                mime="text/plain",
                                key="tab4_download_clearsigned"
                            )
                        else:
                            st.error("❌ No se pudo descifrar ni verificar el archivo.")
                            if verified_result_tab4.stderr:
                                st.info(f"Detalles de GnuPG (verificación): {verified_result_tab4.stderr}")
                            st.info("Asegúrate de que tienes la clave pública del firmante importada.")

                    st.subheader("Detalles de la Firma:")
                    if decrypted_result_tab4 and decrypted_result_tab4.valid:
                        st.write(f"**Firmado por:** {decrypted_result_tab4.username}")
                        st.write(f"**Fingerprint del Firmante:** {decrypted_result_tab4.fingerprint}")
                        st.write(f"**Estado de la Firma:** ✅ Válida")
                    elif verified_result_tab4 and verified_result_tab4.valid:
                        st.write(f"**Firmado por:** {verified_result_tab4.username}")
                        st.write(f"**Fingerprint del Firmante:** {verified_result_tab4.fingerprint}")
                        st.write(f"**Estado de la Firma:** ✅ Válida")
                    else:
                        st.write("**Estado de la Firma:** ❌ No válida o no detectada.")
                        if decrypted_result_tab4 and decrypted_result_tab4.stderr:
                            st.write(f"Mensaje de GnuPG: {decrypted_result_tab4.stderr}")
                        elif verified_result_tab4 and verified_result_tab4.stderr:
                            st.write(f"Mensaje de GnuPG: {verified_result_tab4.stderr}")
                    
                except Exception as e:
                    st.error(f"❌ Ocurrió un error al procesar el archivo .asc: {e}")
                    st.info("Asegúrate de que el archivo es un formato .asc válido.")
                finally:
                    if temp_asc_file_path and os.path.exists(temp_asc_file_path):
                        os.remove(temp_asc_file_path)

    with tab_admin:
        st.header("⚙️ Administración de usuarios")

        nombre = st.text_input("Nombre")
        correo = st.text_input("Correo")
        area = st.selectbox("Área", ["Finanzas", "TI", "RRHH", "Legal", "Marketing"])
        fingerprint = st.text_input("Fingerprint (clave pública)")

        if st.button("Registrar usuario"):
            conn = sqlite3.connect("firmas.db")
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO usuarios (nombre, email, rol, area, contraseña) VALUES (?, ?, 'usuario', ?, '1234')", (nombre, correo, area))
            conn.commit()
            cursor.execute("SELECT id_usuario FROM usuarios WHERE email = ?", (correo,))
            id_usuario = cursor.fetchone()[0]
            cursor.execute("INSERT INTO claves_gpg (id_usuario, fingerprint, tipo) VALUES (?, ?, 'publica')", (id_usuario, fingerprint))
            conn.commit()
            conn.close()
            st.success("Usuario registrado.")

        with sqlite3.connect("firmas.db") as conn:
            df = pd.read_sql_query("""
                SELECT 
                    u.nombre, 
                    u.email, 
                    u.area, 
                    c.fingerprint
                FROM usuarios u 
                LEFT JOIN claves_gpg c 
                    ON u.id_usuario = c.id_usuario AND c.tipo = 'publica'
            """, conn)

            st.subheader("📋 Usuarios registrados y claves públicas")
            st.dataframe(df)
            st.subheader("🗑️ Eliminar usuarios")

            with sqlite3.connect("firmas.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id_usuario, nombre, email FROM usuarios")
                usuarios = cursor.fetchall()

            if usuarios:
                opciones = [f"{u[0]} – {u[1]} ({u[2]})" for u in usuarios]
                seleccion = st.selectbox("Selecciona un usuario para eliminar:", opciones)

                if st.button("Eliminar usuario seleccionado"):
                    id_a_borrar = int(seleccion.split("–")[0].strip())

                    with sqlite3.connect("firmas.db") as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM claves_gpg WHERE id_usuario = ?", (id_a_borrar,))
                        cursor.execute("DELETE FROM interacciones WHERE id_emisor = ? OR id_receptor = ?", (id_a_borrar, id_a_borrar))
                        cursor.execute("DELETE FROM usuarios WHERE id_usuario = ?", (id_a_borrar,))
                        conn.commit()
                    st.success("✅ Usuario eliminado correctamente.")
                    st.rerun()
            else:
                st.info("No hay usuarios registrados.")
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.email = ""
        st.session_state.password = ""
        st.session_state.drive = None
        st.session_state.gpg_passphrase = "" # Clear passphrase on logout
        # Clear all session states related to decrypted data
        st.session_state.decrypted_content_for_tab3 = None
        st.session_state.decrypted_file_path_for_tab3 = None
        st.session_state.decrypted_file_name_for_tab3 = None
        st.session_state.original_sender_email_for_tab3 = ""
        st.session_state.decryption_status_for_tab3 = ""
        st.session_state.verification_status_for_tab3 = ""
        st.session_state.verified_sender_uid_for_tab3 = "Desconocido"
        st.session_state.original_subject_for_tab3 = ""
        st.rerun()