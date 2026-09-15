import json
import os
import re
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from core.rag_retriever import retrieve
from core.counselor_style_retriever import CounselorStyleRetriever


# =========================================================
# Vertex AI 설정
# =========================================================

# 새 프로젝트 Billing 활성화 전까지는 기존 프로젝트 fallback 사용.
# 나중에는 환경변수만 바꾸면 코드 수정 없이 전환 가능.
PROJECT_ID = os.getenv(
    "GOOGLE_CLOUD_PROJECT",
    "live-copliot"
)

LOCATION = os.getenv(
    "GOOGLE_CLOUD_LOCATION",
    "global"
)

MODEL_ID = os.getenv(
    "GEMINI_MODEL_ID",
    "gemini-3.5-flash-lite"
)


client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)


# =========================================================
# Shared Counselor Style Retriever
# =========================================================

style_retriever = CounselorStyleRetriever()


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
# 질문 유형 판별
#
# Gemini 호출 전에
# 어떤 종류의 상담 Style Frame을 줄지만 결정한다.
#
# 사실 판단은 절대로 여기서 하지 않는다.
# =========================================================

def detect_question_style_candidates(
    question: str
) -> list[str]:

    question = str(
        question or ""
    ).strip()

    # -----------------------------------------
    # 가능 여부 / 지원 여부 질문
    # -----------------------------------------

    yes_no_patterns = [
        r"가능",
        r"되나요",
        r"돼요",
        r"됩니까",
        r"되냐",
        r"할 수 있",
        r"지원하",
        r"지원되",
        r"있나요",
        r"있어요",
        r"있습니까",
        r"없나요",
        r"없어요",
    ]

    if any(
        re.search(
            pattern,
            question,
            flags=re.IGNORECASE
        )
        for pattern in yes_no_patterns
    ):

        return [
            "POSITIVE",
            "NEGATIVE",
            "NO_INFORMATION",
            "INFORMATION"
        ]

    # -----------------------------------------
    # 일반 정보 질문
    # -----------------------------------------

    return [
        "INFORMATION",
        "CONFIRMATION",
        "NO_INFORMATION",
        "APOLOGY"
    ]


# =========================================================
# Style Frame 검색
#
# counselor_style_search.json의 47개 Frame 중
# 질문에 필요할 가능성이 있는 Style에서
# 대표 Frame을 가져온다.
#
# Gemini 호출 없음.
# =========================================================

def retrieve_style_frames(
    question: str,
    per_style: int = 1
) -> list[dict]:

    target_styles = (
        detect_question_style_candidates(
            question
        )
    )

    frames = []
    used_texts = set()

    for style in target_styles:

        entries = (
            style_retriever
            .by_style
            .get(
                style,
                []
            )
        )

        count = 0

        for entry in entries:

            text = entry.get(
                "retrieval_text",
                ""
            ).strip()

            if not text:
                continue

            if text in used_texts:
                continue

            used_texts.add(
                text
            )

            frames.append(
                {
                    "style_type":
                        style,

                    "retrieval_text":
                        text,

                    "evidence_count":
                        entry.get(
                            "evidence_count",
                            0
                        )
                }
            )

            count += 1

            if count >= per_style:
                break

    return frames


# =========================================================
# Style Frame → Prompt Text
# =========================================================

def build_style_text(
    style_frames: list[dict]
) -> str:

    if not style_frames:

        return (
            "- 자연스럽고 짧은 "
            "상담사 말투로 답변하세요."
        )

    lines = []

    for frame in style_frames:

        lines.append(
            f"- [{frame['style_type']}] "
            f"{frame['retrieval_text']}"
        )

    return "\n".join(
        lines
    )


# =========================================================
# NO_GROUNDED_INFO 기본 답변
#
# Product KB 자체가 전혀 검색되지 않은 경우에는
# Gemini를 호출할 이유가 없으므로 로컬에서 반환한다.
# =========================================================

def no_grounded_answer():

    return {
        "grounding_status":
            "NO_GROUNDED_INFO",

        "source_chunk_ids": [],

        "answer":
            (
                "문의주신 내용은 현재 "
                "제공된 상품정보에서 "
                "확인이 어렵습니다."
            )
    }


# =========================================================
# 질문 → Retrieval → Style Retrieval
#      → Grounding + Answer
#
# Gemini 호출 최대 1회
# =========================================================

