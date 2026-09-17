"""P파트: 상품 상담 Product Agent (RAG + 상담사 문체 — 심현서 구현).

part.py 는 오케스트레이터 계약(CopilotPart)과 P파트 단일 진입점
services/product_copilot.process_product_question() 을 잇는 어댑터일 뿐이다.
검색·Grounding·문체 적용·미답변 분석 로직은 전부 현서 모듈에 있다.

Grounding 상태 → 오케스트레이터 계약 매핑:
  GROUNDED          → ANSWER (상품 KB 근거 + 상담사 문체 답변)
  PARTIAL_GROUNDED  → ANSWER (확인 가능한 부분만 답변) + meta 로 미해결 토픽 전달
  NO_GROUNDED_INFO  → UNANSWERABLE (+ meta 로 관심 토픽 전달)

동적 KB: prepare 로 상품이 교체되면 (rag_retriever.set_product_md)
retrieve 가 호출마다 활성 KB 를 다시 읽으므로 이 어댑터는 수정 없이 동작한다.
"""
from __future__ import annotations

from shared.part_base import CopilotPart
from shared.schemas import (
    Comment, Decision, LiveContext, PartAnswer, PartManifest, RouteMatch,
)


class PPart(CopilotPart):
    part_id = "p_part"

    def manifest(self) -> PartManifest:
        # 활성 KB 기준 카테고리 (상품이 교체돼도 서비스 재기동 시 자동 반영)
        try:
            from parts.p_part.rag_retriever import load_chunks
            labels = sorted({c["category"] for c in load_chunks()})
        except Exception:
            labels = []
        return PartManifest(
            part_id=self.part_id,
            description=(
                "상품 상담 파트. 현재 방송에서 판매 중인 상품 자체의 성능·사양·"
                "기능·구성품·사용법·크기·무게·배터리·소음·관리 등 제품에 관한 "
                "질문을 담당한다. 플랫폼 운영(주문·결제·배송·환불·쿠폰) 질문은 "
                "담당하지 않는다."
            ),
            labels=labels,
            # RAG 자체 검색을 쓰므로 faq_index 는 비운다 (라벨 라우팅만 받음)
        )

    def handle(self, comment: Comment, match: RouteMatch, context: LiveContext) -> PartAnswer:
        from parts.p_part.services.product_copilot import process_product_question

        # 단일 진입점: RAG → Grounding+문체 → (미답변 분석까지) — tracker 집계는
        # 서빙 레이어(api/webtest)가 meta.unresolved_topics 로 수행한다
        result = process_product_question(comment.text)
        status = result["grounding_status"]
        meta = {
            "grounding": status,
            "source_chunk_ids": result.get("source_chunk_ids", []),
            "unresolved_topics": result.get("unresolved_topics", []),
            "needs_seller_attention": result.get("needs_seller_attention", False),
        }

        if status == "NO_GROUNDED_INFO":
            return PartAnswer(
                decision=Decision.UNANSWERABLE,
                part_id=self.part_id,
                label=match.label,
                meta=meta,
            )

        return PartAnswer(
            decision=Decision.ANSWER,
            part_id=self.part_id,
            label=match.label,
            answer_text=result["answer"],
            source=", ".join(result.get("source_chunk_ids", [])) or None,
            meta=meta,
        )
