from typing import Any, Optional


from core.interest_tracker import InterestTracker
from core.rag_answer import answer_question
from core.unanswered_analyzer import analyze_unanswered


VALID_GROUNDING_STATUSES = {
    "GROUNDED",
    "PARTIAL_GROUNDED",
    "NO_GROUNDED_INFO",
}


def to_dict(result: Any) -> dict:
    """
    Pydantic 모델 또는 dict 형태의 결과를
    일반 dict 형태로 변환한다.
    """

    if hasattr(result, "model_dump"):
        return result.model_dump()

    if isinstance(result, dict):
        return result

    raise TypeError(
        f"지원하지 않는 결과 타입입니다: {type(result)}"
    )


def topic_to_dict(topic: Any) -> dict:
    """
    unanswered_analyzer의 Topic 결과를
    외부에서 사용하기 쉬운 dict로 변환한다.
    """

    if hasattr(topic, "model_dump"):
        return topic.model_dump()

    if isinstance(topic, dict):
        return topic

    if hasattr(topic, "__dict__"):
        return vars(topic)

    return {
        "value": str(topic)
    }


def process_product_question(
    question: str,
    tracker: Optional[InterestTracker] = None,
) -> dict:
    """
    P파트 상품 질문 처리의 단일 진입 함수.

    처리 흐름
    1. 상품 RAG 실행
    2. Grounding 상태 확인
    3. PARTIAL / NO인 경우 미답변 세부질문 분석
    4. tracker가 전달된 경우 관심사 집계
    5. 외부에서 사용할 수 있는 dict 반환

    주의:
    이 함수는 입력이 P(Product) 질문이라고 가정한다.
    P/O/DROP 라우팅은 현재 범위에 포함하지 않는다.
    """

    question = question.strip()

    if not question:
        raise ValueError(
            "question은 비어 있을 수 없습니다."
        )

    # -----------------------------------------------------
    # 1. 상품 RAG 실행
    # -----------------------------------------------------

    rag_result = to_dict(
        answer_question(question)
    )

    grounding_status = rag_result.get(
        "grounding_status",
        "",
    )

    answer = rag_result.get(
        "answer",
        "",
    )

    source_chunk_ids = (
        rag_result.get(
            "source_chunk_ids",
            [],
        )
        or []
    )

    # -----------------------------------------------------
    # 2. Grounding 상태 검증
    # -----------------------------------------------------

    if grounding_status not in VALID_GROUNDING_STATUSES:
        raise ValueError(
            "알 수 없는 Grounding 상태입니다: "
            f"{grounding_status}"
        )

    # -----------------------------------------------------
    # 3. GROUNDED
    # -----------------------------------------------------

    if grounding_status == "GROUNDED":

        return {
            "question": question,
            "grounding_status": grounding_status,
            "answer": answer,
            "source_chunk_ids": source_chunk_ids,
            "unresolved_topics": [],
            "needs_seller_attention": False,
        }

    # -----------------------------------------------------
    # 4. PARTIAL / NO 미답변 분석
    # -----------------------------------------------------

    analysis = analyze_unanswered(
        question=question,
        grounding_status=grounding_status,
        rag_answer=answer,
    )

    topics = (
        analysis.topics
        if analysis.topics
        else []
    )

    unresolved_topics = [
        topic_to_dict(topic)
        for topic in topics
    ]

    # -----------------------------------------------------
    # 5. 관심사 집계
    # -----------------------------------------------------

    if tracker is not None and topics:

        tracker.add_topics(
            topics=topics,
            original_question=question,
        )

    # -----------------------------------------------------
    # 6. 최종 결과
    # -----------------------------------------------------

    return {
        "question": question,
        "grounding_status": grounding_status,
        "answer": answer,
        "source_chunk_ids": source_chunk_ids,
        "unresolved_topics": unresolved_topics,
        "needs_seller_attention": bool(topics),
    }