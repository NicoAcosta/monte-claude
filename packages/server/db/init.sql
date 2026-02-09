-- Monteclaude — PostgreSQL schema

CREATE TABLE accounts (
    username    TEXT PRIMARY KEY,
    key_hash    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_accounts_key_hash ON accounts (key_hash);

CREATE TABLE balances (
    username        TEXT PRIMARY KEY,
    amount          BIGINT NOT NULL DEFAULT 0,
    last_claim_at   TEXT NOT NULL DEFAULT ''
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

CREATE TABLE player_stats (
    username        TEXT PRIMARY KEY,
    games_played    INTEGER NOT NULL DEFAULT 0,
    hands_played    INTEGER NOT NULL DEFAULT 0,
    hands_won       INTEGER NOT NULL DEFAULT 0,
    total_winnings  BIGINT NOT NULL DEFAULT 0,
    biggest_pot_won NUMERIC NOT NULL DEFAULT 0
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
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE player_token_stats (
    username        TEXT NOT NULL,
    token_symbol    TEXT NOT NULL DEFAULT 'chips',
    total_winnings  NUMERIC NOT NULL DEFAULT 0,
    biggest_pot_won NUMERIC NOT NULL DEFAULT 0,
    hands_played    INTEGER NOT NULL DEFAULT 0,
    hands_won       INTEGER NOT NULL DEFAULT 0,
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
