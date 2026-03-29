CREATE TABLE IF NOT EXISTS plans (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    price_monthly   INTEGER NOT NULL,
    credits_monthly INTEGER NOT NULL,
    searches_daily  INTEGER NOT NULL,
    llm_model       TEXT NOT NULL,
    features        JSONB DEFAULT '{}',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO plans (name, display_name, price_monthly, credits_monthly, searches_daily, llm_model, features)
VALUES
    ('free',  'Free',  0,      0,   10,  'none',                  '{"semantic_search":false,"pdf_access":false,"ai_answers":false}'),
    ('basic', 'Basic', 29900,  50,  100, 'claude-haiku-4-5-20251001', '{"semantic_search":true,"pdf_access":true,"ai_answers":true}'),
    ('pro',   'Pro',   99900,  500, -1,  'claude-sonnet-4-6',     '{"semantic_search":true,"pdf_access":true,"ai_answers":true,"api_access":true}')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    full_name       TEXT,
    phone           TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    is_admin        BOOLEAN DEFAULT FALSE,
    plan_id         INTEGER REFERENCES plans(id) DEFAULT 1,
    credits_used    INTEGER DEFAULT 0,
    credits_reset   TIMESTAMPTZ DEFAULT NOW(),
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id             INTEGER NOT NULL REFERENCES plans(id),
    status              TEXT NOT NULL DEFAULT 'active',
    razorpay_order_id   TEXT,
    razorpay_payment_id TEXT,
    amount_paid         INTEGER,
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    expires_at          TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    model_used  TEXT,
    credits     INTEGER DEFAULT 0,
    query       TEXT,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reset_tokens (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email        ON users(email);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_user         ON usage_logs(user_id);

SELECT 'SaaS schema ready.' AS status;
