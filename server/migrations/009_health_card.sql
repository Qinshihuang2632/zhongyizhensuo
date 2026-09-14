-- 009：保健卡（治愈患者权益卡）
-- 持卡信息内置于患者档案：card_since 为获卡日期（空=无卡）
ALTER TABLE patients ADD COLUMN card_since TEXT NOT NULL DEFAULT '';

-- 每轮权益窗口的使用登记（每轮仅一次：自开始日起连续 7 个自然日）
CREATE TABLE IF NOT EXISTS card_usages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id   INTEGER NOT NULL REFERENCES patients(id),
    window_index INTEGER NOT NULL,
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(patient_id, window_index)
);

-- 提醒确认（确认前每次登录持续提醒，跨重启生效）
CREATE TABLE IF NOT EXISTS card_reminders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id   INTEGER NOT NULL REFERENCES patients(id),
    window_index INTEGER NOT NULL,
    confirmed_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(patient_id, window_index)
);
