---
name: customer-report
description: 고객 분석 보고서 생성 가이드라인과 마크다운 템플릿 (매출 DB + 재고 DB 연계 분석)
metadata:
  type: prompt-bundle
  version: "1.0"
---

## 보고서 구조

보고서는 반드시 아래 섹션 순서를 따릅니다:

1. **요약 (Executive Summary)** -- 핵심 지표 3~5개, 한 문단
2. **매출 분석** -- 기간별 매출 추이, 지역별/등급별 분포
3. **고객 분석** -- 활성 고객 수, CLV 상위 고객, 이탈 위험 고객
4. **재고 현황** -- 재주문 필요 상품, 창고별 재고 분포
5. **권장 액션** -- 데이터 기반 구체적 제안 3~5개

## 스타일 규칙

- 수치에는 반드시 단위 표기 (원, 건, 명)
- 금액은 천 단위 쉼표 사용 (예: 1,234,000원)
- 비율은 소수점 1자리까지 (예: 23.5%)
- 차트/테이블 포함 시 캡션 필수
- 파일명: `report_YYYYMMDD_주제.md`

## Scripts

- `generate.py` -- 매출/재고 DB에서 데이터를 읽어 보고서 초안 생성
  - Usage: `python generate.py --type summary`
  - Options: `--type summary|sales|inventory|full`
