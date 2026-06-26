---
name: data-viz
description: 수치 데이터를 matplotlib 파이썬 코드로 차트화한다. 막대/선/원형 등 실제 데이터 시각화가 필요할 때 사용한다.
metadata:
  type: prompt-bundle
---

## 용도

표나 수치 데이터를 matplotlib 코드로 생성해 차트 이미지로 만든다.
생성형 이미지(컨셉/일러스트/표지)가 아니라, 데이터에 근거한 정확한 차트가 필요할 때 쓴다.
컨셉 이미지가 필요하면 `image-gen` 스킬을 대신 로드한다.

## 차트 종류 선택 기준

| 데이터 성격 | 차트 종류 | matplotlib |
|---|---|---|
| 항목 간 크기 비교 | 막대 | `ax.bar` / `ax.barh` |
| 시간에 따른 추세 | 선 | `ax.plot` |
| 전체 대비 구성비 | 원형 | `ax.pie` |
| 두 변수의 관계 | 산점도 | `ax.scatter` |

## 한글 폰트 설정

차트에 한글이 깨지지 않도록 OS에 맞는 폰트를 먼저 지정한다.
윈도우는 `Malgun Gothic`, macOS는 `AppleGothic`, 리눅스는 `NanumGothic`을 쓴다.
마이너스 기호 깨짐도 함께 막는다.

## 실행 방법

아래 템플릿을 채워 `python_repl` 도구로 실행하고, 저장된 PNG 경로를 반환한다.
파일은 `outputs/charts/`에 저장한다.

```python
import matplotlib
matplotlib.use("Agg")  # 화면 없이 파일로만 저장
import matplotlib.pyplot as plt
import platform, os

# OS별 한글 폰트
_font = {"Windows": "Malgun Gothic", "Darwin": "AppleGothic"}.get(platform.system(), "NanumGothic")
plt.rcParams["font.family"] = _font
plt.rcParams["axes.unicode_minus"] = False

os.makedirs("outputs/charts", exist_ok=True)

labels = ["A", "B", "C"]
values = [10, 24, 17]

fig, ax = plt.subplots(figsize=(7, 4))
ax.bar(labels, values, color="#4C72B0")
ax.set_title("제목을 데이터에 맞게 작성")
ax.set_ylabel("값")
fig.tight_layout()

out_path = "outputs/charts/chart_demo.png"
fig.savefig(out_path, dpi=120)
plt.close(fig)
print(out_path)  # 반환할 경로를 출력으로 남긴다
```

## 규칙

- 데이터는 지시에 담겨온 실제 수치만 쓴다. 값을 임의로 지어내지 않는다.
- 파일명은 내용을 알 수 있게 짓는다(예: `region_sales.png`).
- 차트를 저장한 뒤 최종 응답에는 저장 경로 한 줄과 한 줄 설명만 남긴다. 코드 전문을 다시 붙이지 않는다.
