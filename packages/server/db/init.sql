-- Claude Poker — PostgreSQL schema

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
    pot             INTEGER NOT NULL,
    community_cards TEXT NOT NULL,
    timestamp       DOUBLE PRECISION NOT NULL
);
CREATE INDEX idx_hand_summaries_game_id ON hand_summaries (game_id);

CREATE TABLE player_stats (
    username        TEXT PRIMARY KEY,
    games_played    INTEGER NOT NULL DEFAULT 0,
    hands_played    INTEGER NOT NULL DEFAULT 0,
    hands_won       INTEGER NOT NULL DEFAULT 0,
    total_winnings  BIGINT NOT NULL DEFAULT 0,
    biggest_pot_won INTEGER NOT NULL DEFAULT 0
);
