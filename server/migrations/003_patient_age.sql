-- 003：患者增加年龄字段（直接登记年龄；出生日期改为选填）
ALTER TABLE patients ADD COLUMN age INTEGER NOT NULL DEFAULT 0;
