-- 001：基线表。settings 以键值对存放系统参数（诊所信息、票头、固化医嘱、备份份数等）。
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
