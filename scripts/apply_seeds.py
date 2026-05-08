"""PR #8 시드 데이터 적용 (system_user + 54종 node_definitions)."""
import json
import subprocess
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

# 1) system_user
result = subprocess.run(
    ["git", "show", "feature/req-001-database:database/seeds/system_user.sql"],
    capture_output=True, encoding="utf-8",
)
cur.execute(result.stdout)
print("OK  system_user")

# 2) node_definitions (54종)
result = subprocess.run(
    ["git", "show", "feature/req-001-database:database/seeds/node_definitions.json"],
    capture_output=True, encoding="utf-8",
)
nodes = json.loads(result.stdout)

for node in nodes:
    cur.execute(
        """
        INSERT INTO node_definitions (node_type, category, display_name, description, parameters, is_mvp)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (node_type) DO NOTHING
        """,
        (
            node["node_type"],
            node["category"],
            node["display_name"],
            node.get("description", ""),
            json.dumps(node.get("parameters", {})),
            node.get("is_mvp", False),
        ),
    )

cur.execute("SELECT count(*) FROM node_definitions")
count = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM users")
user_count = cur.fetchone()[0]

conn.close()
print(f"OK  node_definitions: {count}개")
print(f"OK  users: {user_count}개")
print("Seeds done!")
