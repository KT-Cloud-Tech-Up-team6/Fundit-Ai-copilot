"""P파트 스텁: 상품 상담 파트 (다른 담당자 구현 예정).

이 파일은 인터페이스 예시이자 머지 지점이다.
P파트 담당자는 이 폴더 안에서만 작업하면 되고,
manifest()/handle() 시그니처만 유지하면 오케스트레이터에 그대로 붙는다.

구현 가이드:
- manifest(): 상품 지식 카테고리(제품 성능 및 사양, 주요 기능, 가격 및 구매 혜택 등)와
  대표 질문을 채우면 라우터가 제품 질문을 이 파트로 보낸다.
  faq_index 는 비워도 된다 (RAG/자체 검색을 쓰는 파트는 label 라우팅만 받으면 됨).
- handle(): 55만건 상담데이터 학습 모델·상품 KB 검색 등 자체 파이프라인 자유.
  단, 근거 없으면 반드시 decision=UNANSWERABLE 로 반환 (생성 금지 규칙 공유).
"""
from __future__ import annotations

import json
from pathlib import Path

from shared.part_base import CopilotPart
from shared.schemas import (
    Comment, Decision, LiveContext, PartAnswer, PartManifest, RouteMatch,
)

DATA_DIR = Path(__file__).parent / "data"


class PPart(CopilotPart):
    part_id = "p_part"

    def manifest(self) -> PartManifest:
        labels: list[str] = []
        kb_path = DATA_DIR / "product_kb.json"
        if kb_path.exists():
            raw = json.loads(kb_path.read_text(encoding="utf-8"))
            labels = sorted({c["category"] for c in raw.get("knowledge", [])})
        return PartManifest(
            part_id=self.part_id,
            description=(
                "상품 상담 파트. 제품 자체의 성능·사양·기능·구성품·사용법 등 "
                "상품 정보에 관한 질문을 담당한다. (현재 스텁 — 구현 예정)"
            ),
            labels=labels or ["제품 성능 및 사양", "주요 기능", "가격 및 구매 혜택"],
        )

    def handle(self, comment: Comment, match: RouteMatch, context: LiveContext) -> PartAnswer:
        # TODO(P파트 담당): 상품 KB 검색 + 답변 파이프라인으로 교체
        return PartAnswer(
            decision=Decision.UNANSWERABLE,
            part_id=self.part_id,
            label=match.label,
            meta={"stub": True, "note": "P파트 미구현 — 라우팅만 동작"},
        )
