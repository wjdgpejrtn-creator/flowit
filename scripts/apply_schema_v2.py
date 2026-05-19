"""Drop all existing tables and apply schema v2 (Spec-aligned DDL)."""
import sys
from pathlib import Path
import psycopg2

password = input("DB password: ")

conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    dbname="workflow_automation",
    user="postgres",
    password=password,
)
conn.autocommit = True
cur = conn.cursor()

# Drop all existing tables
print("=== Dropping existing schema ===")
cur.execute("""
    DO $$ DECLARE r RECORD;
    BEGIN
        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
            EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
        END LOOP;
    END $$;
""")
cur.execute("DROP FUNCTION IF EXISTS trigger_set_updated_at() CASCADE;")
cur.execute("DROP EXTENSION IF EXISTS vector CASCADE;")
print("  Done — clean slate")

# Re-create pgcrypto (vector will be created by 005)
cur.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

schema_dir = Path(__file__).resolve().parent / "schema_v2"
schema_files = sorted(schema_dir.glob("*.sql"))

if not schema_files:
    print("ERROR: No SQL files found in scripts/schema_v2/")
    sys.exit(1)

print(f"\n=== Applying {len(schema_files)} schema files ===")
success = 0
failed = 0

for f in schema_files:
    sql = f.read_text(encoding="utf-8")
    try:
        cur.execute(sql)
        print(f"  OK   {f.name}")
        success += 1
    except Exception as e:
        print(f"  FAIL {f.name}: {e}")
        failed += 1

cur.execute(
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
)
table_count = cur.fetchone()[0]

conn.close()
print(f"\nDone: {success} OK, {failed} failed, {table_count} tables total")
