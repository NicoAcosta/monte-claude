-- Monteclaude — PostgreSQL schema

CREATE TABLE accounts (
    username    TEXT PRIMARY KEY,
    key_hash    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_accounts_key_hash ON accounts (key_hash);

CREATE TABLE balances (
    username        TEXT PRIMARY KEY REFERENCES accounts(username),
    amount          BIGINT NOT NULL DEFAULT 0,
    last_claim_at   TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CHECK (amount >= 0)
);

CREATE TABLE game_events (
    id              BIGSERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    timestamp       DOUBLE PRECISION NOT NULL,
    hand_number     INTEGER NOT NULL,
    data            TEXT NOT NULL,
    sequence        INTEGER NOT NULL
);
CREATE INDEX idx_game_events_game_id ON game_events (game_id);
CREATE INDEX idx_game_events_timestamp ON game_events (timestamp);

CREATE TABLE hand_summaries (
    id              BIGSERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL,
    hand_number     INTEGER NOT NULL,
    dealer_id       INTEGER NOT NULL,
    player_ids      TEXT NOT NULL,
    winner_ids      TEXT NOT NULL,
    pot             NUMERIC NOT NULL,
    community_cards TEXT NOT NULL,
    timestamp       DOUBLE PRECISION NOT NULL,
    winner_names    TEXT NOT NULL DEFAULT '[]',
    winning_cards   TEXT NOT NULL DEFAULT '{}',
    result_type     TEXT NOT NULL DEFAULT 'fold',
    token_symbol    TEXT
);
CREATE INDEX idx_hand_summaries_game_id ON hand_summaries (game_id);
CREATE INDEX idx_hand_summaries_timestamp ON hand_summaries (timestamp DESC);

CREATE TABLE player_stats (
    username        TEXT PRIMARY KEY REFERENCES accounts(username),
    games_played    INTEGER NOT NULL DEFAULT 0,
    hands_played    INTEGER NOT NULL DEFAULT 0,
    hands_won       INTEGER NOT NULL DEFAULT 0,
    total_winnings  BIGINT NOT NULL DEFAULT 0,
    biggest_pot_won NUMERIC NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE game_metadata (
    game_id         SERIAL PRIMARY KEY,
    mode            TEXT NOT NULL DEFAULT 'offchain',
    buy_in          NUMERIC NOT NULL DEFAULT 0,
    max_players     INTEGER NOT NULL DEFAULT 0,
    token           TEXT,
    token_decimals  INTEGER NOT NULL DEFAULT 0,
    token_symbol    TEXT,
    player_count    INTEGER NOT NULL DEFAULT 0,
    player_names    TEXT[] NOT NULL DEFAULT '{}',
    started         BOOLEAN NOT NULL DEFAULT FALSE,
    game_over       BOOLEAN NOT NULL DEFAULT FALSE,
    winner          TEXT,
    hand_number     INTEGER NOT NULL DEFAULT 0,
    funded          BOOLEAN NOT NULL DEFAULT FALSE,
    escrow_address  TEXT,
    action_timeout  REAL,
    extensions_per_player INTEGER,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    CHECK (buy_in >= 0),
    CHECK (max_players >= 0)
);
CREATE INDEX idx_game_metadata_created_at ON game_metadata (created_at DESC);

CREATE TABLE player_token_stats (
    username        TEXT NOT NULL REFERENCES accounts(username),
    token_symbol    TEXT NOT NULL DEFAULT 'chips',
    total_winnings  NUMERIC NOT NULL DEFAULT 0,
    biggest_pot_won NUMERIC NOT NULL DEFAULT 0,
    hands_played    INTEGER NOT NULL DEFAULT 0,
    hands_won       INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (username, token_symbol)
);

CREATE TABLE streams (
    id              SERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL,
    host_username   TEXT NOT NULL,
    title           TEXT NOT NULL,
    commentary_text TEXT,
    created_at      REAL NOT NULL,
    UNIQUE(game_id, host_username)
);

-- ── Audit tables (append-only) ──────────────────────────

CREATE TABLE balance_history (
    id              BIGSERIAL PRIMARY KEY,
    username        TEXT NOT NULL REFERENCES accounts(username),
    amount          BIGINT NOT NULL,
    balance_after   BIGINT NOT NULL,
    reason          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_balance_history_username ON balance_history (username);
CREATE INDEX idx_balance_history_created_at ON balance_history (created_at);

CREATE TABLE auth_events (
    id              BIGSERIAL PRIMARY KEY,
    username        TEXT,
    event_type      TEXT NOT NULL,
    ip_address      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_auth_events_created_at ON auth_events (created_at);

CREATE TABLE escrow_operations (
    id              BIGSERIAL PRIMARY KEY,
    game_id         INTEGER NOT NULL,
    operation       TEXT NOT NULL,
    escrow_address  TEXT,
    details         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_escrow_operations_game_id ON escrow_operations (game_id);
