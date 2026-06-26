"""inventory.db에 SQL 쿼리를 실행합니다.

Usage: python skills/inventory_management/query.py "SELECT * FROM products LIMIT 5"
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "inventory.db"

def run_query(sql: str) -> str:
    if not DB_PATH.exists():
        return f"[ERROR] {DB_PATH}가 없습니다. 먼저 setup.py를 실행하세요."
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql)
        if cur.description:
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            header = " | ".join(cols)
            sep = "-+-".join("-" * max(len(c), 8) for c in cols)
            lines = [header, sep]
            for row in rows[:50]:
                lines.append(" | ".join(str(row[c])[:20] for c in cols))
            if len(rows) > 50:
                lines.append(f"... ({len(rows)}건 중 50건 표시)")
            return "\n".join(lines)
        else:
            conn.commit()
            return f"[OK] {cur.rowcount}건 영향받음"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python query.py \"SQL문\"")
        sys.exit(1)
    print(run_query(sys.argv[1]))
