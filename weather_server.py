from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

# FastMCP 서버 초기화
mcp = FastMCP("weather")

# 상수
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

# ⚠️ 참고: 아래 verify 인자는 다양한 환경에서의 SSL 인증서 문제를
# 우회하기 위한 학습용 옵션입니다. production에서는 반드시 verify=True (또는 인증서 번들 경로)로 두고,
# 실패하면 환경의 CA 인증서를 점검하세요.
async def make_nws_request(url: str, verify: bool) -> dict[str, Any] | None:
    """NWS API를 통한 기상 데이터 요청 (verify=False는 학습용)"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient(verify=verify) as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

def format_alert(feature: dict) -> str:
    """기상경보 정보를 포맷팅하여 문자열로 반환환"""
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""


@mcp.tool()
async def get_alerts(state: str) -> str:
    """미국 주의 기상 경보 수집

    Args:
        state: 2글자로 구성된 미국 주 코드 (예: CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url, verify=False)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)

@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """특정 위-경도 위치의 일기예보 수집

    Args:
        latitude: 위치의 위도
        longitude: 위치의 경도
    """
    # 예보 그리드 엔드포인트 호출
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url, verify=False)

    if not points_data:
        return "Unable to fetch forecast data for this location."

    # points 응답에서 예보 URL 추출
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url, verify=False)

    if not forecast_data:
        return "Unable to fetch detailed forecast."

    # 기간들을 읽기 쉬운 예보로 포맷팅
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # 다음 5개 기간만 출력
        forecast = f"""
{period['name']}:
Temperature: {period['temperature']}°{period['temperatureUnit']}
Wind: {period['windSpeed']} {period['windDirection']}
Forecast: {period['detailedForecast']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

if __name__ == "__main__":
    # 서버 초기화 및 실행
    print("Starting weather server...")
    mcp.run(transport='stdio')
