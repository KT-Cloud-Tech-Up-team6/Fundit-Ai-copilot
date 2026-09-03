import json
from typing import Literal

from google.genai import types
from pydantic import BaseModel

from orchestrator import llm
from parts.p_part.rag_retriever import retrieve


# =========================================================
# 모델 설정 — 통합 시 변경: 인증·모델 선택을 공용 llm 모듈로 통일
# (env 로 API 키/Vertex 선택 — Grounding 판정 로직·프롬프트 무변경)
# =========================================================

MODEL_ID = llm.DEFAULT_MODEL


# =========================================================
# 출력 Schema
# =========================================================

class GroundedAnswer(BaseModel):

    grounding_status: Literal[
        "GROUNDED",
        "PARTIAL_GROUNDED",
        "NO_GROUNDED_INFO"
    ]

    source_chunk_ids: list[str]

    answer: str


# =========================================================
# 질문 → Retrieval → Grounding → Answer
# =========================================================

def answer_question(question: str):

    # -----------------------------------------
    # 1. 관련 KB Retrieval
    # -----------------------------------------

    chunks = retrieve(
        question,
        top_k=3
    )

    # 검색되는 KB 자체가 없는 경우
    if not chunks:

        return {
            "grounding_status":
                "NO_GROUNDED_INFO",

            "source_chunk_ids": [],

            "answer":
                "제공된 상품정보에서 확인되지 않습니다."
        }

    # -----------------------------------------
    # 2. Gemini에 전달할 KB 구성
    # -----------------------------------------

    kb_text = "\n\n".join(

        [
            f"""
[chunk_id]
{chunk['chunk_id']}

[category]
{chunk['category']}

[product_information]
{chunk['text']}

[strict]
{chunk['strict']}
""".strip()

            for chunk in chunks
        ]
    )

    retrieved_chunk_ids = [
        chunk["chunk_id"]
        for chunk in chunks
    ]

    # -----------------------------------------
    # 3. Grounding 프롬프트
    # -----------------------------------------

    prompt = f"""
당신은 라이브커머스 판매자를 지원하는
상품정보 답변 AI입니다.

반드시 아래에 제공된 상품정보 KB만 사용하여
고객 질문에 답하세요.

모델이 알고 있는 외부 지식,
일반적인 제품 지식,
추측을 사용해서는 안 됩니다.


========================================
[Grounding 판정 기준]
========================================

1. GROUNDED

제공된 KB만으로
고객 질문 전체에 충분히 답변할 수 있는 경우입니다.


2. PARTIAL_GROUNDED

고객 질문 중 일부 내용은 KB로 답할 수 있지만,
질문의 나머지 내용은 KB에 근거가 없는 경우입니다.


3. NO_GROUNDED_INFO

고객 질문에 필요한 정보가
제공된 KB에 존재하지 않는 경우입니다.


========================================
[복합 질문 판정]
========================================

고객 질문에 여러 개의 정보 요청이 포함되어 있다면
반드시 각각의 세부 질문으로 나누어 판단하세요.

예시:

고객 질문:
"흡입력은 몇이고 앱으로 원격 조작도 가능한가요?"

세부 질문:

1. 흡입력은 얼마인가?
2. 앱 원격 조작이 가능한가?

KB에 흡입력 정보만 존재한다면:

→ PARTIAL_GROUNDED

모든 세부 질문에 근거가 존재하면:

→ GROUNDED

모든 세부 질문에 근거가 없다면:

→ NO_GROUNDED_INFO


========================================
[매우 중요한 Grounding 규칙]
========================================

1.

질문과 관련된 정보가 있다는 이유만으로
답변 가능하다고 판단하면 안 됩니다.

질문에서 요구하는 정보 자체가
KB에 존재해야 합니다.


2.

질문에서 특정 숫자나 정확한 값을 요구하면
해당 숫자 또는 값이 KB에 직접 명시되어 있어야 합니다.

예:

질문:
"롤러 세척 온도는 정확히 몇 도인가요?"

KB:
"롤러를 고온으로 세척합니다."

이 경우 정확한 온도가 존재하지 않으므로:

→ NO_GROUNDED_INFO


3.

서로 다른 기능의 숫자를
다른 질문의 답으로 사용해서는 안 됩니다.

예:

KB:
"90°C 밀폐 건조 시스템"

질문:
"세척 온도는 몇 도인가요?"

90°C는 건조에 관한 정보이므로
세척 온도로 사용할 수 없습니다.

→ NO_GROUNDED_INFO


4.

특정 값이 존재한다고 해서
다른 선택지가 존재하지 않는다고
추론해서는 안 됩니다.

예:

KB:
"제품 색상은 블랙입니다."

질문:
"화이트 색상도 선택 가능한가요?"

블랙이라는 정보만으로
화이트 옵션 존재 여부를 알 수 없습니다.

→ NO_GROUNDED_INFO


5.

'가능한가요?',
'지원하나요?',
'있나요?',
'없나요?'

같은 가능 여부 질문은
그 가능 여부를 직접 뒷받침하는 KB 근거가 있어야 합니다.


6.

strict=true인 정보는
숫자, 단위, 조건을 임의로 바꾸면 안 됩니다.


7.

KB에 없는 내용을
일반 상식이나 제품 지식으로 보완하면 안 됩니다.


8.

답변에 실제로 사용한 chunk_id만
source_chunk_ids에 포함하세요.


9.

검색은 되었지만 실제 답변에 사용하지 않은 chunk는
source_chunk_ids에 넣지 마세요.


10.

답변은 라이브커머스 판매자가
즉시 참고할 수 있도록
짧고 자연스럽게 작성하세요.


========================================
[상태별 답변 방식]
========================================

GROUNDED:

KB에서 확인되는 정보를 이용하여
질문에 직접 답하세요.


PARTIAL_GROUNDED:

확인 가능한 부분만 답하고,
나머지 내용은 상품정보에서 확인되지 않는다고
명확하게 말하세요.


NO_GROUNDED_INFO:

추측하지 말고
상품정보에서 확인되지 않는다고 판단하세요.


========================================
[고객 질문]
========================================

{question}


========================================
[검색된 상품정보 KB]
========================================

{kb_text}
"""

    # -----------------------------------------
    # 4. Gemini 호출
    # -----------------------------------------

    response = llm.client().models.generate_content(
        model=MODEL_ID,
        contents=prompt,

        config=types.GenerateContentConfig(
            temperature=0,

            response_mime_type=
                "application/json",

            response_schema=
                GroundedAnswer
        )
    )

    # -----------------------------------------
    # 5. JSON 변환
    # -----------------------------------------

    result = json.loads(
        response.text
    )

    # -----------------------------------------
    # 6. 존재하지 않는 chunk_id 제거
    # -----------------------------------------

    result["source_chunk_ids"] = [

        chunk_id

        for chunk_id
        in result.get(
            "source_chunk_ids",
            []
        )

        if chunk_id
        in retrieved_chunk_ids
    ]

    # -----------------------------------------
    # 7. NO_GROUNDED_INFO 정규화
    # -----------------------------------------

    if (
        result["grounding_status"]
        == "NO_GROUNDED_INFO"
    ):

        result["source_chunk_ids"] = []

        result["answer"] = (
            "제공된 상품정보에서 확인되지 않습니다."
        )

    # -----------------------------------------
    # 8. 근거 없이 GROUNDED라고 나온 경우 방어
    # -----------------------------------------

    elif (
        result["grounding_status"]
        in [
            "GROUNDED",
            "PARTIAL_GROUNDED"
        ]
        and not result[
            "source_chunk_ids"
        ]
    ):

        result["grounding_status"] = (
            "NO_GROUNDED_INFO"
        )

        result["source_chunk_ids"] = []

        result["answer"] = (
            "제공된 상품정보에서 확인되지 않습니다."
        )

    return result


# =========================================================
# 단독 실행
# =========================================================

if __name__ == "__main__":

    question = input(
        "고객 질문: "
    )

    result = answer_question(
        question
    )

    print(
        "\n답변 결과"
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )