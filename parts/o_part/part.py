"""O파트: 플랫폼·펀딩 정책 응대.

답변 본문은 절대 LLM이 생성하지 않는다.
- KB answer_text 에 슬롯을 치환해 그대로 내보낸다 (환각 차단).
- strict=False 항목만, 옵션이 켜진 경우 라이브 채팅 톤으로 가벼운 리라이트를 허용한다.
  리라이트도 수치·날짜가 하나라도 달라지면 원문으로 되돌린다.
"""
from __future__ import annotations

import os
import re

from shared.part_base import CopilotPart
from shared.schemas import (
    Comment, Decision, LiveContext, PartAnswer, PartManifest, RouteMatch,
)
from parts.o_part import kb, slots as slot_mod
from orchestrator import llm

REPHRASE_ENABLED = os.getenv("O_PART_REPHRASE", "0") == "1"

REPHRASE_PROMPT = """다음 안내 문구를 라이브 방송 채팅 답글 톤으로 한 문장~두 문장으로 자연스럽게 다듬어 주세요.
규칙: 숫자·날짜·시각·금액·조건은 글자 하나도 바꾸지 말 것. 새로운 정보를 추가하지 말 것. 이모지 금지.

원문: {text}
"""

_NUM_RE = re.compile(r"\d+")


class OPart(CopilotPart):
    part_id = "o_part"

    def manifest(self) -> PartManifest:
        faq = kb.load_faq()
        return PartManifest(
            part_id=self.part_id,
            description=(
                "플랫폼·펀딩 운영 응대 파트. 방송 시간/다시보기, 펀딩 방식/마감/달성률, "
                "결제 수단·시점, 배송 정책, 취소·환불, 리워드 옵션, 가입·로그인·알림, "
                "쿠폰·적립금 등 플랫폼 정책에 관한 질문을 담당한다. "
                "제품 자체의 성능·스펙·기능 질문은 담당하지 않는다."
            ),
            labels=sorted({f["label"] for f in faq.values()}),
            faq_index=[
                {
                    "faq_id": f["faq_id"],
                    "label": f["label"],
                    "question_variants": f["question_variants"],
                }
                for f in faq.values()
            ],
        )

    def handle(self, comment: Comment, match: RouteMatch, context: LiveContext) -> PartAnswer:
        faq = kb.load_faq().get(match.faq_id or "")
        if faq is None:
            return PartAnswer(decision=Decision.UNANSWERABLE, part_id=self.part_id)

        answer = slot_mod.fill(faq["answer_text"], slot_mod.resolve(context))

        if REPHRASE_ENABLED and not faq["strict"]:
            answer = self._safe_rephrase(answer)

        return PartAnswer(
            decision=Decision.ANSWER,
            part_id=self.part_id,
            label=faq["label"],
            faq_id=faq["faq_id"],
            answer_text=answer,
            strict=faq["strict"],
            source=faq.get("source"),
        )

    @staticmethod
    def _safe_rephrase(text: str) -> str:
        try:
            rephrased = llm.generate_text(REPHRASE_PROMPT.format(text=text))
        except Exception:
            return text
        # 숫자 멀티셋이 하나라도 달라지면 원문 유지
        if sorted(_NUM_RE.findall(rephrased)) != sorted(_NUM_RE.findall(text)):
            return text
        return rephrased or text
