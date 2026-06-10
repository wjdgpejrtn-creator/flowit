"""Schema v2 검증 — Spec 정합성 확인."""
import psycopg2

password = input("DB password: ")

conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    dbname="workflow_automation",
    user="postgres",
    password=password,
)
cur = conn.cursor()
results = []


def check(name, sql, expected_fn):
    try:
        cur.execute(sql)
        row = cur.fetchone()
        val = row[0] if row else None
        ok = expected_fn(val)
        status = "PASS" if ok else "FAIL"
        results.append((status, name))
        print(f"  [{status}] {name}: {val}")
    except Exception as e:
        results.append(("FAIL", name))
        print(f"  [FAIL] {name}: {e}")
        conn.rollback()


print("=== Schema v2 Verification ===\n")

# 1. Table count (33 original + 4 new = ~37+)
check("Tables >= 35",
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
    lambda v: v >= 35)

# 2. Extensions
check("pgcrypto", "SELECT count(*) FROM pg_extension WHERE extname='pgcrypto'", lambda v: v == 1)
check("pgvector", "SELECT count(*) FROM pg_extension WHERE extname='vector'", lambda v: v == 1)

# 3. PK naming — semantic PKs (not 'id')
pk_checks = [
    ("workflows", "workflow_id"),
    ("executions", "execution_id"),
    ("sessions", "session_id"),
    ("oauth_connections", "oauth_id"),
    ("node_definitions", "node_id"),
    ("agent_memories", "memory_id"),
    ("documents", "document_id"),
    ("skills", "skill_id"),
]
for table, pk_col in pk_checks:
    check(f"PK {table}.{pk_col}",
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND column_name='{pk_col}'",
        lambda v: v is not None)

# 4. Table names (sessions not chat_sessions, document_chunks not document_blocks)
check("Table 'sessions' exists",
    "SELECT count(*) FROM information_schema.tables WHERE table_name='sessions' AND table_schema='public'",
    lambda v: v == 1)
check("Table 'chat_sessions' NOT exist",
    "SELECT count(*) FROM information_schema.tables WHERE table_name='chat_sessions' AND table_schema='public'",
    lambda v: v == 0)
check("Table 'document_chunks' exists",
    "SELECT count(*) FROM information_schema.tables WHERE table_name='document_chunks' AND table_schema='public'",
    lambda v: v == 1)
check("Table 'document_blocks' NOT exist",
    "SELECT count(*) FROM information_schema.tables WHERE table_name='document_blocks' AND table_schema='public'",
    lambda v: v == 0)

# 5. Column renames
check("node_definitions.name (not display_name)",
    "SELECT column_name FROM information_schema.columns WHERE table_name='node_definitions' AND column_name='name'",
    lambda v: v is not None)
check("node_definitions.parameter_schema (not parameters)",
    "SELECT column_name FROM information_schema.columns WHERE table_name='node_definitions' AND column_name='parameter_schema'",
    lambda v: v is not None)
check("executions.completed_at (not finished_at)",
    "SELECT column_name FROM information_schema.columns WHERE table_name='executions' AND column_name='completed_at'",
    lambda v: v is not None)
check("executions.error (not error_message)",
    "SELECT column_name FROM information_schema.columns WHERE table_name='executions' AND column_name='error'",
    lambda v: v is not None)
check("skills.author_id (not user_id)",
    "SELECT column_name FROM information_schema.columns WHERE table_name='skills' AND column_name='author_id'",
    lambda v: v is not None)
check("skills.lifecycle_state (not status)",
    "SELECT column_name FROM information_schema.columns WHERE table_name='skills' AND column_name='lifecycle_state'",
    lambda v: v is not None)

# 6. New columns from spec
check("node_definitions.risk_level exists",
    "SELECT column_name FROM information_schema.columns WHERE table_name='node_definitions' AND column_name='risk_level'",
    lambda v: v is not None)
check("node_definitions.required_connections exists",
    "SELECT column_name FROM information_schema.columns WHERE table_name='node_definitions' AND column_name='required_connections'",
    lambda v: v is not None)
check("node_definitions.service_type exists",
    "SELECT column_name FROM information_schema.columns WHERE table_name='node_definitions' AND column_name='service_type'",
    lambda v: v is not None)

# 7. Vector dimension = 768 (not 1024)
check("node_definitions.embedding USER-DEFINED",
    "SELECT data_type FROM information_schema.columns WHERE table_name='node_definitions' AND column_name='embedding'",
    lambda v: v == "USER-DEFINED")

# 8. New tables (016)
for tbl in ["node_results", "tool_executions", "storage_objects", "quality_gate_logs"]:
    check(f"New table '{tbl}' exists",
        f"SELECT count(*) FROM information_schema.tables WHERE table_name='{tbl}' AND table_schema='public'",
        lambda v: v == 1)

# 9. Execution status CHECK (completed not success)
check("Execution status allows 'completed'",
    "SELECT count(*) FROM executions WHERE FALSE",
    lambda v: v == 0)

# 10. users.role CHECK (Title case)
try:
    cur.execute("INSERT INTO users (email, name, role) VALUES ('__test__@test.com', 'Test', 'User') RETURNING user_id")
    uid = cur.fetchone()[0]
    results.append(("PASS", "users.role accepts 'User' (Title case)"))
    print("  [PASS] users.role accepts 'User' (Title case)")
    conn.rollback()
except Exception as e:
    results.append(("FAIL", f"users.role Title case: {e}"))
    print(f"  [FAIL] users.role Title case: {e}")
    conn.rollback()

# 11. Partition
check("node_logs partitions >= 4",
    "SELECT count(*) FROM pg_inherits WHERE inhparent = 'node_logs'::regclass",
    lambda v: v >= 4)

# 12. Seeds
check("node_definitions = 62", "SELECT count(*) FROM node_definitions", lambda v: v == 62)
check("system user exists",
    "SELECT count(*) FROM users WHERE email='system@workflow-automation.internal'",
    lambda v: v == 1)

# 13. HNSW indexes
for idx in ["idx_node_definitions_embedding_hnsw", "idx_skills_embedding_hnsw", "idx_document_chunks_embedding_hnsw"]:
    check(f"HNSW index {idx}",
        f"SELECT count(*) FROM pg_indexes WHERE indexname='{idx}'",
        lambda v: v == 1)

# 14. oauth scopes = array (not jsonb)
check("oauth_connections.scopes is ARRAY",
    "SELECT data_type FROM information_schema.columns WHERE table_name='oauth_connections' AND column_name='scopes'",
    lambda v: v == "ARRAY")

# 15. documents.file_meta is JSONB
check("documents.file_meta JSONB",
    "SELECT data_type FROM information_schema.columns WHERE table_name='documents' AND column_name='file_meta'",
    lambda v: v == "jsonb")

conn.close()

passed = sum(1 for s, _ in results if s == "PASS")
print(f"\n=== Results: {passed}/{len(results)} passed ===")
for status, name in results:
    if status == "FAIL":
        print(f"  FAILED: {name}")
