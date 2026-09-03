import logging
import re
import time


# =========================================================
# Google GenAI SDK 경고 숨김
# =========================================================
#
# 기능에는 영향을 주지 않는 AFC 안내 로그만 숨긴다.
# 전체 WARNING을 비활성화하지 않고
# google-genai 모델 관련 로그만 ERROR 이상으로 제한한다.
#
# 반드시 google 관련 모듈 import 전에 설정한다.
# =========================================================

logging.getLogger(
    "google_genai.models"
).setLevel(logging.ERROR)

logging.getLogger(
    "google.genai.models"
).setLevel(logging.ERROR)


from parts.p_part.interest_tracker import InterestTracker
from parts.p_part.rag_answer import answer_question
from parts.p_part.unanswered_analyzer import analyze_unanswered


# =========================================================
# 1. RAG 결과 dict 변환
# =========================================================

def to_dict(result):
    if hasattr(result, "model_dump"):
        return result.model_dump()

    if isinstance(result, dict):
        return result

    raise TypeError(
        f"지원하지 않는 RAG 결과 타입입니다: {type(result)}"
    )


# =========================================================
# 2. 질문 여부 판단
# =========================================================

def is_question_comment(comment: str) -> bool:
    """
    라이브 댓글 중 질문으로 판단되는 댓글만
    RAG 파이프라인으로 전달한다.

    질문 예시
    - 흡입력 몇 파스칼이에요?
    - 장판에도 돼요?
    - 앱으로 조작 가능한가요?
    - 배터리 얼마나 가요?
    - 롤러 세척 자동인가요?

    비질문 예시
    - ㅇㅇ
    - ㅋㅋㅋ
    - 대박
    - 좋네요
    - 사고 싶다
    """

    text = comment.strip()

    if not text:
        return False

    normalized = (
        text.lower()
        .replace(" ", "")
    )

    # -----------------------------------------------------
    # 2-1. 단순 반응형 댓글 제거
    # -----------------------------------------------------

    reaction_text = re.sub(
        r"[!?~.,ㅋㅎㅠㅜ\s]",
        "",
        normalized,
    )

    short_reactions = {
        "ㅇㅇ",
        "ㅇ",
        "ㄴㄴ",
        "ㄴ",
        "대박",
        "오",
        "와",
        "굿",
        "좋다",
        "좋네요",
        "좋아요",
        "예쁘다",
        "예뻐요",
        "멋지다",
        "사고싶다",
        "사고싶어요",
        "살게요",
        "구매할게요",
        "감사합니다",
        "감사해요",
    }

    if reaction_text in short_reactions:
        return False

    # -----------------------------------------------------
    # 2-2. ㅋㅋㅋ / ㅎㅎ / ㅠㅠ 등 제거
    # -----------------------------------------------------

    if re.fullmatch(
        r"[ㅋㅎㅠㅜㅇㄴㄷㄱ]+",
        normalized,
    ):
        return False

    # -----------------------------------------------------
    # 2-3. 물음표가 있으면 질문으로 판단
    # -----------------------------------------------------

    if "?" in text:
        return True

    # -----------------------------------------------------
    # 2-4. 일반적인 질문 표현
    # -----------------------------------------------------

    question_patterns = [
        "인가요",
        "인가",
        "나요",
        "되나요",
        "돼요",
        "되죠",
        "되나",
        "가능한가요",
        "가능해요",
        "가능하나요",
        "있나요",
        "없나요",
        "맞나요",
        "맞죠",
        "맞아요",
        "어떤가요",
        "어때요",
        "어떻게",
        "얼마",
        "얼마나",
        "몇",
        "뭔가요",
        "뭐예요",
        "뭐에요",
        "언제",
        "왜",
        "어디",
        "쓸수",
        "사용할수",
        "지원해요",
        "지원하나요",
        "지원되나요",
        "궁금해요",
        "궁금합니다",
    ]

    for pattern in question_patterns:
        normalized_pattern = (
            pattern.replace(" ", "")
        )

        if normalized_pattern in normalized:
            return True

    # -----------------------------------------------------
    # 2-5. 상품 키워드 + 요청형 표현
    # -----------------------------------------------------

    product_keywords = [
        "흡입력",
        "물걸레",
        "배터리",
        "충전",
        "세척",
        "건조",
        "물통",
        "청수통",
        "오수통",
        "소음",
        "무게",
        "크기",
        "사이즈",
        "롤러",
        "머리카락",
        "반려동물",
        "강아지",
        "고양이",
        "카펫",
        "러그",
        "장판",
        "마루",
        "대리석",
        "앱",
        "와이파이",
        "색상",
        "컬러",
        "as",
        "보증",
        "모드",
        "클리너",
        "세제",
        "헤드",
        "틈새",
        "모서리",
    ]

    request_patterns = [
        "알려줘",
        "알려주세요",
        "궁금",
    ]

    has_product_keyword = any(
        keyword in normalized
        for keyword in product_keywords
    )

    has_request_pattern = any(
        pattern in normalized
        for pattern in request_patterns
    )

    if (
        has_product_keyword
        and has_request_pattern
    ):
        return True

    return False


# =========================================================
# 3. Grounding 결과 출력
# =========================================================

