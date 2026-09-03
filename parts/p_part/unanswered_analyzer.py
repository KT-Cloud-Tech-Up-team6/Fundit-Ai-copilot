from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel


PROJECT_ID = "live-copliot"
LOCATION = "global"
MODEL = "gemini-3.5-flash-lite"

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION,
)


PCategory = Literal[
    "CLEANING_POWER",
    "WASH_DRY",
    "HAIR_TANGLE",
    "EDGE_REACH",
    "WATER_TANK",
    "CLEANING_MODE",
    "BATTERY",
    "APP_REMOTE",
    "MAINTENANCE",
    "PRODUCT_SPEC",
    "FLOOR_COMPATIBILITY",
    "PRODUCT_COMPARE",
    "OTHER_PRODUCT",
]


TopicKey = Literal[
    # CLEANING_POWER
    "SUCTION_PERFORMANCE",
    "REAL_WORLD_MESS_CLEANING",
    "VACUUM_REPLACEMENT",
    "AFTER_CLEANING_MOISTURE",

    # WASH_DRY
    "AUTO_WASH",
    "WASH_TEMPERATURE",
    "DRYING_ODOR",
    "STERILIZATION",

    # HAIR_TANGLE
    "HAIR_TANGLE_PREVENTION",
    "PET_HAIR",

    # EDGE_REACH
    "LOW_SPACE_REACH",
    "EDGE_CLEANING",
    "MANEUVERABILITY",
    "LAY_FLAT_LEAK",

    # WATER_TANK
    "COVERAGE_PER_TANK",
    "TANK_EMPTYING",
    "TANK_STRUCTURE",

    # CLEANING_MODE
    "MODE_DIFFERENCE",
    "MODE_BEHAVIOR",

    # BATTERY
    "BATTERY_RUNTIME",
    "BATTERY_CHARGING",
    "BATTERY_REPLACEMENT",

    # APP_REMOTE
    "SMART_CONNECTIVITY",

    # MAINTENANCE
    "CONSUMABLE_REPLACEMENT",
    "DETERGENT_USE",
    "WASTEWATER_MAINTENANCE",
    "INCLUDED_ACCESSORIES",

    # PRODUCT_SPEC
    "COLOR_OPTIONS",
    "WEIGHT_USABILITY",
    "NOISE_USABILITY",
    "CERTIFICATION",
    "LIGHTING",

    # FLOOR_COMPATIBILITY
    "HARD_FLOOR_USE",
    "CARPET_RUG_USE",

    # PRODUCT_COMPARE
    "PRODUCT_COMPARISON",

    # OTHER_PRODUCT
    "OTHER_PRODUCT_QUESTION",
]


class UnansweredTopic(BaseModel):
    category: PCategory
    topic_key: TopicKey
    representative_question: str


class UnansweredAnalysis(BaseModel):
    topics: list[UnansweredTopic]


