-- System user for automated operations (seeded on first deploy)
INSERT INTO users (user_id, email, name, role, department, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'system@workflow-automation.internal',
    'System',
    'Admin',
    'Platform',
    TRUE
) ON CONFLICT (email) DO NOTHING;
