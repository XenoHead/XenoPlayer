CREATE TABLE reg_keys (
    id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL COLLATE NOCASE UNIQUE,
    label TEXT,
    machine_id TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX reg_keys_key_hash ON reg_keys(key_hash);
CREATE INDEX reg_keys_active ON reg_keys(active);
