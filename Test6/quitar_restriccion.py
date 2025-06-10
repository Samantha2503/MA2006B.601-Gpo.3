import sqlite3

# Conecta a la base de datos existente
conn = sqlite3.connect("firmas.db")
cursor = conn.cursor()

# 🪧 Renombrar la tabla vieja (por seguridad)
cursor.execute("ALTER TABLE usuarios RENAME TO usuarios_viejos;")

# 🛠 Crear la nueva tabla sin restricción CHECK en 'rol'
cursor.execute("""
CREATE TABLE usuarios (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    email TEXT UNIQUE NOT NULL,
    rol TEXT NOT NULL,
    area TEXT,
    contraseña TEXT,
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
);
""")

# 📦 Copiar los datos de la tabla vieja a la nueva
cursor.execute("""
INSERT INTO usuarios (id_usuario, nombre, email, rol, area, contraseña, fecha_registro)
SELECT id_usuario, nombre, email, rol, area, contraseña, fecha_registro
FROM usuarios_viejos;
""")

conn.commit()
conn.close()

print("✅ Tabla 'usuarios' recreada sin restricción CHECK.")
