"""실증 시나리오 러너.

testbed/scenario/ 의 실제 상품정보·질문 리스트·방송 영상을 읽어
라이브 테스트 서버에 주입하고, 방송 시작과 함께 질문을 흘려보낸다.
종료 후 채팅 로그를 하이라이트 쇼츠 실증 입력 형식으로 내보낸다.

사용법 (테스트 서버가 떠 있어야 한다):
  python -m testbed.run_scenario                 # 준비 + 방송 대기 후 질문 송출
  python -m testbed.run_scenario --prepare-only  # 상품·영상만 주입하고 종료
  python -m testbed.run_scenario --export-only   # 실행 결과만 내보내기

입력: testbed/scenario/{product,questions,video}/
출력: testbed/scenario/exports/
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from pathlib import Path

import httpx

SCENARIO = Path(__file__).parent / "scenario"
UPLOADS = Path(__file__).parent / "uploads"
EXPORTS = SCENARIO / "exports"

NICKS = ["구름토끼", "살림왕", "먼지없는집", "쇼핑홀릭", "라이브죽순이", "청소는귀찮아",
         "미니멀리스트", "월급루팡", "혼수준비중", "집순이", "댕댕이집사", "새벽배송러"]


# =========================================================
# 입력 로드
# =========================================================

def load_product() -> dict | None:
    for name in ("product.json", "products.json"):
        p = SCENARIO / "product" / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def load_context() -> dict | None:
    p = SCENARIO / "product" / "context.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_questions() -> list[dict]:
    """형식 A(json, at_ms 포함) / 형식 B(txt, 한 줄 하나) 모두 인식."""
    d = SCENARIO / "questions"
    for p in sorted(d.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw.get("questions", raw) if isinstance(raw, dict) else raw
        out = []
        for i, q in enumerate(items):
            if isinstance(q, str):
                out.append({"text": q})
            else:
                out.append({
                    "text": q.get("text") or q.get("question") or q.get("content", ""),
                    "at_ms": q.get("at_ms") or q.get("atMs"),
                    "nickname": q.get("nickname") or q.get("nick"),
                })
        return [q for q in out if q["text"].strip()]

    for p in sorted(d.glob("*.txt")):
        return [{"text": line.strip()}
                for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return []


def find_video() -> Path | None:
    d = SCENARIO / "video"
    for pattern in ("broadcast.*", "*.mp4", "*.mov", "*.webm"):
        for p in sorted(d.glob(pattern)):
            if p.is_file():
                return p
    return None


# =========================================================
# 준비
# =========================================================

def prepare(base: str, pw: str) -> None:
    product = load_product()
    if product is None:
        print("! scenario/product/product.json 이 없습니다 — 상품 질문은 답변되지 않습니다")
    else:
        body = {
            "product_name": product.get("product_name", "상품"),
            "product_category": product.get("product_category", "기타"),
            "category_minor": product.get("category_minor"),
            "project_display_code": product.get("project_display_code"),
            "knowledge": product.get("knowledge", []),
            "rewards": product.get("rewards", []),
        }
        r = httpx.post(f"{base}/api/prepare", json={"password": pw, "product": body}, timeout=60)
        if r.status_code == 404:
            print("! 서버에 /api/prepare 가 없습니다 — testbed/app.py 갱신이 필요합니다")
        else:
            print("상품 색인:", r.json())

    ctx = load_context()
    if ctx:
        r = httpx.post(f"{base}/api/context", json={"password": pw, "context": ctx}, timeout=30)
        print("실시간 값:", r.json() if r.status_code == 200 else r.status_code)

    video = find_video()
    if video is None:
        print("! scenario/video/ 에 영상이 없습니다 — 기존 업로드 영상을 사용합니다")
    else:
        UPLOADS.mkdir(parents=True, exist_ok=True)
        dest = UPLOADS / f"scenario{video.suffix.lower()}"
        if not dest.exists() or dest.stat().st_size != video.stat().st_size:
            print(f"영상 복사 중... ({video.stat().st_size / 1048576:.0f}MB)")
            shutil.copy2(video, dest)
        r = httpx.post(f"{base}/api/set-video",
                       json={"password": pw, "url": f"/media/{dest.name}"}, timeout=30)
        print("영상 연결:", r.json())


# =========================================================
# 질문 송출
# =========================================================

def run_questions(base: str, pw: str, questions: list[dict]) -> None:
    print(f"\n질문 {len(questions)}건 대기 — [방송 시작]을 누르면 송출합니다")
    while True:
        st = httpx.get(f"{base}/api/state", params={"password": pw, "since": 0}, timeout=10).json()
        if st.get("started_at"):
            break
        time.sleep(2)
    started = st["started_at"]
    print("방송 감지 — 송출 시작\n")

    timed = [q for q in questions if q.get("at_ms") is not None]
    untimed = [q for q in questions if q.get("at_ms") is None]

    # 시각 없는 질문은 3~8초 간격으로 배치
    cursor = 5000
    for q in untimed:
        q["at_ms"] = cursor
        cursor += random.randint(3000, 8000)

    plan = sorted(timed + untimed, key=lambda q: q["at_ms"])
    sent = 0
    for q in plan:
        wait = (started + q["at_ms"] / 1000) - time.time()
        if wait > 0:
            time.sleep(wait)
        nick = q.get("nickname") or random.choice(NICKS)
        try:
            r = httpx.post(f"{base}/api/chat",
                           json={"nickname": nick, "password": pw, "text": q["text"]},
                           timeout=60).json()
            sent += 1
            print(f"[{sent:3d}] {q['at_ms'] // 1000:>4}s {nick}: {q['text']}"
                  f"  -> {r.get('decision') or r.get('error')}")
        except Exception as e:
            print(f"[!] {q['text']} -> {e}")
    print(f"\n송출 완료 — 총 {sent}건")


# =========================================================
# 내보내기 (하이라이트 실증 입력)
# =========================================================

def export(base: str, pw: str) -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    data = httpx.get(f"{base}/api/export", params={"password": pw}, timeout=60).json()
    (EXPORTS / "session_raw.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    started = (data.get("state") or {}).get("started_at") or 0
    records = data.get("records", [])

    # 하이라이트 쇼츠 실증 입력 형식 — at_ms 기준 채팅 시계열
    chats = []
    seq = 0
    for r in records:
        if r.get("type") != "user":
            continue
        seq += 1
        chats.append({
            "commentId": f"c_{seq:04d}",
            "text": r.get("text", ""),
            "atMs": max(0, int((r.get("ts", started) - started) * 1000)),
            "kind": "chat",
            "nickname": r.get("nick"),
        })

    verdicts = {r.get("text"): r for r in records if r.get("type") == "result"}
    out = {
        "source": "testbed scenario",
        "broadcast_started_at": started,
        "total_chats": len(chats),
        "chats": chats,
        "ai_verdicts": [
            {"text": t, "decision": v.get("decision"), "label": v.get("label"),
             "latency_ms": v.get("latency_ms")}
            for t, v in verdicts.items()
        ],
    }
    (EXPORTS / "chat_log.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n내보내기 완료 ({len(chats)}건)")
    print(f"  {EXPORTS / 'chat_log.json'}     ← 하이라이트 쇼츠 실증 입력")
    print(f"  {EXPORTS / 'session_raw.json'}  ← 세션 원본")
    print(f"\n리포트: python -m testbed.report {base} {pw}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--password", default="team-only")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--export-only", action="store_true")
    args = ap.parse_args()

    base, pw = args.base.rstrip("/"), args.password

    if args.export_only:
        export(base, pw)
        return

    prepare(base, pw)
    if args.prepare_only:
        return

    questions = load_questions()
    if not questions:
        print("\n! scenario/questions/ 에 질문 파일이 없습니다 — 송출을 건너뜁니다")
        return
    run_questions(base, pw, questions)
    export(base, pw)


if __name__ == "__main__":
    main()
