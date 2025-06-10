from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta
import os

def generar_certificado_pfx(nombre="Usuario Firmante", password_pfx="clave123", nombre_archivo="certificado.pfx"):
    # Generar clave privada
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Datos del sujeto
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"MX"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"CDMX"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"Ciudad de México"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Mi Empresa"),
        x509.NameAttribute(NameOID.COMMON_NAME, nombre),
    ])

    # Crear certificado autofirmado
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow() - timedelta(days=1))
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    # Guardar en .pfx
    pfx = serialization.pkcs12.serialize_key_and_certificates(
        name=nombre.encode(),
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password_pfx.encode()),
    )

    with open(nombre_archivo, "wb") as f:
        f.write(pfx)

    print(f"✅ Certificado generado: {nombre_archivo} (contraseña: {password_pfx})")

# Ejecutar
if __name__ == "__main__":
    generar_certificado_pfx()
