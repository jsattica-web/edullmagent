"""
Lab 11 멀티에이전트 실습용 툴 9개 검증 스크립트
각 툴을 독립적으로 테스트하여 결과 확인
"""
import os, sys, subprocess, textwrap
from dotenv import load_dotenv
load_dotenv('env', override=True)

from langchain_core.tools import tool

# ============================================================
# 1. tavily_search
# ============================================================
from langchain_tavily import TavilySearch

@tool
def tavily_search(query: str, max_results: int = 5):
    """Tavily API를 통해 검색 결과를 가져옵니다.
검색 출처 별 최대 3000글자의 텍스트를 가져옵니다.

query: 검색어
max_results : 검색 결과의 수(최소 1, 최대 20, 별도의 요청이 없으면 5로 고정)"""
    tavily = TavilySearch(max_results=max_results)
    search_results = tavily.invoke(query)['results']
    context = ''
    try:
        for doc in search_results:
            doc_content = doc.get('content')
            context += 'TITLE: ' + doc.get('title', 'N/A') + '\nURL:' + doc.get('url') + '\nContent:' + doc_content + '\n---\n'
    except Exception as e:
        context = f'검색 결과를 가져오는데 실패했습니다.: {str(search_results)}\n{str(e)}'
    return context

# ============================================================
# 2. fetch_url
# ============================================================
from langchain_community.document_loaders import WebBaseLoader

@tool
def fetch_url(url: str) -> str:
    """URL의 웹페이지 내용을 가져옵니다.

url: 가져올 웹페이지의 URL"""
    loader = WebBaseLoader(url)
    docs = loader.load()
    content = docs[0].page_content if docs else "내용을 가져올 수 없습니다."
    # 너무 길면 앞부분만 반환
    return content[:5000] if len(content) > 5000 else content

# ============================================================
# 3. run_command
# ============================================================
@tool
def run_command(command: str) -> str:
    """터미널 명령어를 실행합니다. 시스템 정보 확인, 파일 목록 조회 등에 활용합니다.

command: 실행할 셸 명령어"""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        if result.returncode != 0:
            output += f"\n[STDERR] {result.stderr}"
        return output.strip() if output.strip() else "(명령 실행 완료, 출력 없음)"
    except subprocess.TimeoutExpired:
        return "오류: 명령 실행 시간이 30초를 초과했습니다."
    except Exception as e:
        return f"오류: {str(e)}"

# ============================================================
# 4. load_skill
# ============================================================
@tool
def load_skill(skill_name: str) -> str:
    """스킬 디렉토리에서 SKILL.md 파일을 읽어 에이전트에게 전문 지식을 제공합니다.

skill_name: 로드할 스킬의 디렉토리 이름"""
    skill_dirs = ['skills', '.']
    for base in skill_dirs:
        path = os.path.join(base, skill_name, 'SKILL.md')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
    # 사용 가능한 스킬 목록 반환
    available = []
    for base in skill_dirs:
        if os.path.isdir(base):
            for d in os.listdir(base):
                if os.path.exists(os.path.join(base, d, 'SKILL.md')):
                    available.append(d)
    return f"'{skill_name}' 스킬을 찾을 수 없습니다. 사용 가능한 스킬: {available}"

# ============================================================
# 5. write_slack_message
# ============================================================
from slack_sdk import WebClient

@tool
def write_slack_message(message: str, channel: str = "") -> str:
    """Slack 채널에 메시지를 전송합니다.

message: 전송할 메시지 내용
channel: Slack 채널 ID (미지정 시 기본 채널 사용)"""
    token = os.getenv("SLACK_BOT_TOKEN")
    default_channel = os.getenv("SLACK_CHANNEL_ID", "")
    channel = channel or default_channel
    if not token:
        return "오류: SLACK_BOT_TOKEN이 설정되지 않았습니다."
    if not channel:
        return "오류: 채널 ID가 지정되지 않았습니다."
    try:
        client = WebClient(token=token)
        response = client.chat_postMessage(channel=channel, text=message)
        return f"메시지 전송 완료 (채널: {channel}, ts: {response['ts']})"
    except Exception as e:
        return f"Slack 전송 실패: {str(e)}"

# ============================================================
# 6. python_repl
# ============================================================
@tool
def python_repl(code: str) -> str:
    """Python 코드를 실행하고 결과를 반환합니다. 데이터 분석, 계산, 텍스트 처리 등에 활용합니다.

code: 실행할 Python 코드"""
    import io, contextlib
    stdout_capture = io.StringIO()
    local_vars = {}
    try:
        with contextlib.redirect_stdout(stdout_capture):
            exec(code, {"__builtins__": __builtins__}, local_vars)
        output = stdout_capture.getvalue()
        return output.strip() if output.strip() else "(코드 실행 완료, 출력 없음)"
    except Exception as e:
        return f"실행 오류: {type(e).__name__}: {str(e)}"

