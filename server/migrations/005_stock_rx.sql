-- 005：药库批次库存 + 出入库流水 + 入库单 + 中药处方

ALTER TABLE items ADD COLUMN min_stock REAL NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS stock_batches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL REFERENCES items(id),
    qty        REAL NOT NULL DEFAULT 0,
    cost       REAL NOT NULL DEFAULT 0,
    batch_no   TEXT NOT NULL DEFAULT '',
    expiry     TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_batches_item ON stock_batches(item_id);

CREATE TABLE IF NOT EXISTS stock_moves (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER NOT NULL REFERENCES items(id),
    direction  TEXT NOT NULL CHECK(direction IN ('入库', '出库', '退回', '调整')),
    qty        REAL NOT NULL,
    cost       REAL NOT NULL DEFAULT 0,
    ref_type   TEXT NOT NULL DEFAULT '',
    ref_no     TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_moves_item ON stock_moves(item_id);

CREATE TABLE IF NOT EXISTS stock_ins (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier   TEXT NOT NULL DEFAULT '',
    note       TEXT NOT NULL DEFAULT '',
    total_cost REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS stock_in_lines (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_in_id INTEGER NOT NULL REFERENCES stock_ins(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES items(id),
    item_name  TEXT NOT NULL DEFAULT '',
    unit       TEXT NOT NULL DEFAULT '',
    qty        REAL NOT NULL,
    cost       REAL NOT NULL DEFAULT 0,
    batch_no   TEXT NOT NULL DEFAULT '',
    expiry     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_stock_in_lines_in ON stock_in_lines(stock_in_id);

CREATE TABLE IF NOT EXISTS prescriptions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id     INTEGER REFERENCES patients(id),
    patient_name   TEXT NOT NULL DEFAULT '',
    owner_type     TEXT NOT NULL CHECK(owner_type IN ('散户', '住院')),
    status         TEXT NOT NULL DEFAULT '待付药' CHECK(status IN ('待付药', '已付药', '已收费', '已作废')),
    doses          INTEGER NOT NULL DEFAULT 1,
    usage_method   TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    per_dose_total REAL NOT NULL DEFAULT 0,
    total          REAL NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS prescription_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prescription_id INTEGER NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    item_name       TEXT NOT NULL DEFAULT '',
    unit            TEXT NOT NULL DEFAULT '',
    price           REAL NOT NULL DEFAULT 0,
    qty             REAL NOT NULL DEFAULT 0,
    cost            REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_rx_lines_rx ON prescription_lines(prescription_id);
