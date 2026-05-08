"""PR #8 SQL 스키마 15개 순서대로 적용."""
import subprocess
import sys
from pathlib import Path

password = input("DB password: ")

schema_dir = Path(__file__).resolve().parents[1] / "database" / "schemas"

result = subprocess.run(
    ["git", "ls-tree", "--name-only", "feature/req-001-database", "database/schemas/"],
    capture_output=True, text=True,
)
schema_files = sorted(
    line.split("/")[-1]
    for line in result.stdout.strip().splitlines()
    if line.endswith(".sql")
)

if not schema_files:
    print("ERROR: SQL 파일을 찾을 수 없습니다. feature/req-001-database 브랜치가 있는지 확인하세요.")
    sys.exit(1)

print(f"적용할 스키마: {len(schema_files)}개\n")

import psycopg2

conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    dbname="workflow_automation",
    user="postgres",
    password=password,
)
conn.autocommit = True
cur = conn.cursor()

success = 0
failed = 0

for fname in schema_files:
    git_result = subprocess.run(
        ["git", "show", f"feature/req-001-database:database/schemas/{fname}"],
        capture_output=True, text=True,
    )
    if git_result.returncode != 0:
        print(f"  SKIP {fname} (git show failed)")
        failed += 1
        continue

    sql = git_result.stdout
    try:
        cur.execute(sql)
        print(f"  OK   {fname}")
        success += 1
    except Exception as e:
        print(f"  FAIL {fname}: {e}")
        failed += 1

cur.execute(
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
)
table_count = cur.fetchone()[0]

conn.close()
print(f"\nDone: {success} OK, {failed} failed, {table_count} tables total")
