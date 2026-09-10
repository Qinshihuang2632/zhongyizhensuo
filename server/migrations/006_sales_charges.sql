-- 006：药品销售（含协定方）+ 收费/退费/预交款 + 住院登记 + 操作留痕

CREATE TABLE IF NOT EXISTS sales (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id   INTEGER REFERENCES patients(id),
    patient_name TEXT NOT NULL DEFAULT '',
    owner_type   TEXT NOT NULL CHECK(owner_type IN ('散户', '住院')),
    status       TEXT NOT NULL DEFAULT '待收费' CHECK(status IN ('待收费', '已收费', '已作废', '已退费')),
    note         TEXT NOT NULL DEFAULT '',
    total        REAL NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS sale_lines (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id   INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    line_type TEXT NOT NULL CHECK(line_type IN ('item', 'formula')),
    ref_id    INTEGER NOT NULL,
    item_name TEXT NOT NULL DEFAULT '',
    unit      TEXT NOT NULL DEFAULT '',
    price     REAL NOT NULL DEFAULT 0,
    qty       REAL NOT NULL DEFAULT 1,
    amount    REAL NOT NULL DEFAULT 0,
    cost      REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sale_lines_sale ON sale_lines(sale_id);

CREATE TABLE IF NOT EXISTS charges (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    no_type      TEXT NOT NULL CHECK(no_type IN ('收费', '退费', '预交款', '出院结算')),
    owner_type   TEXT NOT NULL DEFAULT '散户',
    patient_id   INTEGER,
    patient_name TEXT NOT NULL DEFAULT '',
    admission_id INTEGER,
    source_type  TEXT NOT NULL DEFAULT '',
    source_id    INTEGER,
    amount       REAL NOT NULL,
    method       TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_charges_created ON charges(created_at);

CREATE TABLE IF NOT EXISTS admissions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id    INTEGER NOT NULL REFERENCES patients(id),
    patient_name  TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT '在院' CHECK(status IN ('在院', '已出院')),
    note          TEXT NOT NULL DEFAULT '',
    admitted_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    discharged_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    action     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
