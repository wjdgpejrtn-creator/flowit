"""Cloud SQL 접속 테스트 스크립트."""
import psycopg2

conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    dbname="workflow_automation",
    user="postgres",
    password=input("DB password: "),
)
print(f"PostgreSQL version: {conn.server_version}")

cur = conn.cursor()
cur.execute("SELECT version()")
print(cur.fetchone()[0])

conn.close()
print("Connection OK!")
