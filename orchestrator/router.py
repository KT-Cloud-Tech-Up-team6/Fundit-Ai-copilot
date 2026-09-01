"""댓글 → (제외 / 답변불가 / 담당 파트 + faq_id) 라우팅.

등록된 모든 파트의 manifest 를 합쳐 분류 프롬프트를 만들기 때문에,
파트가 추가되면 코드 수정 없이 라우팅 대상에 자동 포함된다.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from orchestrator import llm
from shared.schemas import Decision, IgnoredReason, PartManifest, RouteMatch


class _ClassifyOut(BaseModel):
    """Gemini 구조화 출력 스키마."""

    decision: str            # ANSWER | IGNORE | UNANSWERABLE
    part_id: Optional[str] = None
    label: Optional[str] = None
    faq_id: Optional[str] = None
    ignored_reason: Optional[str] = None
    confidence: float = 0.0


PROMPT_TEMPLATE = """당신은 라이브 펀딩 방송의 실시간 채팅 상담 분류기입니다.
시청자 댓글 1건을 아래 규칙에 따라 분류하세요. 답변 문장을 만들지 말고 분류만 하세요.

## 결정 규칙 (순서대로 적용)
1. 인사·감상·리액션 등 질문이 아닌 댓글 → decision=IGNORE, ignored_reason=SMALLTALK 또는 NOT_QUESTION
2. 특정 개인의 주문·계정·결제 내역을 확인해야 하는 문의 → decision=IGNORE, ignored_reason=PERSONAL_INQUIRY
3. 아래 파트 중 하나가 담당하는 질문 → decision=ANSWER, 해당 part_id 지정
   - FAQ 색인이 있는 파트는 의미가 가장 가까운 faq_id 와 label 까지 지정
   - 오타·축약·구어체("몇시까지함?" 등)도 의미가 같으면 같은 FAQ 로 매칭
4. 질문이지만 어떤 파트의 근거로도 답할 수 없는 것 → decision=UNANSWERABLE
   (없는 정보를 추측해 faq_id 를 지정하면 절대 안 됨)

## 등록된 파트
{parts_section}

## 분류할 댓글
"{comment}"
"""


def _parts_section(manifests: list[PartManifest]) -> str:
    blocks = []
    for m in manifests:
        lines = [f"### part_id: {m.part_id}", m.description]
        if m.labels:
            lines.append(f"labels: {', '.join(m.labels)}")
        if m.faq_index:
            lines.append("FAQ 색인 (faq_id | label | 대표 질문):")
            for f in m.faq_index:
                variants = " / ".join(f.get("question_variants", [])[:5])
                lines.append(f"- {f['faq_id']} | {f['label']} | {variants}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


class Router:
    def __init__(self, manifests: list[PartManifest]):
        self._manifests = manifests
        self._known_faq_ids = {
            f["faq_id"] for m in manifests for f in m.faq_index
        }
        self._known_part_ids = {m.part_id for m in manifests}

    def route(self, comment_text: str) -> RouteMatch:
        prompt = PROMPT_TEMPLATE.format(
            parts_section=_parts_section(self._manifests),
            comment=comment_text,
        )
        out: _ClassifyOut = llm.generate_json(prompt, _ClassifyOut)
        return self._validate(out)

    def _validate(self, out: _ClassifyOut) -> RouteMatch:
        """모델 출력 검증: 모르는 faq_id/part_id 는 UNANSWERABLE 로 강등."""
        try:
            decision = Decision(out.decision)
        except ValueError:
            decision = Decision.UNANSWERABLE

        reason = None
        if out.ignored_reason:
            try:
                reason = IgnoredReason(out.ignored_reason)
            except ValueError:
                reason = IgnoredReason.NOT_QUESTION

        if decision == Decision.ANSWER:
            if out.part_id not in self._known_part_ids:
                return RouteMatch(decision=Decision.UNANSWERABLE, confidence=out.confidence)
            if out.faq_id is not None and out.faq_id not in self._known_faq_ids:
                out.faq_id = None

        return RouteMatch(
            decision=decision,
            part_id=out.part_id if decision == Decision.ANSWER else None,
            label=out.label,
            faq_id=out.faq_id,
            ignored_reason=reason if decision == Decision.IGNORE else None,
            confidence=out.confidence,
        )
