# %% [markdown]
# # 국민연금 법령 Agent 버전
#
# 기존 pesion_law_graph.py는 LangGraph StateGraph로 Self-RAG 흐름을 직접 구성했습니다.
# 이 파일은 같은 목적을 create_agent() 기반 Agent 구조로 단순화한 버전입니다.
#
# 핵심 변경:
# - retrieve 노드 -> search_pension_law tool
# - rewrite 노드 -> system_prompt의 용어 사전 지시
# - hallucination/helpfulness 검증 -> system_prompt의 답변 규칙 + 근거 기반 응답 지시
# - 기존 graph.invoke({"query": ...}) 호출 호환을 위해 PensionLawAgentAdapter 제공

# %%
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_upstage import UpstageEmbeddings, ChatUpstage
from langchain_core.tools import tool
from langchain.agents import create_agent

load_dotenv()

# %%
# Embedding / VectorStore / Retriever
embedding_function = UpstageEmbeddings(model="solar-embedding-1-large")

vector_store = Chroma(
    embedding_function=embedding_function,
    collection_name="pension_law_collection",
    persist_directory="./pension_law_collection",
)

retriever = vector_store.as_retriever(search_kwargs={"k": 3})

# %%
# LLM
llm = ChatUpstage()

# %%
# 사용자 표현 -> 법령 표현 치환 사전
DICTIONARY = [
    "직장인 -> 사업장가입자",
    "회사원 -> 사업장가입자",
    "근로자 -> 사업장가입자",
    "개인사업자 -> 지역가입자",
    "자영업자 -> 지역가입자",
    "프리랜서 -> 지역가입자",
    "학생 -> 임의가입자",
    "전업주부 -> 임의가입자",
    "주부 -> 임의가입자",
    "외국인 -> 외국인가입자",
    "연금 보험료 -> 연금보험료",
    "국민연금 보험료 -> 연금보험료",
    "보험료 미납 -> 연금보험료 체납",
    "연금 못 냄 -> 연금보험료 체납",
    "가입 해지 -> 가입자 자격 상실",
    "탈퇴 -> 가입자 자격 상실",
    "가입 시작일 -> 자격 취득 시기",
    "가입 끝나는 날 -> 자격 상실 시기",
    "수급자 -> 수급권자",
    "연금 받는 사람 -> 수급권자",
    "노후연금 -> 노령연금",
    "장애 보상 -> 장애연금",
    "사망 후 연금 -> 유족연금",
    "배우자 연금 -> 유족연금",
]


def docs_to_text(docs) -> str:
    """검색된 Document 리스트를 Agent tool 반환값으로 변환합니다."""
    if not docs:
        return "관련 문서를 찾지 못했습니다."

    chunks = []

    for idx, doc in enumerate(docs, start=1):
        content = getattr(doc, "page_content", "") or ""
        metadata = getattr(doc, "metadata", {}) or {}

        source = (
            metadata.get("source")
            or metadata.get("file_path")
            or metadata.get("title")
            or metadata.get("filename")
            or "출처 정보 없음"
        )
        page = metadata.get("page") or metadata.get("page_number")

        header = f"[검색 결과 {idx}]\n출처: {source}"
        if page is not None:
            header += f"\n페이지: {page}"

        chunks.append(f"{header}\n내용:\n{content}")

    return "\n\n---\n\n".join(chunks)


@tool
def search_pension_law(query: str) -> str:
    """국민연금 법령/문서에서 질문과 관련된 내용을 검색합니다.

    국민연금 가입자, 사업장가입자, 지역가입자, 임의가입자, 연금보험료,
    노령연금, 장애연금, 유족연금, 수급권자, 자격 취득/상실 등
    국민연금 법령 근거가 필요한 질문에 사용합니다.
    """
    docs = retriever.invoke(query)
    return docs_to_text(docs)


# %%
SYSTEM_PROMPT = f"""
당신은 국민연금 법령/문서 기반으로 답변하는 RAG Agent입니다.

답변 규칙:
1. 국민연금, 연금 수급, 가입자 자격, 보험료, 노령연금, 장애연금, 유족연금 관련 질문은 반드시 search_pension_law tool을 먼저 사용하세요.
2. 사용자의 표현이 법령 용어와 다르면 아래 사전을 참고해 검색어를 보정하세요.
3. 검색 결과에 근거가 있는 내용만 답변하세요.
4. 검색 결과에 없는 내용은 추측하지 말고 "제공된 문서에서 확인하기 어렵습니다"라고 말하세요.
5. 답변은 한국어로, 사용자가 이해하기 쉽게 설명하세요.
6. 가능하면 답변 마지막에 참고한 검색 결과 번호를 간단히 표시하세요.
7. 답변을 작성한 뒤 스스로 다음을 점검하세요.
   - 검색 결과에 근거한 답변인가?
   - 사용자의 질문에 직접 답했는가?
   - 법령 용어를 사용하되 너무 어렵게 쓰지는 않았는가?

용어 사전:
{DICTIONARY}
"""

# %%
agent = create_agent(
    model=llm,
    tools=[search_pension_law],
    system_prompt=SYSTEM_PROMPT,
)


# %%
def get_answer_from_agent_result(result) -> str:
    """create_agent 결과에서 최종 답변 텍스트를 안전하게 추출합니다."""
    if isinstance(result, dict):
        messages = result.get("messages") or []
        if messages:
            last_message = messages[-1]
            content = getattr(last_message, "content", None)
            if content is not None:
                return content
            if isinstance(last_message, dict):
                return last_message.get("content", str(last_message))
        return str(result)

    content = getattr(result, "content", None)
    if content is not None:
        return content

    return str(result)


class PensionLawAgentAdapter:
    """기존 graph.invoke({'query': ...}) 형태와 호환되도록 만든 래퍼입니다.

    기존 pesion_law_graph.py를 사용하는 다른 코드가 아래처럼 호출하더라도
    그대로 동작하게 만들기 위한 목적입니다.

    result = graph.invoke({'query': '직장인은 언제 연금을 받을 수 있나요?'})
    print(result['answer'])
    """

    def __init__(self, agent):
        self.agent = agent

    def invoke(self, inputs, **kwargs):
        if isinstance(inputs, dict):
            query = inputs.get("query") or inputs.get("question") or inputs.get("input")
        else:
            query = str(inputs)

        if not query:
            raise ValueError("query, question, input 중 하나가 필요합니다.")

        result = self.agent.invoke(
            {
                "messages": [
                    {"role": "user", "content": query}
                ]
            },
            **kwargs,
        )
        answer = get_answer_from_agent_result(result)
        return {"query": query, "answer": answer, "raw_result": result}

    def get_graph(self):
        return self.agent.get_graph()


# 기존 코드 호환용 이름
# from pesion_law_agent import graph 로 가져와도 graph.invoke({'query': ...}) 사용 가능
graph = PensionLawAgentAdapter(agent)


# %%
def ask_pension_law(query: str) -> str:
    """간단 실행용 헬퍼 함수입니다."""
    return graph.invoke({"query": query})["answer"]


# %%
if __name__ == "__main__":
    query = "일반적으로 직장인은 언제 연금을 수령할 수 있나요?"
    result = graph.invoke({"query": query})
    print(result["answer"])
