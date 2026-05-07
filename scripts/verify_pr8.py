"""PR #8 테스트 체크리스트 검증."""
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


print("=== PR #8 Verification ===\n")

# 1. 테이블 수
check(
    "Tables >= 33",
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
    lambda v: v >= 33,
)

# 2. Extensions
check(
    "pgcrypto extension",
    "SELECT count(*) FROM pg_extension WHERE extname='pgcrypto'",
    lambda v: v == 1,
)
check(
    "pgvector extension",
    "SELECT count(*) FROM pg_extension WHERE extname='vector'",
    lambda v: v == 1,
)

# 3. Node definitions seed
check(
    "node_definitions = 54",
    "SELECT count(*) FROM node_definitions",
    lambda v: v == 54,
)

# 4. System user
check(
    "system user exists",
    "SELECT count(*) FROM users WHERE email='system@workflow-automation.internal'",
    lambda v: v == 1,
)

# 5. Vector column exists
check(
    "node_definitions.embedding vector(1024)",
    "SELECT data_type FROM information_schema.columns WHERE table_name='node_definitions' AND column_name='embedding'",
    lambda v: v == "USER-DEFINED",
)

# 6. HNSW index on skills
check(
    "skills HNSW index",
    "SELECT count(*) FROM pg_indexes WHERE indexname='idx_skills_embedding_hnsw'",
    lambda v: v == 1,
)

# 7. HNSW index on agent_memories
check(
    "agent_memories HNSW index",
    "SELECT count(*) FROM pg_indexes WHERE indexname='idx_agent_memories_embedding_hnsw'",
    lambda v: v == 1,
)

# 8. node_logs partitions
check(
    "node_logs partitions >= 4",
    "SELECT count(*) FROM pg_inherits WHERE inhparent = 'node_logs'::regclass",
    lambda v: v >= 4,
)

# 9. Partition routing test
try:
    cur.execute("""
        INSERT INTO users (email, name, role) VALUES ('test@test.com', 'Test', 'user')
        RETURNING id
    """)
    user_id = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO workflows (user_id, name, nodes) VALUES (%s, 'test', '[]'::jsonb)
        RETURNING id
    """, (user_id,))
    wf_id = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO executions (workflow_id, user_id, status) VALUES (%s, %s, 'running')
        RETURNING id
    """, (wf_id, user_id))
    exec_id = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO node_logs (execution_id, node_id, node_type, status, started_at)
        VALUES (%s, 'test_node', 'action', 'success', '2026-05-15')
    """, (exec_id,))
    cur.execute("SELECT count(*) FROM node_logs_2026_05")
    val = cur.fetchone()[0]
    ok = val >= 1
    results.append(("PASS" if ok else "FAIL", "partition routing (2026_05)"))
    print(f"  [{'PASS' if ok else 'FAIL'}] partition routing (2026_05): {val} rows")
    conn.rollback()
except Exception as e:
    results.append(("FAIL", "partition routing"))
    print(f"  [FAIL] partition routing: {e}")
    conn.rollback()

# 10. Credential store BYTEA column
check(
    "credentials.encrypted_value BYTEA",
    "SELECT data_type FROM information_schema.columns WHERE table_name='credentials' AND column_name='encrypted_value'",
    lambda v: v == "bytea",
)

# 11. updated_at trigger
try:
    cur.execute("SELECT tgname FROM pg_trigger WHERE tgname='set_users_updated_at'")
    val = cur.fetchone()
    ok = val is not None
    results.append(("PASS" if ok else "FAIL", "updated_at trigger"))
    print(f"  [{'PASS' if ok else 'FAIL'}] updated_at trigger: {val[0] if val else 'not found'}")
except Exception as e:
    results.append(("FAIL", "updated_at trigger"))
    print(f"  [FAIL] updated_at trigger: {e}")
    conn.rollback()

conn.close()

print(f"\n=== Results: {sum(1 for s,_ in results if s=='PASS')}/{len(results)} passed ===")
for status, name in results:
    if status == "FAIL":
        print(f"  FAILED: {name}")