TOPIC_GUIDE = """
[CLEANING_POWER]

SUCTION_PERFORMANCE
- 흡입 세기
- 흡입력 체감
- 큰 먼지 흡입 성능

REAL_WORLD_MESS_CLEANING
- 음식물
- 날계란
- 음료
- 기름
- 끈적한 오염
- 실제 생활 오염 청소 가능 여부

VACUUM_REPLACEMENT
- 일반 진공청소기 대체 가능 여부

AFTER_CLEANING_MOISTURE
- 물걸레 청소 후 바닥에 물기가 남는지


[WASH_DRY]

AUTO_WASH
- 자동 세척
- 도크 세척
- 롤러를 따로 손빨래해야 하는지

WASH_TEMPERATURE
- 세척수 온도
- 온수 세척 온도
- 롤러 세척 온도

DRYING_ODOR
- 건조 후 냄새
- 걸레 냄새 방지

STERILIZATION
- 살균 효과
- 살균 수치
- 살균 관련 인증


[HAIR_TANGLE]

HAIR_TANGLE_PREVENTION
- 머리카락 엉킴 방지
- 롤러에 머리카락이 감기는지

PET_HAIR
- 강아지 털
- 고양이 털
- 반려동물 털 청소
- 반려동물 털 엉킴


[EDGE_REACH]

LOW_SPACE_REACH
- 소파 밑
- 침대 밑
- 12.5cm 공간
- 180도 눕힘
- 낮은 공간 진입

EDGE_CLEANING
- 벽면 밀착
- 모서리
- 가장자리 청소

MANEUVERABILITY
- 헤드 회전각
- 방향 전환
- 조작성

LAY_FLAT_LEAK
- 본체를 눕혀 사용할 때 누수되는지


[WATER_TANK]

COVERAGE_PER_TANK
- 물통을 한 번 채웠을 때 청소 가능한 면적

TANK_EMPTYING
- 오수통 비우기
- 오수통 관리 난이도

TANK_STRUCTURE
- 물통 위치
- 물통 구조
- 구조에 따른 안정성


[CLEANING_MODE]

MODE_DIFFERENCE
- AUTO와 ECO 등 모드 간 차이

MODE_BEHAVIOR
- 특정 모드에서 물걸레가 작동하는지
- 특정 모드의 세부 동작


[BATTERY]

BATTERY_RUNTIME
- 완충 사용시간
- 한 번 충전으로 청소 가능한 면적

BATTERY_CHARGING
- 충전 시간

BATTERY_REPLACEMENT
- 배터리 분리 가능 여부
- 배터리 교체 가능 여부


[APP_REMOTE]

SMART_CONNECTIVITY
- 앱 연결
- Wi-Fi 연결
- 휴대폰 원격 조작
- 음성 명령
- 스마트 기능 연동


[MAINTENANCE]

CONSUMABLE_REPLACEMENT
- 롤러 교체 주기
- 필터 교체 주기
- 걸레 교체 주기
- 소모품 교체 비용

DETERGENT_USE
- 전용 클리너
- 일반 세제
- 세제 사용 가능 여부

WASTEWATER_MAINTENANCE
- 오수통에 머리카락이 들어가는지
- 오수 관리

INCLUDED_ACCESSORIES
- 여분 롤러
- 추가 구성품
- 기본 구성품 포함 여부


[PRODUCT_SPEC]

COLOR_OPTIONS
- 색상 종류
- 색상 옵션

WEIGHT_USABILITY
- 실제 사용할 때 무거운지
- 밀고 사용할 때 체감 무게

NOISE_USABILITY
- 야간 사용
- 체감 소음

CERTIFICATION
- 제품 시험
- 제품 인증
- 수치 인증 여부

LIGHTING
- LED 조명
- 조명 기능


[FLOOR_COMPATIBILITY]

HARD_FLOOR_USE
- 대리석
- 장판
- 강화마루
- 원목마루
- 일반 바닥재 사용 가능 여부

CARPET_RUG_USE
- 카펫
- 러그
- 카펫 전용 모드
- 카펫류 사용 가능 여부


[PRODUCT_COMPARE]

PRODUCT_COMPARISON
- 다른 제품과 비교
- 타 브랜드와 비교
- 타 모델과 비교


[OTHER_PRODUCT]

OTHER_PRODUCT_QUESTION
- 위 주제로 묶을 수 없는 기타 상품 질문
"""


