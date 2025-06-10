import sqlite3

# Cambia estos valores
EMAIL_OBJETIVO = "josedavidbr04@gmail.com"
NUEVA_AREA = "Almacén" # 1=admin, 2=coordinador, 3=operativo, 4=externo

conn = sqlite3.connect("firmas.db")
cursor = conn.cursor()

cursor.execute("UPDATE usuarios SET area = ? WHERE email = ?", (str(NUEVA_AREA), EMAIL_OBJETIVO))
conn.commit()
conn.close()

print(f"✅ Nivel de acceso cambiado a {NUEVA_AREA} para {EMAIL_OBJETIVO}")