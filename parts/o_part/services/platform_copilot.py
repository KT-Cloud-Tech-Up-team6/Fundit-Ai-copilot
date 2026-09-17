"""O파트: 플랫폼·펀딩 질문 처리의 단일 진입점 (Platform Copilot).

P파트 services/product_copilot.process_product_question 과 대칭 —
인수인계 문서의 "Platform Agent 의 A2A 인터페이스" 요구에 대응한다.

주의:
이 함수는 입력이 이미 O(플랫폼·펀딩) 질문이라고 가정하지 않는다.
O 단독 FAQ 매칭(faq_id 결정)에는 분류기가 필요하므로, O파트만 등록한
전용 오케스트레이터를 내부에서 사용한다 (P/DROP 라우팅은 상위 통합 라우터 담당,
여기서는 O FAQ 매칭 + 잡담/개인문의 제외만 수행).
"""
from __future__ import annotations

from typing import Optional

from orchestrator.service import CopilotService
from parts.o_part.part import OPart
from shared.schemas import Comment, Decision, LiveContext

_service: CopilotService | None = None
DEFAULT_LIVE_ID = "default"


def _svc() -> CopilotService:
    global _service
    if _service is None:
        _service = CopilotService(parts=[OPart()])
    return _service


def set_live_context(context: LiveContext) -> None:
    """방송·펀딩 실시간 값(동적 슬롯) 주입."""
    _svc().put_context(context)


def process_platform_question(
    question: str,
    live_id: Optional[str] = None,
) -> dict:
    """플랫폼·펀딩 질문 처리의 단일 진입 함수.

    처리 흐름
    1. O 전용 분류 (FAQ 매칭 / 잡담·개인문의 제외 / 근거 없음)
    2. FAQ 원문 + 동적 슬롯 치환 답변 (LLM 답변 생성 없음)
    3. 외부(A2A/BE)에서 쓰기 쉬운 dict 반환
    """
    question = question.strip()
    if not question:
        raise ValueError("question은 비어 있을 수 없습니다.")

    ans = _svc().process(live_id or DEFAULT_LIVE_ID, Comment(text=question))

    if ans.decision == Decision.IGNORE:
        return {
            "question": question,
            "decision": "IGNORE",
            "ignored_reason": ans.ignored_reason.value if ans.ignored_reason else None,
            "answer": None,
            "faq_id": None,
            "category": None,
        }

    return {
        "question": question,
        "decision": ans.decision.value,          # ANSWER | UNANSWERABLE
        "answer": ans.answer_text if ans.decision == Decision.ANSWER else None,
        "faq_id": ans.faq_id,
        "category": ans.label,
        "strict": ans.strict,
        "source": ans.source,
        "needs_seller_attention": ans.decision == Decision.UNANSWERABLE,
    }
