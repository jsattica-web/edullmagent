from mcp.server.fastmcp import FastMCP
from datetime import datetime
from typing import Literal
from dotenv import load_dotenv
from langchain_community.document_loaders import WebBaseLoader

mcp = FastMCP(
    name="tavily_search",
    instructions="Tavily 웹 검색 MCP 서버",
    port=8082
)

@mcp.resource("search://current_date")
def current_date() -> str:
    """현재 날짜를 반환합니다."""
    return f"오늘 날짜는 {datetime.now().isoformat()} 입니다."

@mcp.tool()
def fetch_url(url: str) -> str:
    """URL의 웹페이지 상세 내용을 가져옵니다. url: http(s):// 웹페이지 URL"""
    if not url.startswith(('http://', 'https://')):
        return f'오류: http(s):// URL만 지원합니다. 받은 값: {url}'
    try:
        docs = WebBaseLoader(url).load()
        content = docs[0].page_content if docs else '내용을 가져올 수 없습니다.'
        return content[:5000]
    except Exception as e:
        return f'fetch_url 오류: {type(e).__name__}: {e}'


@mcp.tool()
def web_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    time_range: Literal["day", "week", "month", "year"] | None = None,
    include_raw_content: bool = False,
) -> str:
    """
    query를 검색어로 하는 Tavily 웹 검색을 수행합니다.

    Args:
        query: 검색어
        max_results: 검색 결과 개수 (기본값: 5)
        topic: 검색 토픽. 'general'은 일반 웹, 'news'는 최근 뉴스 기사 중심,
            'finance'는 주식/시장/기업 재무 정보 중심으로 결과를 가져옵니다.
            (기본값: 'general')
        time_range: 결과를 최근 기간으로 제한합니다. 'day'(24시간), 'week'(7일),
            'month'(30일), 'year'(365일) 중 하나. None이면 기간 제한 없음.
            최신 정보가 필요한 질의(예: '오늘', '이번 주')에 사용하세요.
        include_raw_content: True면 각 결과에 페이지 본문 전체(raw_content)를
            포함합니다. 길어서 컨텍스트를 많이 차지하므로, 요약된 content로
            부족하고 본문 그대로의 인용과 정밀 분석이 필요할 때만 True로 켜세요.
            (기본값: False)
    """
    from langchain_tavily import TavilySearch

    load_dotenv('.env', override=True)

    tavily_search = TavilySearch(
        max_results=max_results,
        topic=topic,
        time_range=time_range,
        include_raw_content=include_raw_content,
    )
    tavily_result = tavily_search.invoke(query)

    result = ""
    for item in tavily_result.get('results', []):
        result += f"Title: {item.get('title', 'N/A')}\n"
        result += f"URL: {item.get('url', 'N/A')}\n"
        if item.get('published_date'):
            result += f"Published: {item.get('published_date')}\n"
        result += f"Content: {item.get('content', 'N/A')}\n"
        if include_raw_content and item.get('raw_content'):
            result += f"Raw: {item.get('raw_content')}\n"
        result += "---\n"

    if not result:
        result = "검색 결과가 없습니다."

    return result

if __name__ == "__main__":
    print("Tavily 검색 MCP 서버 시작 (포트: 8082)")
    mcp.run(transport="streamable-http")