def print_grounding_result(
    status: str,
    answer: str,
):
    """
    Grounding 상태에 따라
    데모 화면에 보여줄 내용을 출력한다.
    """

    if status == "GROUNDED":

        print(
            "→ 상품 KB에서 처리 가능한 질문"
        )

        if answer:
            print(
                f"→ 답변: {answer}"
            )

    elif status == "PARTIAL_GROUNDED":

        print(
            "→ 상품 KB에서 일부 처리 가능한 질문"
        )

        if answer:
            print(
                f"→ 부분 답변: {answer}"
            )

    elif status == "NO_GROUNDED_INFO":

        print(
            "→ 상품 KB에 답변 근거가 없는 질문"
        )

    else:

        print(
            f"→ 알 수 없는 Grounding 상태: {status}"
        )


# =========================================================
# 4. 미답변 질문 집계
# =========================================================

def process_unanswered(
    tracker: InterestTracker,
    comment: str,
    status: str,
    answer: str,
):
    """
    PARTIAL_GROUNDED 또는
    NO_GROUNDED_INFO 질문을 분석하여
    해결되지 않은 상품 질문만 관심사에 반영한다.
    """

    analysis = analyze_unanswered(
        question=comment,
        grounding_status=status,
        rag_answer=answer,
    )

    if not analysis.topics:

        print(
            "→ 추가로 집계할 미답변 상품 질문 없음"
        )

        return

    # 실제 시청자가 입력한 원문 질문을 같이 저장
    tracker.add_topics(
        topics=analysis.topics,
        original_question=comment,
    )

    if status == "PARTIAL_GROUNDED":

        print(
            f"→ 해결되지 않은 세부질문 "
            f"{len(analysis.topics)}건 집계"
        )

    else:

        print(
            f"→ 미답변 질문 "
            f"{len(analysis.topics)}건 집계"
        )

    print()

    # 미답변 질문이 발생하면
    # 현재 Seller Copilot 화면을 바로 출력
    tracker.print_dashboard(
        top_n=5
    )


# =========================================================
# 5. 메인
# =========================================================

def main():

    # -----------------------------------------------------
    # 관심사 Tracker 생성
    # -----------------------------------------------------

    tracker = InterestTracker()

    # -----------------------------------------------------
    # 새로운 방송 세션으로 시작
    #
    # 프로그램을 새로 실행할 때마다
    # 이전 테스트 집계를 초기화한다.
    #
    # 같은 프로그램 실행 중에는 계속 누적된다.
    # -----------------------------------------------------

    tracker.reset()

    # -----------------------------------------------------
    # 시작 화면
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print(
        "로보락 F25 Seller Copilot - P파트 MVP"
    )
    print("=" * 70)
    print(
        "/dashboard : 현재 미답변 고객 관심사 확인"
    )
    print(
        "/reset     : 관심사 집계 초기화"
    )
    print(
        "q          : 종료"
    )
    print("=" * 70)

    # =====================================================
    # 실시간 댓글 입력
    # =====================================================

    while True:

        print()

        comment = input(
            "고객 댓글 > "
        ).strip()

        if not comment:
            continue

        # =================================================
        # 명령어 처리
        # =================================================

        if comment.lower() in {
            "q",
            "quit",
            "exit",
        }:

            print(
                "테스트를 종료합니다."
            )

            break

        if comment == "/dashboard":

            tracker.print_dashboard(
                top_n=5
            )

            continue

        if comment == "/reset":

            tracker.reset()

            print(
                "→ 관심사 집계를 초기화했습니다."
            )

            continue

        # =================================================
        # 질문 여부 판단
        # =================================================

        if not is_question_comment(
            comment
        ):

            print(
                "→ 질문이 아닌 댓글로 판단되어 제외"
            )

            continue

        # =================================================
        # 처리 시작
        # =================================================

        start = time.time()

        try:

            # =============================================
            # RAG 실행
            # =============================================

            rag_result = to_dict(
                answer_question(
                    comment
                )
            )

            status = rag_result.get(
                "grounding_status",
                "",
            )

            answer = rag_result.get(
                "answer",
                "",
            )

            # =============================================
            # Grounding 결과 출력
            # =============================================

            print_grounding_result(
                status=status,
                answer=answer,
            )

            # =============================================
            # GROUNDED
            #
            # 상품 KB로 전체 질문을 해결했으므로
            # 관심사 집계에는 포함하지 않는다.
            # =============================================

            if status == "GROUNDED":

                pass

            # =============================================
            # PARTIAL / NO
            # =============================================

            elif status in {
                "PARTIAL_GROUNDED",
                "NO_GROUNDED_INFO",
            }:

                process_unanswered(
                    tracker=tracker,
                    comment=comment,
                    status=status,
                    answer=answer,
                )

            # =============================================
            # 처리 시간 출력
            # =============================================

            elapsed = (
                time.time()
                - start
            )

            print(
                f"처리 시간: "
                f"{elapsed:.2f}초"
            )

        except Exception as exc:

            print(
                f"오류 발생: {exc}"
            )


# =========================================================
# 6. 실행
# =========================================================

if __name__ == "__main__":
    main()