def analyze_unanswered(
    question: str,
    grounding_status: str,
    rag_answer: str = "",
) -> UnansweredAnalysis:
    """
    RAG가 해결하지 못한 세부질문만 추출한다.

    GROUNDED
    - 판매자 관심사 화면에 반영하지 않음

    NO_GROUNDED_INFO
    - 원본 질문 전체에서 미답변 상품 질문 추출

    PARTIAL_GROUNDED
    - 이미 답한 내용은 제외
    - 해결하지 못한 세부 질문만 추출
    """

    if grounding_status == "GROUNDED":
        return UnansweredAnalysis(topics=[])

    prompt = f"""
당신은 라이브커머스 Seller Copilot의
P(Product) 미답변 질문 분석기입니다.

목표:
상품 Knowledge Base로 답하지 못한 질문을
'고객 관심 유형 + 대표 질문' 형태로 집계하기 위한
구조화 데이터로 변환합니다.

가장 중요한 규칙:
topic_key를 새로 만들면 안 됩니다.

반드시 아래에 정의된 topic_key 중
가장 가까운 하나를 선택해야 합니다.

[고정 Topic 체계]

{TOPIC_GUIDE}


[입력]

원본 고객 질문:
{question}

Grounding 상태:
{grounding_status}

RAG 처리 결과:
{rag_answer}


[분석 규칙]

1.
RAG에서 이미 답변한 내용은
topics에 포함하지 않습니다.

2.
NO_GROUNDED_INFO이면
원본 질문에서 상품 KB로 해결하지 못한
상품 관련 질문을 추출합니다.

3.
PARTIAL_GROUNDED이면
이미 답변된 부분은 제외하고
해결되지 않은 세부 질문만 추출합니다.

4.
서로 다른 의미의 미답변 질문이
2개 이상 존재하면 topics를 여러 개 반환할 수 있습니다.

5.
같은 의미의 질문은 반드시
같은 topic_key를 사용합니다.

6.
대리석 / 장판 / 강화마루 / 원목마루 질문은
HARD_FLOOR_USE로 묶습니다.

7.
카펫 / 러그 / 카펫 전용 모드 질문은
CARPET_RUG_USE로 묶습니다.

8.
자동 세척 / 도크 세척 / 롤러 손빨래 필요 여부는
AUTO_WASH로 묶습니다.

9.
세척수 온도 / 온수 세척 / 롤러 세척 온도는
WASH_TEMPERATURE로 묶습니다.

10.
앱 / Wi-Fi / 휴대폰 원격 조작 / 음성 명령은
SMART_CONNECTIVITY로 묶습니다.

11.
강아지 / 고양이 / 반려동물 털 질문은
PET_HAIR로 묶습니다.

12.
소파 밑 / 침대 밑 / 12.5cm / 180도 눕힘은
LOW_SPACE_REACH로 묶습니다.

13.
representative_question은
판매자가 방송에서 바로 이해할 수 있는
짧고 자연스러운 질문 형태로 작성합니다.

14.
질문에 대한 답변을 생성하지 않습니다.

15.
상품과 관계없는 잡담, 감탄,
단순 구매 의사 표현은 제외합니다.


[예시 1]

원본:
"대리석에도 되나요?"

출력:
category = FLOOR_COMPATIBILITY
topic_key = HARD_FLOOR_USE
representative_question =
"어떤 바닥재에서 사용할 수 있나요?"


[예시 2]

원본:
"장판도 돼요?"

출력:
category = FLOOR_COMPATIBILITY
topic_key = HARD_FLOOR_USE
representative_question =
"어떤 바닥재에서 사용할 수 있나요?"


[예시 3]

원본:
"도크에 올리면 자동 세척돼요?"

출력:
category = WASH_DRY
topic_key = AUTO_WASH
representative_question =
"롤러를 자동으로 세척해주나요?"


[예시 4]

원본:
"흡입력은 몇이고 앱으로도 조작돼요?"

Grounding 상태:
PARTIAL_GROUNDED

RAG 처리 결과:
"최대 흡입력은 20,000Pa이며,
앱 조작 여부는 상품정보에서 확인되지 않습니다."

출력:
category = APP_REMOTE
topic_key = SMART_CONNECTIVITY
representative_question =
"앱이나 와이파이로 원격 조작할 수 있나요?"
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=UnansweredAnalysis,
        ),
    )

    if not response.text:
        return UnansweredAnalysis(topics=[])

    return UnansweredAnalysis.model_validate_json(
        response.text
    )