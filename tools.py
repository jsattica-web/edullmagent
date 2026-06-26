"""tools.py

코스 전반에서 에이전트가 사용하는 표준 도구 모음입니다.
Tool Calling 실습에서 배운 @tool 정의 방식을 그대로 따르며,
에이전트 구현(create_agent) 실습부터 from tools import ... 로 가져와 재사용합니다.

import 시 .env를 읽어 TAVILY_API_KEY 등을 로드합니다.
web_search는 Tavily 검색 API를 사용하므로 TAVILY_API_KEY가 필요합니다.
키가 없으면 안내 메시지를 돌려주는 대체 도구로 동작합니다.

사용 예시
    from tools import DEFAULT_TOOLS, calculator
    from langchain.agents import create_agent

    agent = create_agent('gpt-5.2', tools=DEFAULT_TOOLS)
"""

from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.tools import tool

for _candidate in (".env", "env", "environment"):
    if os.path.exists(_candidate):
        load_dotenv(_candidate, override=True)
        break


@tool
def calculator(expression: str) -> str:
    """수학 계산식을 입력받아 계산 결과를 반환합니다.
    사칙연산, 거듭제곱(**) 등 Python 수식을 지원합니다.

    Args:
        expression: 계산할 수식 (예: '3 + 5 * 2', '2 ** 10')
    """
    try:
        allowed_chars = set('0123456789+-*/.()**% ')
        if not all(c in allowed_chars for c in expression):
            return f'허용되지 않는 문자가 포함되어 있습니다: {expression}'
        # 주의: 교육용 코드입니다. 프로덕션에서는 ast.literal_eval 또는 numexpr을 사용하세요.
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f'계산 오류: {str(e)}'


@tool
def get_current_datetime() -> str:
    """현재 날짜와 시간을 반환합니다."""
    now = datetime.now()
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    weekday = weekdays[now.weekday()]
    return f"{now.strftime('%Y-%m-%d %H:%M:%S')} ({weekday}요일)"


@tool
def text_analyzer(text: str) -> str:
    """텍스트를 분석하여 글자 수, 단어 수, 문장 수 등의 통계를 반환합니다.

    Args:
        text: 분석할 텍스트
    """
    char_count = len(text)
    char_no_space = len(text.replace(' ', ''))
    word_count = len(text.split())
    sentence_count = text.count('.') + text.count('!') + text.count('?')
    if sentence_count == 0:
        sentence_count = 1
    return (
        f'텍스트 분석 결과:\n'
        f'  - 전체 글자 수: {char_count}자\n'
        f'  - 공백 제외 글자 수: {char_no_space}자\n'
        f'  - 단어 수: {word_count}개\n'
        f'  - 문장 수: {sentence_count}개'
    )


_notes = {}


@tool
def save_note(title: str, content: str) -> str:
    """메모를 저장합니다. 제목과 내용을 입력받아 저장하고, 저장된 메모 목록을 반환합니다.

    Args:
        title: 메모 제목
        content: 메모 내용
    """
    _notes[title] = content
    note_list = ', '.join(_notes.keys())
    return f"메모 '{title}'이(가) 저장되었습니다. 현재 저장된 메모: [{note_list}]"


@tool
def get_notes() -> str:
    """저장된 모든 메모를 조회합니다."""
    if not _notes:
        return '저장된 메모가 없습니다.'
    result = '저장된 메모 목록:\n'
    for title, content in _notes.items():
        result += f'  - [{title}]: {content}\n'
    return result.strip()


# web_search: Tavily 검색 도구. 외부 검색 API라 TAVILY_API_KEY가 필요합니다.
# 키가 없으면 안내 메시지를 돌려주는 대체 도구로 두어 import는 항상 성공하게 합니다.
from langchain_tavily import TavilySearch

if os.environ.get('TAVILY_API_KEY'):
    web_search = TavilySearch(max_results=3)
else:
    @tool
    def web_search(query: str) -> str:
        """웹에서 최신 정보를 검색합니다. (TAVILY_API_KEY 설정 시 동작)

        Args:
            query: 검색어
        """
        return 'TAVILY_API_KEY가 설정되지 않아 웹 검색을 사용할 수 없습니다. .env에 키를 추가하세요.'


# 표준 도구 묶음. create_agent(tools=DEFAULT_TOOLS) 또는 build_agent에서 그대로 씁니다.
DEFAULT_TOOLS = [
    web_search,
    calculator,
    get_current_datetime,
    text_analyzer,
    save_note,
    get_notes,
]
