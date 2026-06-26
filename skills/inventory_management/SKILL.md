---
name: inventory-management
description: 재고 관리를 위한 DB 스키마와 SQL 쿼리 스크립트 (products, warehouses, inventory, stock_movements 테이블)
metadata:
  type: cli-tool
  version: "1.0"
---

## Tables

### products
| 컬럼 | 타입 | 설명 |
|------|------|------|
| product_id | INTEGER PK | 상품 ID |
| product_name | TEXT | 상품명 |
| sku | TEXT | SKU 코드 |
| category | TEXT | 카테고리 |
| unit_cost | REAL | 단가 |
| reorder_point | INTEGER | 최소 재고 수준 (이하이면 재주문) |
| discontinued | INTEGER | 단종 여부 (0/1) |

### warehouses
| 컬럼 | 타입 | 설명 |
|------|------|------|
| warehouse_id | INTEGER PK | 창고 ID |
| warehouse_name | TEXT | 창고명 |
| location | TEXT | 위치 |
| capacity | INTEGER | 최대 수용량 |

### inventory
| 컬럼 | 타입 | 설명 |
|------|------|------|
| inventory_id | INTEGER PK | 재고 ID |
| product_id | INTEGER FK | 상품 ID |
| warehouse_id | INTEGER FK | 창고 ID |
| quantity_on_hand | INTEGER | 현재 재고량 |
| last_updated | DATE | 최종 업데이트 |

### stock_movements
| 컬럼 | 타입 | 설명 |
|------|------|------|
| movement_id | INTEGER PK | 이동 ID |
| product_id | INTEGER FK | 상품 ID |
| warehouse_id | INTEGER FK | 창고 ID |
| movement_type | TEXT | inbound / outbound / transfer / adjustment |
| quantity | INTEGER | 수량 (inbound +, outbound -) |
| movement_date | DATE | 이동일 |

## Business Logic

- **Available stock**: quantity_on_hand > 0 인 재고
- **Reorder 필요**: 전체 창고 합산 재고가 reorder_point 이하인 상품
- **Active products only**: discontinued = 0 인 상품만 (단종 분석 시 제외)
- **Stock valuation**: quantity_on_hand * unit_cost

## Scripts

- `setup.py` -- SQLite DB에 샘플 재고 데이터 생성 (`inventory.db`)
- `query.py` -- SQL 쿼리 실행 (`python query.py "SELECT ..."`)
