"""매출/재고 DB에서 핵심 지표를 추출하여 보고서 초안을 생성합니다.

Usage:
    python skills/customer_report/generate.py --type summary
    python skills/customer_report/generate.py --type sales
    python skills/customer_report/generate.py --type inventory
    python skills/customer_report/generate.py --type full
"""
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

SALES_DB = Path(__file__).parent.parent / "sales_analytics" / "sales.db"
INVENTORY_DB = Path(__file__).parent.parent / "inventory_management" / "inventory.db"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"


def get_sales_summary() -> str:
    if not SALES_DB.exists():
        return "[ERROR] sales.db가 없습니다. sales_analytics/setup.py를 먼저 실행하세요.\n"
    conn = sqlite3.connect(SALES_DB)
    lines = ["## 매출 분석\n"]

    # 전체 매출
    r = conn.execute("SELECT COUNT(*), SUM(total_amount) FROM orders WHERE status='completed'").fetchone()
    lines.append(f"- 완료 주문: {r[0]:,}건")
    lines.append(f"- 총 매출: {r[1]:,.0f}원")

    # 지역별
    lines.append("\n### 지역별 매출")
    lines.append("| 지역 | 주문 수 | 매출 |")
    lines.append("|------|--------|------|")
    for row in conn.execute("""
        SELECT sales_region, COUNT(*), SUM(total_amount)
        FROM orders WHERE status='completed'
        GROUP BY sales_region ORDER BY SUM(total_amount) DESC
    """):
        lines.append(f"| {row[0]} | {row[1]:,}건 | {row[2]:,.0f}원 |")

    # 등급별 고객 수
    lines.append("\n### 고객 등급 분포")
    for row in conn.execute("SELECT customer_tier, COUNT(*) FROM customers GROUP BY customer_tier ORDER BY COUNT(*) DESC"):
        lines.append(f"- {row[0]}: {row[1]}명")

    conn.close()
    return "\n".join(lines)


def get_inventory_summary() -> str:
    if not INVENTORY_DB.exists():
        return "[ERROR] inventory.db가 없습니다. inventory_management/setup.py를 먼저 실행하세요.\n"
    conn = sqlite3.connect(INVENTORY_DB)
    lines = ["## 재고 현황\n"]

    # 전체 재고 가치
    r = conn.execute("""
        SELECT SUM(i.quantity_on_hand * p.unit_cost)
        FROM inventory i JOIN products p ON i.product_id = p.product_id
        WHERE p.discontinued = 0
    """).fetchone()
    lines.append(f"- 총 재고 가치: {r[0]:,.0f}원")

    # 재주문 필요 상품
    lines.append("\n### 재주문 필요 상품")
    lines.append("| 상품명 | 현재 재고 | 기준 | 부족분 |")
    lines.append("|--------|---------|------|--------|")
    for row in conn.execute("""
        SELECT p.product_name, SUM(i.quantity_on_hand) as total, p.reorder_point,
               (p.reorder_point - SUM(i.quantity_on_hand)) as shortage
        FROM products p JOIN inventory i ON p.product_id = i.product_id
        WHERE p.discontinued = 0
        GROUP BY p.product_id
        HAVING total <= p.reorder_point
        ORDER BY shortage DESC
    """):
        lines.append(f"| {row[0]} | {row[1]}개 | {row[2]}개 | {row[3]}개 |")

    conn.close()
    return "\n".join(lines)


def generate_report(report_type: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    header = f"# 고객 분석 보고서\n\n> 생성일: {today}\n"

    if report_type == "summary":
        return header + "\n" + get_sales_summary() + "\n\n" + get_inventory_summary()
    elif report_type == "sales":
        return header + "\n" + get_sales_summary()
    elif report_type == "inventory":
        return header + "\n" + get_inventory_summary()
    elif report_type == "full":
        body = get_sales_summary() + "\n\n" + get_inventory_summary()
        body += "\n\n## 권장 액션\n\n> (LLM이 위 데이터를 기반으로 작성)\n"
        return header + "\n" + body
    else:
        return f"[ERROR] 알 수 없는 타입: {report_type}. (summary|sales|inventory|full)"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", default="summary", choices=["summary", "sales", "inventory", "full"])
    parser.add_argument("--save", action="store_true", help="outputs/ 폴더에 저장")
    args = parser.parse_args()

    result = generate_report(args.type)
    print(result)

    if args.save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        fname = OUTPUT_DIR / f"report_{datetime.now().strftime('%Y%m%d')}_{args.type}.md"
        fname.write_text(result, encoding="utf-8")
        print(f"\n[OK] {fname} 저장 완료")
