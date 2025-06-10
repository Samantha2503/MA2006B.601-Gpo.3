# Exportar usuarios a CSV si quieres
import sqlite3
import pandas as pd

conn = sqlite3.connect("firmas.db")
df = pd.read_sql("SELECT * FROM usuarios", conn)
df.to_csv("backup_usuarios.csv", index=False)
conn.close()
print("✅ Respaldo de usuarios realizado exitosamente en 'backup_usuarios.csv'")