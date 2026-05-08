"""Seed data for schema v2 (Spec-aligned column names)."""
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

# 1) system_user (updated FK column name: user_id)
cur.execute("""
    INSERT INTO users (user_id, email, name, role, department, is_active)
    VALUES (
        '00000000-0000-0000-0000-000000000001',
        'system@workflow-automation.internal',
        'System',
        'Admin',
        'Platform',
        TRUE
    ) ON CONFLICT (email) DO NOTHING
""")
print("OK  system_user")

# 2) node_definitions (54종, updated column names)
result = subprocess.run(
    ["git", "show", "feature/req-001-database:database/seeds/node_definitions.json"],
    capture_output=True, encoding="utf-8",
)
nodes = json.loads(result.stdout)

for node in nodes:
    cur.execute(
        """
        INSERT INTO node_definitions (node_type, name, category, description, parameter_schema, risk_level, is_mvp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (node_type) DO NOTHING
        """,
        (
            node["node_type"],
            node["display_name"],
            node["category"],
            node.get("description", ""),
            json.dumps(node.get("parameters", {})),
            "Low",
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
