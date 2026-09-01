"""PoC 평가 스크립트 — 검증 계획(V1~V10) 중 O파트 담당 지표 측정.

실행 (프로젝트 루트에서):  python -m eval.run_eval
GEMINI_API_KEY 필요 (.env 참고).

측정 지표 (검증 계획 13-2 O파트 프로토콜 기준):
  V1  드롭 정확도 ≥ 95% / 오드롭률(정상 질문을 IGNORE로 버린 비율) ≤ 3%
  V4  라벨 Macro-F1 ≥ 90%, FAQ top-1 ≥ 90%, Exact Match ≥ 85%
  V5  할루시네이션 0건 — ANSWER 본문의 숫자가 KB 슬롯 치환 원문과 다르면 카운트
  V6  NO_GROUNDED_INFO(UNANSWERABLE) 탐지율 ≥ 95%
  V9  댓글당 평균 처리 지연 < 1.5초
  V10 호출·토큰 집계 → 1,000건 비용 추정
      (단가는 env GEMINI_PRICE_IN_PER_1M / GEMINI_PRICE_OUT_PER_1M, USD/1M tokens)

결과: 콘솔 리포트 + eval/results/report_<timestamp>.json
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from orchestrator import llm
from orchestrator.service import CopilotService
from parts.o_part import kb, slots as slot_mod
from parts.o_part.part import OPart
from parts.p_part.part import PPart
from shared.schemas import Comment, Decision, LiveContext

LIVE_ID = "9401"

# 검증 계획 목표치. (지표 키, 표시명, 목표, 방향)  방향 ">=" 이상 / "<=" 이하
TARGETS = [
    ("drop_accuracy",      "V1 드롭 정확도",             0.95, ">="),
    ("misdrop_rate",       "V1 오드롭률",                0.03, "<="),
    ("label_macro_f1",     "V4 라벨 Macro-F1",           0.90, ">="),
    ("faq_top1_accuracy",  "V4 FAQ top-1 정확도",        0.90, ">="),
    ("exact_match",        "V4 Exact Match",             0.85, ">="),
    ("hallucination_count","V5 할루시네이션 건수",        0,    "<="),
    ("ungrounded_detect",  "V6 NO_GROUNDED_INFO 탐지율", 0.95, ">="),
    ("latency_avg_sec",    "V9 평균 처리 지연(초)",       1.5,  "<="),
]

_NUM_RE = re.compile(r"\d+")


def build_service() -> tuple[CopilotService, LiveContext]:
    ctx = LiveContext(
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
    )
    svc = CopilotService(parts=[OPart(), PPart()])
    svc.put_context(ctx)  # PUT /lives/{live_id}/context 목데이터와 동일
    return svc, ctx


def collect(svc: CopilotService) -> list[dict]:
    """전 섹션 실행. 섹션별 gold 기대값과 예측·지연을 record 로 남긴다."""
    questions = json.loads(
        (Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    records: list[dict] = []

    section_gold = {
        # (gold decision, gold 필드 목록)
        "answerable":   Decision.ANSWER,
        "colloquial":   Decision.ANSWER,
        "unanswerable": Decision.UNANSWERABLE,
        "ignored":      Decision.IGNORE,
    }

    for section, gold_decision in section_gold.items():
        print(f"\n== {section} ==")
        for q in questions[section]:
            rec = {
                "section": section,
                "text": q["text"],
                "gold_decision": gold_decision.value,
                "gold_label": q.get("category"),
                "gold_faq_id": q.get("faq_id"),
                "gold_reason": q.get("reason"),
            }
            t0 = time.perf_counter()
            try:
                a = svc.process(LIVE_ID, Comment(text=q["text"]))
            except Exception as e:  # API 오류도 오답으로 기록하고 계속 진행
                rec.update(error=str(e), latency_sec=time.perf_counter() - t0)
                records.append(rec)
                print(f"  [!] {q['text']!r} -> ERROR {e}")
                time.sleep(1.0)
                continue
            rec.update(
                latency_sec=round(time.perf_counter() - t0, 3),
                pred_decision=a.decision.value,
                pred_part=a.part_id,
                pred_label=a.label,
                pred_faq_id=a.faq_id,
                pred_reason=a.ignored_reason.value if a.ignored_reason else None,
                answer_text=a.answer_text,
            )
            records.append(rec)
            mark = "O" if _exact_match(rec) else "X"
            print(f"  [{mark}] {q['text']!r:40s} -> {a.decision.value}"
                  f" {a.label or ''} {a.faq_id or ''}"
                  f" {rec['pred_reason'] or ''} ({rec['latency_sec']:.2f}s)")
            time.sleep(0.2)  # rate limit 완화
    return records


def _exact_match(r: dict) -> bool:
    """섹션별 정답 기준을 모두 만족하는가 (13-2 Exact Match)."""
    if "error" in r:
        return False
    if r["pred_decision"] != r["gold_decision"]:
        return False
    if r["section"] == "answerable":
        return r["pred_label"] == r["gold_label"] and r["pred_faq_id"] == r["gold_faq_id"]
    if r["section"] == "colloquial":
        return r["pred_label"] == r["gold_label"]
    if r["section"] == "ignored":
        return r["pred_reason"] == r["gold_reason"]
    return True  # unanswerable: decision 일치면 성공


def _macro_f1(records: list[dict]) -> tuple[float, dict[str, dict]]:
    """O 8라벨 Macro-F1. gold 라벨은 answerable·colloquial 에만 있고,
    다른 섹션에서 ANSWER 로 잘못 라벨을 붙이면 해당 라벨의 FP 로 계산된다."""
    labels = sorted({r["gold_label"] for r in records if r["gold_label"]})
    per: dict[str, dict] = {}
    f1s = []
    for lb in labels:
        tp = sum(1 for r in records if r["gold_label"] == lb and r.get("pred_label") == lb
                 and r.get("pred_decision") == "ANSWER")
        fp = sum(1 for r in records if r["gold_label"] != lb and r.get("pred_label") == lb
                 and r.get("pred_decision") == "ANSWER")
        fn = sum(1 for r in records if r["gold_label"] == lb
                 and not (r.get("pred_label") == lb and r.get("pred_decision") == "ANSWER"))
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
        per[lb] = {"precision": round(p, 4), "recall": round(rc, 4),
                   "f1": round(f1, 4), "support": tp + fn}
        f1s.append(f1)
    return (sum(f1s) / len(f1s) if f1s else 0.0), per


def _hallucination_count(records: list[dict], ctx: LiveContext) -> int:
    """V5: ANSWER 본문의 숫자 멀티셋이 KB 슬롯 치환 원문과 다르면 할루시네이션."""
    faq_map = kb.load_faq()
    resolved = slot_mod.resolve(ctx)
    count = 0
    for r in records:
        if r.get("pred_decision") != "ANSWER" or not r.get("answer_text"):
            continue
        faq = faq_map.get(r.get("pred_faq_id") or "")
        if faq is None:
            continue  # o_part 외 파트 답변은 여기서 검사하지 않음
        expected = slot_mod.fill(faq["answer_text"], resolved)
        if sorted(_NUM_RE.findall(r["answer_text"])) != sorted(_NUM_RE.findall(expected)):
            count += 1
            r["hallucination"] = True
    return count


def compute_metrics(records: list[dict], ctx: LiveContext) -> dict:
    by = lambda s: [r for r in records if r["section"] == s]
    answerable, colloquial = by("answerable"), by("colloquial")
    unanswerable, ignored = by("unanswerable"), by("ignored")
    real_questions = answerable + colloquial + unanswerable  # IGNORE 가 아니어야 하는 것

    macro_f1, per_label = _macro_f1(records)
    latencies = sorted(r["latency_sec"] for r in records if "latency_sec" in r)
    p95 = latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)] if latencies else 0.0

    m = {
        "n_total": len(records),
        # V1
        "drop_accuracy": _rate(ignored, lambda r: r.get("pred_decision") == "IGNORE"),
        "misdrop_rate": _rate(real_questions, lambda r: r.get("pred_decision") == "IGNORE"),
        # V4
        "label_macro_f1": round(macro_f1, 4),
        "per_label": per_label,
        "faq_top1_accuracy": _rate(answerable, lambda r: r.get("pred_faq_id") == r["gold_faq_id"]),
        "exact_match": _rate(records, _exact_match),
        # V5
        "hallucination_count": _hallucination_count(records, ctx),
        # V6
        "ungrounded_detect": _rate(unanswerable, lambda r: r.get("pred_decision") == "UNANSWERABLE"),
        # 보조: 드롭 사유까지 맞춘 비율
        "drop_reason_accuracy": _rate(ignored, _exact_match),
        # V9
        "latency_avg_sec": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "latency_p95_sec": round(p95, 3),
        "latency_max_sec": round(latencies[-1], 3) if latencies else 0.0,
    }

    # V10: 토큰·비용 (llm.usage 는 이번 실행 동안 누적된 값)
    u = dict(llm.usage)
    m["llm_calls"] = u["calls"]
    m["prompt_tokens"] = u["prompt_tokens"]
    m["output_tokens"] = u["output_tokens"]
    n = len(records) or 1
    price_in = float(os.getenv("GEMINI_PRICE_IN_PER_1M", "0") or 0)
    price_out = float(os.getenv("GEMINI_PRICE_OUT_PER_1M", "0") or 0)
    if price_in or price_out:
        cost = (u["prompt_tokens"] * price_in + u["output_tokens"] * price_out) / 1_000_000
        m["cost_usd_this_run"] = round(cost, 6)
        m["cost_usd_per_1000_comments"] = round(cost / n * 1000, 4)
    else:
        m["cost_usd_this_run"] = None  # 단가 미설정: .env 에 GEMINI_PRICE_*_PER_1M 입력
    return m


def _rate(items: list[dict], pred) -> float:
    return round(sum(1 for r in items if pred(r)) / len(items), 4) if items else 0.0


def report(records: list[dict], m: dict) -> None:
    print("\n===== 검증 계획 대비 결과 =====")
    print(f"{'지표':28s} {'측정':>8s} {'목표':>8s}  판정")
    for key, name, target, direction in TARGETS:
        val = m[key]
        ok = val <= target if direction == "<=" else val >= target
        if isinstance(target, float) and target < 1 or key in ("misdrop_rate",):
            shown_v, shown_t = f"{val * 100:.1f}%", f"{'≤' if direction == '<=' else '≥'}{target * 100:.0f}%"
        else:
            shown_v, shown_t = f"{val}", f"{'≤' if direction == '<=' else '≥'}{target}"
        print(f"{name:28s} {shown_v:>8s} {shown_t:>8s}  {'PASS' if ok else 'FAIL'}")

    print(f"\nV9 지연: 평균 {m['latency_avg_sec']}s / p95 {m['latency_p95_sec']}s / 최대 {m['latency_max_sec']}s")
    print(f"V10 사용량: 호출 {m['llm_calls']}회, 입력 {m['prompt_tokens']} tok, 출력 {m['output_tokens']} tok"
          + (f", 1,000건 추정 ${m['cost_usd_per_1000_comments']}" if m.get("cost_usd_per_1000_comments") is not None
             else "  (단가 미설정 → .env GEMINI_PRICE_IN_PER_1M / GEMINI_PRICE_OUT_PER_1M)"))

    print("\n라벨별 F1 (V4):")
    for lb, s in m["per_label"].items():
        print(f"  {lb:16s} P {s['precision'] * 100:5.1f}%  R {s['recall'] * 100:5.1f}%"
              f"  F1 {s['f1'] * 100:5.1f}%  (n={s['support']})")

    failures = [r for r in records if not _exact_match(r)]
    if failures:
        print("\n오분류/오류:")
        for r in failures:
            got = r.get("error") or (
                f"{r.get('pred_decision')} {r.get('pred_label') or ''} "
                f"{r.get('pred_faq_id') or ''} {r.get('pred_reason') or ''}")
            print(f" - [{r['section']}] {r['text']!r} -> {got}")


def main() -> None:
    svc, ctx = build_service()
    llm.reset_usage()
    records = collect(svc)
    metrics = compute_metrics(records, ctx)
    report(records, metrics)

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"report_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({
        "model": llm.DEFAULT_MODEL,
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics,
        "records": records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n리포트 저장: {out}")


if __name__ == "__main__":
    main()
