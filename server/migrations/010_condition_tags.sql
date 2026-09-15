-- 010：病情标签（患者画像与统计维度）
CREATE TABLE IF NOT EXISTS condition_tags (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 标签快照：随事件发生时刻定格，保证跨次住院/用卡的统计归属正确
ALTER TABLE patients    ADD COLUMN condition_tags TEXT NOT NULL DEFAULT '[]';
ALTER TABLE admissions  ADD COLUMN condition_tags TEXT NOT NULL DEFAULT '[]';
ALTER TABLE charges     ADD COLUMN condition_tags TEXT NOT NULL DEFAULT '[]';
ALTER TABLE card_usages ADD COLUMN condition_tags TEXT NOT NULL DEFAULT '[]';
