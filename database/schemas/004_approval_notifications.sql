-- 004_approval_notifications.sql
-- Workflow/skill approval requests and user notifications

-- ============================================================
-- approvals
-- ============================================================
CREATE TABLE approvals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID REFERENCES workflows(id),
    skill_id        UUID,
    requester_id    UUID NOT NULL REFERENCES users(id),
    approver_id     UUID REFERENCES users(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    comment         TEXT,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX idx_approvals_requester_id ON approvals(requester_id);
CREATE INDEX idx_approvals_approver_id ON approvals(approver_id);
CREATE INDEX idx_approvals_status ON approvals(status) WHERE status = 'pending';

-- ============================================================
-- notifications
-- ============================================================
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    type            VARCHAR(50) NOT NULL,
    title           VARCHAR(300) NOT NULL,
    body            TEXT,
    metadata        JSONB DEFAULT '{}'::JSONB,
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_id_unread
    ON notifications(user_id, created_at DESC) WHERE is_read = FALSE;
