-- 004：字典（药品与治疗项目统一条目）+ 协定处方 + 治疗项目登记单

-- items：四类条目统一存放，划价/销售/库存都围绕 item id 展开
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT NOT NULL CHECK(category IN ('中药饮片', '中成药', '西药', '治疗项目')),
    name         TEXT NOT NULL,
    unit         TEXT NOT NULL DEFAULT '',
    spec         TEXT NOT NULL DEFAULT '',
    price        REAL NOT NULL DEFAULT 0,
    cost         REAL NOT NULL DEFAULT 0,
    manufacturer TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

-- 协定处方：自家定好的成方可按整方价销售（M4/M5 扣减库存时用组成明细）
CREATE TABLE IF NOT EXISTS formulas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    price      REAL NOT NULL DEFAULT 0,
    note       TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS formula_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    formula_id INTEGER NOT NULL REFERENCES formulas(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES items(id),
    qty        REAL NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_formula_items_formula ON formula_items(formula_id);

-- 治疗项目登记单：登记后为「待收费」，由收费模块（M5）结算
CREATE TABLE IF NOT EXISTS treatment_orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id   INTEGER REFERENCES patients(id),
    patient_name TEXT NOT NULL DEFAULT '',
    owner_type   TEXT NOT NULL CHECK(owner_type IN ('散户', '住院')),
    status       TEXT NOT NULL DEFAULT '待收费' CHECK(status IN ('待收费', '已收费', '已作废')),
    note         TEXT NOT NULL DEFAULT '',
    total        REAL NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_treatment_orders_status ON treatment_orders(status);

CREATE TABLE IF NOT EXISTS treatment_order_lines (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id  INTEGER NOT NULL REFERENCES treatment_orders(id) ON DELETE CASCADE,
    item_id   INTEGER NOT NULL REFERENCES items(id),
    item_name TEXT NOT NULL DEFAULT '',
    unit      TEXT NOT NULL DEFAULT '',
    price     REAL NOT NULL DEFAULT 0,
    qty       REAL NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_treatment_order_lines_order ON treatment_order_lines(order_id);
