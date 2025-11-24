CREATE TABLE IF NOT EXISTS messages (
    offset INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    text TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    transaction_id TEXT,
    status TEXT NOT NULL DEFAULT 'COMMITTED'
);

