# MA2006B.601-Gpo.3
Nota: Test6, contiene las versiones finales del código.
# Reto

El proyecto busca implementar un flujo seguro y controlado para el envío, validación y registro de mensajes electrónicos dentro de la organización.  
A través de un sistema de autenticación robusto, cifrado de mensajes y firma digital, se garantiza la integridad, confidencialidad y trazabilidad de las comunicaciones.  
Además, se automatiza el proceso de notificación y registro de logs en un repositorio centralizado, permitiendo una auditoría completa y el cumplimiento de estándares de seguridad de la información.

---

# 📌 Flujo del proceso

## 1️⃣ Login al sistema

→ El usuario se autentica en el sistema.

## 2️⃣ Composición y envío del mensaje

→ El usuario envía un mensaje:  
- Puede ser propio (escrito por él) o basado en una plantilla.  
- El mensaje se encripta.  
- Se firma digitalmente.

## 3️⃣ Recepción del mensaje

→ El destinatario recibe el mensaje.

## 4️⃣ Desencriptado y verificación de la firma

→ El sistema o la persona destinataria:  
- Desencripta el mensaje.  
- Verifica la firma digital.

## 5️⃣ Proceso de aprobación

→ El destinatario:  
- Aprueba o rechaza el mensaje.

## 6️⃣ Notificación al remitente

→ El sistema notifica al remitente si su mensaje fue aprobado o rechazado.

## 7️⃣ Registro en Drive

→ Se genera un log del proceso (incluyendo la acción final y metadatos relevantes) y se guarda en un repositorio (ej: Google Drive / OneDrive) para auditoría y control.


# 🛠️ Requisitos del Sistema

## Requisitos de hardware y sistema operativo

💻 **Computadora con:**
- macOS
- o Windows

## Software necesario

🔐 **GPG** o **Kleopatra** instalado  
_Para cifrado / descifrado y firma digital de mensajes._

🐍 **Python** + **Anaconda**  
_Para ejecutar scripts auxiliares y procesamiento de flujos._

## Configuración adicional

🔑 **Contraseñas de aplicación** de los usuarios configuradas  
_Para uso en sistemas seguros._

📦 **Acceso a los repositorios de claves**  
_Para gestión de claves públicas y privadas._


Etapa 1: https://docs.google.com/document/d/1V26wAaVDaUzoG_BlFtpPhMpQAJiNLLlnVoUiexk2xxQ/edit?usp=sharing

Canva: https://www.canva.com/design/DAGpuai57jQ/Hn3cE5AP3Mz-h6pgV1AOLg/view?utm_content=DAGpuai57jQ&utm_campaign=designshare&utm_medium=link2&utm_source=uniquelinks&utlId=h374224b224

_Dado que se tienen enlaces en el código por medio de los puertos SMTP 587, existen 2 archivos los cuales no se encuentran en el repositorio dada la sensibilidad de información y credenciales que estos poseen._
