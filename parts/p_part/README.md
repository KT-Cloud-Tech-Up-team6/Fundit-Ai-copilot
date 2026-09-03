# LiveFunding Copilot

라이브 펀딩 방송 채팅 상담 코파일럿 모노레포. 상담 파트를 **플러그인처럼 등록**하는 구조로,
파트별 담당자가 자기 폴더에서만 작업하고 나중에 브랜치 머지로 합칠 수 있다.

## 폴더 구조와 담당 경계

```
livefunding-copilot/
├─ shared/            # ★ 파트 간 계약 (변경 시 팀 합의 필요)
│  ├─ schemas.py      #   Comment / LiveContext / RouteMatch / PartAnswer / PartManifest
│  └─ part_base.py    #   CopilotPart 추상 클래스 — 모든 파트가 구현
├─ orchestrator/      # 라우팅·서비스 (공용)
│  ├─ llm.py          #   Gemini 호출 래퍼 (모델: GEMINI_MODEL 환경변수)
│  ├─ router.py       #   댓글 → 파트/faq_id 분류 (등록된 파트 manifest 로 프롬프트 자동 구성)
│  └─ service.py      #   파트 레지스트리 + 라이브 컨텍스트 저장소 + 처리 파이프라인
├─ parts/
│  ├─ o_part/         # ★ O파트: 플랫폼·펀딩 응대 (이 저장소에서 구현 완료)
│  │  ├─ data/        #   platform_faq.json (FAQ KB), slots.json (동적 슬롯 기본값)
│  │  ├─ kb.py  slots.py  part.py
│  └─ p_part/         # ★ P파트: 상품 상담 (다른 담당자 — 스텁만 있음)
│     └─ part.py      #   구현 가이드 주석 포함. 이 폴더 안에서만 작업하면 됨
├─ api/main.py        # FastAPI: PUT /lives/{id}/context, POST /lives/{id}/comments
└─ eval/              # PoC 테스트 세트 + 정확도 평가 스크립트
```

**머지 규칙**: P파트 브랜치는 `parts/p_part/` 만 수정한다. `shared/` 와 `orchestrator/` 는
공용이므로 인터페이스 변경이 필요하면 먼저 합의. 파트 등록은 `api/main.py` 의
`CopilotService(parts=[...])` 한 줄.

## 동작 원리 (환각 차단 설계)

1. **분류만 LLM에 시킨다** — Gemini Flash-Lite가 댓글을 `ANSWER(파트+faq_id) / IGNORE / UNANSWERABLE` 로 분류.
   프롬프트는 등록된 모든 파트의 manifest(라벨 + FAQ 색인)로 자동 구성된다.
2. **답변 본문은 KB에서 꺼낸다** — `answer_text` 에 동적 슬롯(`{deadline}` 등)만 치환.
   `strict: true` 항목(결제·배송·환불 등 약관성 문구)은 원문 그대로 나간다.
3. **모델 출력 검증** — 존재하지 않는 faq_id/part_id 를 뱉으면 UNANSWERABLE 로 강등.
4. (옵션) `O_PART_REPHRASE=1` 이면 strict 아닌 답변만 채팅 톤 리라이트.
   리라이트 결과의 숫자가 하나라도 달라지면 원문으로 되돌린다.

## 실행

```bash
pip install -r requirements.txt
copy .env.example .env   # GEMINI_API_KEY 입력

# API 서버
uvicorn api.main:app --reload

# 평가 (섹션 9 PoC 질문 세트 → 정확도 리포트)
python -m eval.run_eval
```

### API 예시

```bash
# ⑩ 방송 컨텍스트 주입
curl -X PUT localhost:8000/lives/9401/context -H "Content-Type: application/json" -d '{
  "project_id": "8812",
  "broadcast": {"start_at": "2026-09-01T20:00:00+09:00", "end_at": "2026-09-01T20:10:00+09:00", "vod_enabled": true},
  "funding": {"deadline": "2026-09-15T23:59:59+09:00", "achieved_rate": 142, "target_amount": 30000000},
  "extra_slots": {"early_bird_left": 6}
}'

# 댓글 처리
curl -X POST localhost:8000/lives/9401/comments -H "Content-Type: application/json" \
  -d '{"text": "지금 바로 돈 나가요?"}'
# → {"decision":"ANSWER","part_id":"o_part","label":"PAYMENT","faq_id":"faq_pay_001",
#    "answer_text":"지금 신청하셔도 바로 결제되지 않습니다. 펀딩이 마감된 뒤 2026년 9월 16일에 일괄 결제됩니다.",
#    "strict":true,"source":"결제 정책 1조"}
```

## P파트 담당자에게

- `parts/p_part/part.py` 의 주석이 구현 가이드다.
- `manifest()` 에 상품 카테고리·대표 질문을 채우면 제품 질문이 자동으로 라우팅되어 온다.
- `handle()` 안에서는 55만건 상담데이터 모델이든 RAG든 자유. 단 **근거 없으면
  `decision=UNANSWERABLE`** 규칙만 지키면 된다 (답변 생성 금지 정책 공유).
- 상품 KB는 `parts/p_part/data/product_kb.json` 위치를 쓰면 manifest 라벨이 자동 로드된다.
