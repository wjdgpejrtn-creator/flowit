"""Cloud SQL 확장 활성화 (pgcrypto + pgvector)."""
import psycopg2

conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    dbname="workflow_automation",
    user="postgres",
    password=input("DB password: "),
)
conn.autocommit = True
cur = conn.cursor()

cur.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
print("pgcrypto OK")

cur.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
print("pgvector OK")

cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname IN ('pgcrypto', 'vector')")
for row in cur.fetchall():
    print(f"  {row[0]}: v{row[1]}")

conn.close()
print("Extensions ready!")
