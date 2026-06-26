---
name: sales-analytics
description: 매출 데이터 분석을 위한 DB 스키마와 SQL 쿼리 스크립트 (customers, orders, order_items 테이블)
metadata:
  type: cli-tool
  version: "1.0"
---

## Tables

### customers
| 컬럼 | 타입 | 설명 |
|------|------|------|
| customer_id | INTEGER PK | 고객 ID |
| name | TEXT | 고객명 |
| email | TEXT | 이메일 |
| signup_date | DATE | 가입일 |
| status | TEXT | active / inactive |
| customer_tier | TEXT | bronze / silver / gold / platinum |

### orders
| 컬럼 | 타입 | 설명 |
|------|------|------|
| order_id | INTEGER PK | 주문 ID |
| customer_id | INTEGER FK | 고객 ID |
| order_date | DATE | 주문일 |
| status | TEXT | pending / completed / cancelled / refunded |
| total_amount | REAL | 총 금액 |
| sales_region | TEXT | north / south / east / west |

### order_items
| 컬럼 | 타입 | 설명 |
|------|------|------|
| item_id | INTEGER PK | 항목 ID |
| order_id | INTEGER FK | 주문 ID |
| product_id | INTEGER | 상품 ID |
| quantity | INTEGER | 수량 |
| unit_price | REAL | 단가 |
| discount_percent | REAL | 할인율 (0-100) |

## Business Logic

- **Active customers**: status = 'active' AND signup_date가 90일 이전
- **Revenue calculation**: status = 'completed'인 주문의 total_amount 합산 (할인 이미 반영됨)
- **Customer Lifetime Value (CLV)**: 고객의 completed 주문 총액
- **High-value orders**: total_amount > 1,000,000

## Scripts

- `setup.py` -- SQLite DB에 샘플 데이터 생성 (`sales.db`)
- `query.py` -- SQL 쿼리 실행 (`python query.py "SELECT ..."`)
