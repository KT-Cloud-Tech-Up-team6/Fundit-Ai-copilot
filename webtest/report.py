"""라이브 테스트 세션 로그 → 검증 리포트 생성.

사용법:
  python -m webtest.report https://<배포주소> <비밀번호>     # 서버에서 로그 받아서 생성
  python -m webtest.report <export.json 파일경로>            # 내려받은 JSON으로 생성

산출물:
  eval/results/live_session_<ts>.json  (원본 로그 백업)
  docs/LIVE_TEST_REPORT.md             (검증 리포트 — 팀 수기 판정 칸 포함)
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent

# 라이브 테스트 세션의 댓글당 예상 비용 (평가 실측 토큰 × 공식 단가)
COST_PER_COMMENT_USD = 0.0008


def load(arg: str, password: str | None) -> dict:
    if arg.startswith("http"):
        r = httpx.get(f"{arg.rstrip('/')}/api/export", params={"password": password}, timeout=30)
        r.raise_for_status()
        return r.json()
    return json.loads(Path(arg).read_text(encoding="utf-8"))


def fmt_ts(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "-"


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    data = load(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    records = data["records"]
    started_at = (data.get("state") or {}).get("started_at")

    results = [r for r in records if r.get("type") == "result"]
    users = {r["nick"] for r in results}
    decisions = Counter(r.get("decision") or "ERROR" for r in results)
    latencies = sorted(r["latency_ms"] for r in results if r.get("latency_ms") and not r.get("error"))
    errors = [r for r in results if r.get("error")]

    # 백업 저장
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (out_dir / f"live_session_{stamp}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    n = len(results)
    avg = statistics.mean(latencies) / 1000 if latencies else 0
    p95 = latencies[max(0, round(len(latencies) * 0.95) - 1)] / 1000 if latencies else 0

    lines = [
        "# 라이브 목방송 테스트 리포트",
        "",
        f"- **세션 일시**: {datetime.now():%Y-%m-%d} (방송 시작 {fmt_ts(started_at)})",
        f"- **참가자**: {len(users)}명 ({', '.join(sorted(users))})",
        f"- **총 채팅**: {n}건",
        "",
        "## 1. 판정 분포",
        "",
        "| 판정 | 건수 | 비율 |",
        "|---|---|---|",
    ]
    for d, c in decisions.most_common():
        lines.append(f"| {d} | {c} | {c / n * 100:.1f}% |" if n else "")
    lines += [
        "",
        "## 2. 응답 속도·비용 (실측)",
        "",
        f"- 평균 지연 **{avg:.2f}초** / p95 {p95:.2f}초 (목표 < 1.5초)",
        f"- 오류(호출 실패) {len(errors)}건",
        f"- 예상 비용: {n}건 × $0.0008 ≈ **${n * COST_PER_COMMENT_USD:.2f}**",
        "",
        "## 3. 전체 채팅 판정 내역 — 팀 수기 검증용",
        "",
        "적절 칸에 O/X 를 채워 오분류를 집계한다 (자유 채팅이라 정답 라벨이 없으므로 수기 판정).",
        "",
        "| 시각 | 닉네임 | 채팅 | 판정 | 라벨/사유 | faq_id | 지연 | 적절? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    bots = {r.get("for_seq"): r for r in results}
    answers = {}
    for r in records:
        if r.get("type") == "bot":
            answers[(r.get("reply_nick"), r.get("reply_text"))] = r["text"]
    for r in results:
        label = r.get("label") or r.get("ignored_reason") or ""
        detail = "ERROR" if r.get("error") else r.get("decision", "")
        lines.append(
            f"| {fmt_ts(r['ts'])} | {r['nick']} | {r['text']} | {detail} | {label} "
            f"| {r.get('faq_id') or ''} | {r.get('latency_ms', '')}ms | |")

    lines += ["", "## 4. 봇이 실제로 내보낸 답변", ""]
    for r in records:
        if r.get("type") == "bot":
            lines.append(f"> **@{r['reply_nick']} \"{r['reply_text']}\"** → ({r['decision']}"
                         f"{' · ' + r['label'] if r.get('label') else ''}"
                         f"{' · ' + r['faq_id'] if r.get('faq_id') else ''})")
            lines.append(f"> {r['text']}")
            lines.append(">")

    if errors:
        lines += ["", "## 5. 오류 목록", ""]
        for r in errors:
            lines.append(f"- {fmt_ts(r['ts'])} {r['nick']}: \"{r['text']}\" → {r['error']}")

    out_md = ROOT / "docs" / "LIVE_TEST_REPORT.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"채팅 {n}건 / 참가자 {len(users)}명 / 평균 {avg:.2f}s / 오류 {len(errors)}건")
    print(f"리포트: {out_md}")
    print(f"원본 백업: eval/results/live_session_{stamp}.json")


if __name__ == "__main__":
    main()
