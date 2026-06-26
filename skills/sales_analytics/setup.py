"""sales.db에 샘플 매출 데이터를 생성합니다."""
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "sales.db"

def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
    DROP TABLE IF EXISTS order_items;
    DROP TABLE IF EXISTS orders;
    DROP TABLE IF EXISTS customers;

    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        signup_date DATE,
        status TEXT CHECK(status IN ('active','inactive')),
        customer_tier TEXT CHECK(customer_tier IN ('bronze','silver','gold','platinum'))
    );

    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(customer_id),
        order_date DATE,
        status TEXT CHECK(status IN ('pending','completed','cancelled','refunded')),
        total_amount REAL,
        sales_region TEXT CHECK(sales_region IN ('north','south','east','west'))
    );

    CREATE TABLE order_items (
        item_id INTEGER PRIMARY KEY,
        order_id INTEGER REFERENCES orders(order_id),
        product_id INTEGER,
        quantity INTEGER,
        unit_price REAL,
        discount_percent REAL DEFAULT 0
    );
    """)

    random.seed(42)
    tiers = ['bronze', 'silver', 'gold', 'platinum']
    regions = ['north', 'south', 'east', 'west']
    statuses = ['completed', 'completed', 'completed', 'pending', 'cancelled', 'refunded']
    names = ['김민수','이영희','박지훈','최수진','정대현','한소영','윤재호','송미라','임태우','오하늘',
             '강서준','배유진','조현우','신다은','류성민','문지아','황동혁','전예린','권도윤','나은서']

    # 고객 20명
    base_date = datetime(2024, 1, 1)
    for i in range(1, 21):
        signup = base_date + timedelta(days=random.randint(0, 365))
        tier = random.choices(tiers, weights=[40, 30, 20, 10])[0]
        status = 'active' if random.random() < 0.8 else 'inactive'
        c.execute("INSERT INTO customers VALUES (?,?,?,?,?,?)",
                  (i, names[i-1], f"user{i}@example.com", signup.strftime('%Y-%m-%d'), status, tier))

    # 주문 200건
    order_id = 0
    for _ in range(200):
        order_id += 1
        cust = random.randint(1, 20)
        odate = base_date + timedelta(days=random.randint(0, 500))
        st = random.choice(statuses)
        region = random.choice(regions)
        # 항목 1~5개
        items = []
        for _ in range(random.randint(1, 5)):
            qty = random.randint(1, 10)
            price = random.choice([9900, 29000, 49000, 99000, 159000, 299000])
            disc = random.choice([0, 0, 0, 5, 10, 15, 20])
            items.append((qty, price, disc))
        total = sum(q * p * (1 - d/100) for q, p, d in items)
        c.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)",
                  (order_id, cust, odate.strftime('%Y-%m-%d'), st, total, region))
        for qty, price, disc in items:
            c.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount_percent) VALUES (?,?,?,?,?)",
                      (order_id, random.randint(100, 120), qty, price, disc))

    conn.commit()
    conn.close()
    print(f"[OK] {DB_PATH} 생성 완료 (고객 20명, 주문 {order_id}건)")

if __name__ == "__main__":
    create_db()