# ============================================================
# 7. read_file
# ============================================================
@tool
def read_file(file_path: str) -> str:
    """파일의 내용을 읽어 반환합니다.

file_path: 읽을 파일의 경로"""
    BLOCKED = ['env', '.env', 'credentials', '.secret', 'id_rsa', '.pem']
    basename = os.path.basename(file_path)
    if basename in BLOCKED or any(file_path.endswith(b) for b in BLOCKED):
        return f"보안 정책에 의해 '{basename}' 파일은 읽을 수 없습니다."
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if len(content) > 10000:
            return content[:10000] + f"\n\n... (총 {len(content)}자 중 앞 10000자만 표시)"
        return content
    except FileNotFoundError:
        return f"파일을 찾을 수 없습니다: {file_path}"
    except Exception as e:
        return f"파일 읽기 오류: {str(e)}"

# ============================================================
# 8. write_file
# ============================================================
@tool
def write_file(file_path: str, content: str) -> str:
    """파일에 내용을 작성합니다.

file_path: 작성할 파일의 경로
content: 파일에 작성할 내용"""
    try:
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"파일 작성 완료: {file_path} ({len(content)}자)"
    except Exception as e:
        return f"파일 작성 오류: {str(e)}"

# ============================================================
# 9. youtube_transcript
# ============================================================
from youtube_transcript_api import YouTubeTranscriptApi

@tool
def youtube_transcript(video_url: str, languages: list[str] = ["ko", "en"]) -> str:
    """YouTube 동영상의 자막을 가져옵니다.

video_url: YouTube 동영상 URL 또는 video ID
languages: 자막 언어 우선순위 (기본: 한국어 > 영어)"""
    # URL에서 video ID 추출
    video_id = video_url
    if "youtube.com" in video_url:
        video_id = video_url.split("v=")[-1].split("&")[0]
    elif "youtu.be" in video_url:
        video_id = video_url.split("/")[-1].split("?")[0]

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=languages)
        text = " ".join([entry.text for entry in transcript.snippets])
        if len(text) > 5000:
            return text[:5000] + f"\n\n... (총 {len(text)}자 중 앞 5000자만 표시)"
        return text
    except Exception as e:
        return f"자막 가져오기 실패: {str(e)}"


# ============================================================
# 테스트 실행
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Lab 11 툴 검증 테스트")
    print("=" * 60)

    tests = {
        "1. tavily_search": lambda: tavily_search.invoke({"query": "LangGraph multi agent 2025", "max_results": 2}),
        "2. fetch_url": lambda: fetch_url.invoke({"url": "https://python.langchain.com/docs/introduction/"}),
        "3. run_command": lambda: run_command.invoke({"command": "python --version && echo hello"}),
        "4. load_skill": lambda: load_skill.invoke({"skill_name": "nonexistent_test"}),
        "5. write_slack_message": None,  # 실제 전송은 스킵
        "6. python_repl": lambda: python_repl.invoke({"code": "import math\nprint(f'pi = {math.pi:.4f}')\nprint(f'2^10 = {2**10}')"}),
        "7. read_file": lambda: read_file.invoke({"file_path": "env"}),
        "8. write_file": lambda: write_file.invoke({"file_path": "_test_output/test.txt", "content": "테스트 파일입니다."}),
        "9. youtube_transcript": lambda: youtube_transcript.invoke({"video_url": "https://www.youtube.com/watch?v=9vM4p9NN0Ts"}),
    }

    for name, test_fn in tests.items():
        print(f"\n{'─' * 60}")
        print(f"▶ {name}")
        print(f"{'─' * 60}")
        if test_fn is None:
            print("  ⏭ SKIP (실제 Slack 전송 방지)")
            continue
        try:
            result = test_fn()
            # 결과를 200자까지만 표시
            preview = str(result)[:300]
            print(f"  ✅ 성공\n  {preview}")
        except Exception as e:
            print(f"  ❌ 실패: {type(e).__name__}: {e}")

    # 테스트 파일 정리
    import shutil
    if os.path.exists("_test_output"):
        shutil.rmtree("_test_output")
        print("\n\n🧹 테스트 파일 정리 완료")

    print(f"\n{'=' * 60}")
    print("테스트 완료")
    print(f"{'=' * 60}")
