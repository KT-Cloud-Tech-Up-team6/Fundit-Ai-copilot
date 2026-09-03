"""P파트: 상품 상담 (RAG 기반 — 심현서 구현).

part.py 는 오케스트레이터 계약(CopilotPart)과 P파트 RAG 파이프라인을 잇는
어댑터일 뿐이다. Grounding 판정·답변 생성 로직은 rag_answer/rag_retriever 에 있고,
미답변 관심사 분석·집계는 unanswered_analyzer/interest_tracker 에 있다.

Grounding 상태 → 오케스트레이터 계약 매핑:
  GROUNDED          → ANSWER (상품 KB 근거 답변)
  PARTIAL_GROUNDED  → ANSWER (확인 가능한 부분만 답변) + meta.grounding 으로 표시
                      — 소비자 화면·판매자 알림 분기는 호출 측(webtest 등)이 결정
  NO_GROUNDED_INFO  → UNANSWERABLE
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from shared.part_base import CopilotPart
from shared.schemas import (
    Comment, Decision, LiveContext, PartAnswer, PartManifest, RouteMatch,
)

DATA_DIR = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def load_product() -> dict:
    return json.loads((DATA_DIR / "product_5454434.json").read_text(encoding="utf-8"))


class PPart(CopilotPart):
    part_id = "p_part"

    def manifest(self) -> PartManifest:
        product = load_product()
        labels = sorted({c["category"] for c in product["knowledge"]})
        return PartManifest(
            part_id=self.part_id,
            description=(
                f"상품 상담 파트. 판매 상품({product['product_name']})의 성능·사양·"
                "기능·구성품·사용법·크기·무게·배터리·소음 등 제품 자체에 관한 "
                "질문을 담당한다. 플랫폼 운영(주문·결제·배송·환불·쿠폰) 질문은 "
                "담당하지 않는다."
            ),
            labels=labels,
            # RAG 자체 검색을 쓰므로 faq_index 는 비운다 (라벨 라우팅만 받음)
        )

    def handle(self, comment: Comment, match: RouteMatch, context: LiveContext) -> PartAnswer:
        from parts.p_part.rag_answer import answer_question

        result = answer_question(comment.text)
        status = result["grounding_status"]
        meta = {
            "grounding": status,
            "source_chunk_ids": result.get("source_chunk_ids", []),
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
