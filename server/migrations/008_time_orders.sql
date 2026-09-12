-- 008：治疗单治疗时间（便于按日核查）+ 出院个性化医嘱
ALTER TABLE treatment_orders ADD COLUMN treatment_time TEXT NOT NULL DEFAULT '';
ALTER TABLE admissions ADD COLUMN custom_orders TEXT NOT NULL DEFAULT '';
