"""inventory.db에 샘플 재고 데이터를 생성합니다."""
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "inventory.db"

def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
    DROP TABLE IF EXISTS stock_movements;
    DROP TABLE IF EXISTS inventory;
    DROP TABLE IF EXISTS warehouses;
    DROP TABLE IF EXISTS products;

    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY,
        product_name TEXT NOT NULL,
        sku TEXT UNIQUE,
        category TEXT,
        unit_cost REAL,
        reorder_point INTEGER,
        discontinued INTEGER DEFAULT 0
    );

    CREATE TABLE warehouses (
        warehouse_id INTEGER PRIMARY KEY,
        warehouse_name TEXT NOT NULL,
        location TEXT,
        capacity INTEGER
    );

    CREATE TABLE inventory (
        inventory_id INTEGER PRIMARY KEY,
        product_id INTEGER REFERENCES products(product_id),
        warehouse_id INTEGER REFERENCES warehouses(warehouse_id),
        quantity_on_hand INTEGER,
        last_updated DATE
    );

    CREATE TABLE stock_movements (
        movement_id INTEGER PRIMARY KEY,
        product_id INTEGER REFERENCES products(product_id),
        warehouse_id INTEGER REFERENCES warehouses(warehouse_id),
        movement_type TEXT CHECK(movement_type IN ('inbound','outbound','transfer','adjustment')),
        quantity INTEGER,
        movement_date DATE
    );
    """)

    random.seed(42)
    categories = ['전자기기', '의류', '식품', '생활용품', '문구']
    products = [
        ('무선 이어폰', '전자기기', 45000), ('블루투스 스피커', '전자기기', 32000),
        ('USB-C 케이블', '전자기기', 5000), ('노트북 파우치', '전자기기', 18000),
        ('면 티셔츠', '의류', 12000), ('청바지', '의류', 35000),
        ('후드집업', '의류', 28000), ('양말 세트', '의류', 8000),
        ('견과류 세트', '식품', 15000), ('유기농 꿀', '식품', 22000),
        ('핸드크림', '생활용품', 9000), ('텀블러', '생활용품', 16000),
        ('노트 세트', '문구', 6000), ('볼펜 10팩', '문구', 4000),
        ('데스크 매트', '문구', 20000),
    ]

    for i, (name, cat, cost) in enumerate(products, 1):
        disc = 1 if random.random() < 0.1 else 0
        reorder = random.choice([10, 20, 30, 50])
        c.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?)",
                  (i, name, f"SKU-{i:04d}", cat, cost, reorder, disc))

    warehouses = [('서울 물류센터', '서울', 5000), ('부산 물류센터', '부산', 3000), ('대전 물류센터', '대전', 2000)]
    for i, (name, loc, cap) in enumerate(warehouses, 1):
        c.execute("INSERT INTO warehouses VALUES (?,?,?,?)", (i, name, loc, cap))

    inv_id = 0
    for pid in range(1, 16):
        for wid in range(1, 4):
            inv_id += 1
            qty = random.randint(0, 80)
            updated = datetime(2025, 3, 1) + timedelta(days=random.randint(0, 30))
            c.execute("INSERT INTO inventory VALUES (?,?,?,?,?)",
                      (inv_id, pid, wid, qty, updated.strftime('%Y-%m-%d')))

    mv_id = 0
    types = ['inbound', 'outbound', 'outbound', 'outbound', 'transfer', 'adjustment']
    for _ in range(300):
        mv_id += 1
        pid = random.randint(1, 15)
        wid = random.randint(1, 3)
        mt = random.choice(types)
        qty = random.randint(1, 30) if mt == 'inbound' else -random.randint(1, 15)
        mdate = datetime(2025, 1, 1) + timedelta(days=random.randint(0, 90))
        c.execute("INSERT INTO stock_movements VALUES (?,?,?,?,?,?)",
                  (mv_id, pid, wid, mt, qty, mdate.strftime('%Y-%m-%d')))

    conn.commit()
    conn.close()
    print(f"[OK] {DB_PATH} 생성 완료 (상품 {len(products)}개, 창고 {len(warehouses)}개, 이동 {mv_id}건)")

if __name__ == "__main__":
    create_db()
