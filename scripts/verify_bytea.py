"""credentials.encrypted_data BYTEA 확인."""
import psycopg2

conn = psycopg2.connect(
    host="127.0.0.1", port=5432, dbname="workflow_automation",
    user="postgres", password=input("DB password: "),
)
cur = conn.cursor()
cur.execute(
    "SELECT column_name, data_type FROM information_schema.columns "
    "WHERE table_name='credentials' AND column_name='encrypted_data'"
)
row = cur.fetchone()
conn.close()
print(f"[{'PASS' if row and row[1] == 'bytea' else 'FAIL'}] credentials.encrypted_data: {row}")
