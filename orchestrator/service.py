"""코파일럿 서비스: 파트 레지스트리 + 라이브 컨텍스트 저장소 + 댓글 처리 파이프라인."""
from __future__ import annotations

from shared.part_base import CopilotPart
from shared.schemas import Comment, Decision, LiveContext, PartAnswer, RouteMatch
from orchestrator.router import Router

UNANSWERABLE_FALLBACK = (
    "해당 내용은 방송 중 바로 확인이 어려워요. "
    "프로젝트 페이지의 '문의하기'로 남겨주시면 메이커 확인 후 안내드릴게요."
)


class CopilotService:
    def __init__(self, parts: list[CopilotPart]):
        self._parts: dict[str, CopilotPart] = {p.part_id: p for p in parts}
        self._router = Router([p.manifest() for p in parts])
        self._contexts: dict[str, LiveContext] = {}

    # ---- 컨텍스트 (PUT /lives/{live_id}/context) ----
    def put_context(self, ctx: LiveContext) -> None:
        self._contexts[ctx.live_id] = ctx

    def get_context(self, live_id: str) -> LiveContext:
        return self._contexts.get(live_id) or LiveContext(live_id=live_id)

    # ---- 댓글 처리 ----
    def process(self, live_id: str, comment: Comment) -> PartAnswer:
        match: RouteMatch = self._router.route(comment.text)

        if match.decision == Decision.IGNORE:
            return PartAnswer(
                decision=Decision.IGNORE,
                ignored_reason=match.ignored_reason,
                meta={"confidence": match.confidence},
            )

        if match.decision == Decision.UNANSWERABLE or match.part_id is None:
            return PartAnswer(
                decision=Decision.UNANSWERABLE,
                answer_text=UNANSWERABLE_FALLBACK,
                meta={"confidence": match.confidence},
            )

        part = self._parts[match.part_id]
        answer = part.handle(comment, match, self.get_context(live_id))
        answer.meta.setdefault("confidence", match.confidence)
        # 파트가 근거를 못 찾은 경우에도 동일한 폴백 멘트로 통일
        if answer.decision == Decision.UNANSWERABLE and not answer.answer_text:
            answer.answer_text = UNANSWERABLE_FALLBACK
        return answer
