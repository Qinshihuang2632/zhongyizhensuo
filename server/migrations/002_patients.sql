-- 002：患者档案
CREATE TABLE IF NOT EXISTS patients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    gender          TEXT NOT NULL DEFAULT '' CHECK(gender IN ('男', '女', '')),
    birth_date      TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    address         TEXT NOT NULL DEFAULT '',
    allergy_history TEXT NOT NULL DEFAULT '',
    medical_history TEXT NOT NULL DEFAULT '',
    note            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_patients_name  ON patients(name);
CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone);
