-- 013_marketplace.sql
-- Skill marketplace reviews, recommendations, dependencies (REQ-008)

CREATE TABLE skill_reviews (
    review_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id        UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(user_id),
    rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_skill_reviews_updated_at
    BEFORE UPDATE ON skill_reviews
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE UNIQUE INDEX idx_skill_reviews_skill_user ON skill_reviews(skill_id, user_id);
CREATE INDEX idx_skill_reviews_skill_id ON skill_reviews(skill_id);

CREATE TABLE marketplace_recommendations (
    recommendation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    skill_id        UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    score           NUMERIC(5, 4) NOT NULL,
    reason          VARCHAR(200),
    is_dismissed    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_marketplace_recommendations_user_id
    ON marketplace_recommendations(user_id, score DESC)
    WHERE is_dismissed = FALSE;

CREATE TABLE skill_dependencies (
    skill_id        UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    depends_on_id   UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    PRIMARY KEY (skill_id, depends_on_id),
    CHECK (skill_id != depends_on_id)
);
