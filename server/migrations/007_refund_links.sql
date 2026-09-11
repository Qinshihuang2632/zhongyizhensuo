-- 007：退费状态支持 + 收费-单据关联表
-- SQLite 无法修改 CHECK 约束，重建 treatment_orders / prescriptions 两表，
-- 在状态枚举中加入「已退费」（散户退费不再触发 500）。

PRAGMA foreign_keys=OFF;

CREATE TABLE treatment_orders_new (
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
INSERT INTO treatment_orders_new SELECT * FROM treatment_orders;
DROP TABLE treatment_orders;
ALTER TABLE treatment_orders_new RENAME TO treatment_orders;

CREATE TABLE prescriptions_new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id     INTEGER REFERENCES patients(id),
    patient_name   TEXT NOT NULL DEFAULT '',
    owner_type     TEXT NOT NULL CHECK(owner_type IN ('散户', '住院')),
    status         TEXT NOT NULL DEFAULT '待付药' CHECK(status IN ('待付药', '已付药', '已收费', '已作废', '已退费')),
    doses          INTEGER NOT NULL DEFAULT 1,
    usage_method   TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    per_dose_total REAL NOT NULL DEFAULT 0,
    total          REAL NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO prescriptions_new SELECT * FROM prescriptions;
DROP TABLE prescriptions;
ALTER TABLE prescriptions_new RENAME TO prescriptions;

PRAGMA foreign_keys=ON;

-- 一张收费/退费记录可对应多张业务单据（合并收款/合并退费）
CREATE TABLE IF NOT EXISTS charge_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    charge_id   INTEGER NOT NULL REFERENCES charges(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id   INTEGER NOT NULL,
    amount      REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_charge_links_charge ON charge_links(charge_id);
CREATE INDEX IF NOT EXISTS idx_charge_links_source ON charge_links(source_type, source_id);
