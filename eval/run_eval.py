"""PoC 테스트 세트 평가 스크립트.

실행 (프로젝트 루트에서):  python -m eval.run_eval
GEMINI_API_KEY 필요 (.env). 섹션별 정확도와 오분류 목록을 출력한다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from orchestrator.service import CopilotService
from parts.o_part.part import OPart
from parts.p_part.part import PPart
from shared.schemas import Comment, Decision, LiveContext

LIVE_ID = "9401"


def build_service() -> CopilotService:
    svc = CopilotService(parts=[OPart(), PPart()])
    # ⑩ PUT /lives/{live_id}/context 목데이터와 동일한 컨텍스트 주입
    svc.put_context(LiveContext(
        live_id=LIVE_ID,
        project_id="8812",
        broadcast={
            "start_at": "2026-09-01T20:00:00+09:00",
            "end_at": "2026-09-01T20:10:00+09:00",
            "vod_enabled": True,
        },
        funding={
            "deadline": "2026-09-15T23:59:59+09:00",
            "achieved_rate": 142,
            "target_amount": 30_000_000,
        },
        extra_slots={"early_bird_left": 6},
    ))
    return svc


def main() -> None:
    questions = json.loads(
        (Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    svc = build_service()
    failures: list[str] = []
    scores: dict[str, tuple[int, int]] = {}

    def run_set(name: str, items: list[dict], check) -> None:
        ok = 0
        for q in items:
            ans = svc.process(LIVE_ID, Comment(text=q["text"]))
            passed, detail = check(q, ans)
            ok += passed
            mark = "O" if passed else "X"
            print(f"  [{mark}] {q['text']!r:40s} -> {detail}")
            if not passed:
                failures.append(f"{name}: {q['text']!r} -> {detail}")
            time.sleep(0.2)  # rate limit 완화
        scores[name] = (ok, len(items))

    print("== answerable (category + faq_id) ==")
    run_set("answerable", questions["answerable"], lambda q, a: (
        a.decision == Decision.ANSWER and a.faq_id == q["faq_id"],
        f"{a.decision.value} {a.faq_id} | {a.answer_text}",
    ))

    print("\n== colloquial (category) ==")
    run_set("colloquial", questions["colloquial"], lambda q, a: (
        a.decision == Decision.ANSWER and a.label == q["category"],
        f"{a.decision.value} {a.label} {a.faq_id}",
    ))

    print("\n== unanswerable ==")
    run_set("unanswerable", questions["unanswerable"], lambda q, a: (
        a.decision == Decision.UNANSWERABLE,
        f"{a.decision.value} {a.faq_id or ''}",
    ))

    print("\n== ignored ==")
    run_set("ignored", questions["ignored"], lambda q, a: (
        a.decision == Decision.IGNORE
        and (a.ignored_reason and a.ignored_reason.value) == q["reason"],
        f"{a.decision.value} {a.ignored_reason.value if a.ignored_reason else ''}",
    ))

    print("\n===== 결과 =====")
    total_ok = total_n = 0
    for name, (ok, n) in scores.items():
        total_ok += ok
        total_n += n
        print(f"{name:12s}: {ok}/{n} ({ok / n * 100:.0f}%)")
    print(f"{'TOTAL':12s}: {total_ok}/{total_n} ({total_ok / total_n * 100:.0f}%)")
    if failures:
        print("\n오분류:")
        for f in failures:
            print(" -", f)


if __name__ == "__main__":
    main()
