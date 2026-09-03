"""LLM 호출 없이 구조 검증: 임포트, KB 로드, manifest, 슬롯 치환, handle() 직접 호출."""
from __future__ import annotations

from orchestrator.service import CopilotService
from parts.o_part.part import OPart
from parts.o_part import kb, slots as slot_mod
from parts.p_part.part import PPart
from shared.schemas import Comment, Decision, LiveContext, RouteMatch


def main() -> None:
    svc = CopilotService(parts=[OPart(), PPart()])
    ctx = LiveContext(
        live_id="9401",
        broadcast={"end_at": "2026-09-01T20:10:00+09:00"},
        funding={"deadline": "2026-09-15T23:59:59+09:00", "achieved_rate": 142,
                 "target_amount": 30_000_000, "current_amount": 42_600_000},
        extra_slots={"early_bird_left": 6},
    )
    svc.put_context(ctx)

    faq = kb.load_faq()
    assert len(faq) == 38, f"FAQ 개수 이상: {len(faq)}"

    slots = slot_mod.resolve(ctx)
    assert slots["end_time"] == "20시 10분", slots["end_time"]
    assert slots["deadline"] == "2026년 9월 15일 23시 59분", slots["deadline"]
    assert slots["target_amount"] == "3,000만 원", slots["target_amount"]
    assert slots["current_amount"] == "4,260만 원", slots["current_amount"]

    o = OPart()
    m = o.manifest()
    assert len(m.faq_index) == 38 and m.part_id == "o_part"

    # 라우터 결과를 흉내내 handle() 직접 호출 (LLM 미사용)
    for fid, expect_sub in [
        ("faq_bc_001", "20시 10분"),
        ("faq_fp_001", "2026년 9월 15일 23시 59분"),
        ("faq_pay_001", "2026년 9월 16일"),
        ("faq_rw_002", "6개 남았습니다"),
        ("faq_fp_005", "4,260만 원"),
    ]:
        ans = o.handle(Comment(text="t"), RouteMatch(
            decision=Decision.ANSWER, part_id="o_part", faq_id=fid), ctx)
        assert ans.decision == Decision.ANSWER and expect_sub in (ans.answer_text or ""), \
            f"{fid}: {ans.answer_text}"
        assert "{" not in ans.answer_text, f"미치환 슬롯: {ans.answer_text}"
        print(f"[O] {fid}: {ans.answer_text}")

    pm = PPart().manifest()
    assert pm.part_id == "p_part" and pm.labels, "P파트 manifest 이상"
    # P파트 retrieval 은 규칙 기반이라 LLM 없이 검증 가능
    from parts.p_part.rag_retriever import retrieve
    chunk_ids = [c["chunk_id"] for c in retrieve("흡입력 몇이에요?", top_k=3)]
    assert "kb_p_005" in chunk_ids, f"P retrieval 이상: {chunk_ids}"
    print(f"[P] manifest 라벨 {len(pm.labels)}개, retrieval OK -> {chunk_ids}")

    print("\nSMOKE OK — 구조·KB·슬롯 치환 정상")


if __name__ == "__main__":
    main()