def answer_question(question: str):

    # -----------------------------------------
    # 1. 관련 Product KB Retrieval
    # Gemini 호출 0회
    # -----------------------------------------

    chunks = retrieve(
        question,
        top_k=3
    )

    # Product KB 검색 결과 자체가 없는 경우
    # Gemini 호출 없이 종료
    if not chunks:

        return no_grounded_answer()

    # -----------------------------------------
    # 2. 상담 Style Frame Retrieval
    # Gemini 호출 0회
    # -----------------------------------------

    style_frames = (
        retrieve_style_frames(
            question=question,
            per_style=1
        )
    )

    style_text = (
        build_style_text(
            style_frames
        )
    )

    # -----------------------------------------
    # 3. Gemini에 전달할 Product KB 구성
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
    # 4. Grounding + Style 통합 Prompt
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
[가장 중요한 정보 출처 규칙]
========================================

아래에는 두 종류의 정보가 제공됩니다.

1. 상품정보 KB
2. 상담 표현 참고

상품에 관한 사실, 숫자, 기능, 조건, 정책은
반드시 '상품정보 KB'에서만 가져와야 합니다.

'상담 표현 참고'는
오직 말투와 문장 구조를 참고하기 위한 자료입니다.

상담 표현 참고에 포함된 문장을
상품 사실의 근거로 사용해서는 안 됩니다.

상담 표현의 {{확인된 정보}},
{{안내 정보}}, {{문의 내용}} 같은 표시는
문장 구조를 보여주기 위한 placeholder입니다.

최종 답변에는 placeholder를 그대로 출력하지 말고,
상품정보 KB에서 실제로 확인된 내용만 넣으세요.


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
[상담 말투 적용 규칙]
========================================

아래 '상담 표현 참고'는
K쇼핑 상담 데이터에서 추출한
상담 표현 Frame입니다.

이 표현들은 사실 근거가 아닙니다.

먼저 상품정보 KB만으로
Grounding 상태와 답변 사실을 결정하세요.

그 다음,
결정한 Grounding 상태와 답변 내용에 적합한 경우에만
상담 표현의 문장 구조를 참고하세요.

GROUNDED인 경우:
- 확인된 정보를 직접 답하세요.
- INFORMATION, CONFIRMATION,
  POSITIVE, NEGATIVE 표현 중
  상황에 맞는 방식을 참고할 수 있습니다.

PARTIAL_GROUNDED인 경우:
- 확인 가능한 부분은 자연스럽게 답하세요.
- 확인되지 않는 부분은
  상품정보에서 확인하기 어렵다고 명확히 말하세요.

NO_GROUNDED_INFO인 경우:
- 새로운 사실을 만들지 마세요.
- NO_INFORMATION 또는 APOLOGY 계열 표현을 참고하여
  자연스럽게 안내하세요.

상담 표현을 억지로 모두 사용할 필요는 없습니다.

같은 의미를 반복하지 마세요.

"잠시만 기다려 주세요",
"확인 후 연락드리겠습니다",
"처리해 드리겠습니다"처럼
실제로 수행하지 않는 행동을 약속하지 마세요.

최종 답변은 가능하면
한두 문장으로 간결하게 작성하세요.


========================================
[고객 질문]
========================================

{question}


========================================
[검색된 상품정보 KB]
========================================

{kb_text}


========================================
[상담 표현 참고 - STYLE ONLY]
========================================

{style_text}
"""

    # -----------------------------------------
    # 5. Gemini 호출
    #
    # 질문당 최대 1회
    # -----------------------------------------

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,

        config=types.GenerateContentConfig(
            # Grounding 안정성을 위해 기존과 동일하게 유지
            temperature=0,

            response_mime_type=
                "application/json",

            response_schema=
                GroundedAnswer
        )
    )

    # -----------------------------------------
    # 6. JSON 변환
    # -----------------------------------------

    result = json.loads(
        response.text
    )

    # -----------------------------------------
    # 7. 존재하지 않는 chunk_id 제거
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
    # 8. NO_GROUNDED_INFO 방어
    #
    # 기존처럼 answer 전체를 고정문으로
    # 덮어쓰지 않는다.
    #
    # 그래야 Style RAG가 생성한
    # 자연스러운 안내 문장을 유지할 수 있다.
    # -----------------------------------------

    if (
        result["grounding_status"]
        == "NO_GROUNDED_INFO"
    ):

        result[
            "source_chunk_ids"
        ] = []

        # 비정상적으로 빈 답변인 경우만 fallback
        if not str(
            result.get(
                "answer",
                ""
            )
        ).strip():

            result[
                "answer"
            ] = (
                "문의주신 내용은 현재 "
                "제공된 상품정보에서 "
                "확인이 어렵습니다."
            )

    # -----------------------------------------
    # 9. 근거 없이 GROUNDED / PARTIAL이면 방어
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

        result[
            "grounding_status"
        ] = (
            "NO_GROUNDED_INFO"
        )

        result[
            "source_chunk_ids"
        ] = []

        result[
            "answer"
        ] = (
            "문의주신 내용은 현재 "
            "제공된 상품정보에서 "
            "확인이 어렵습니다."
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