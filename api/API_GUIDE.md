# Fundit AI Copilot — BE 연동 가이드 (v1)

백엔드 팀 전달용. 기능별 API 계약과 연동 순서를 정리한다.
기계용 스펙: `docs/openapi.json` (Swagger UI: 서버 실행 후 `/docs`)

- **Base Path**: `/api/v1/funding-ai`
- **인증**: `Authorization: Bearer {token}` — 서버 env `API_TOKEN` 설정 시 필수 (미설정 = 개발 모드)
- **실행**: `uvicorn api.main:app --port 8080` (env: `GEMINI_API_KEY` 필수)
- **시간값**: `at_ms` = 방송 시작 기준 ms

---

## 기능 A. 라이브 자동 답변

시청자 채팅을 분류하고, 근거가 있는 질문에 자동 답변을 만들어 반환한다.

### 연동 순서

```
[LIVE 전]  POST /lives/{id}/prepare      상품정보 색인 (필수 — 안 하면 comments 409)
           PUT  /lives/{id}/context      방송·펀딩 실시간 값 (변경 시마다 재호출)
[LIVE 중]  POST /lives/{id}/comments     BE가 도배·중복 1차 필터 → 3초 배치 전달
```

### A-1. `POST /lives/{live_id}/prepare` — 상품정보 색인

```json
{
  "product_category": "가전",
  "knowledge": [
    { "chunk_id": "kb_009", "category": "호환성",
      "text": "iOS 16 이상, Android 12 이상 지원",
      "strict": true, "source": "상품상세 p.12" }
  ]
}
```
- `strict: true` = 원문 그대로만 제공해야 하는 정보 (약관·정확 수치)
- 응답: `{ "status": "ready", "chunks": n }`
- ⚠ 현 단계(MVP)는 단일 상품 검증 — 전달 knowledge 는 저장·검증되고, 답변 근거는 내장 상품 KB 사용. 멀티 상품 동적 교체는 다음 페이즈 (계약 동일 유지)

### A-2. `PUT /lives/{live_id}/context` — 실시간 값

```json
{ "project_id": "8812",
  "broadcast": { "end_at": "2026-09-15T20:10:00+09:00", "vod_enabled": true },
  "funding": { "deadline": "2026-09-15T23:59:59+09:00", "achieved_rate": 142 },
  "extra_slots": { "early_bird_left": 6 } }
```
- 답변 내 동적 슬롯(마감일·달성률·잔여수량)에 즉시 반영

### A-3. `POST /lives/{live_id}/comments` — 댓글 배치 분석 + 답변

요청 (배치 최대 50건, 3초 단위 권장):
```json
{ "comments": [
    { "comment_id": "c_1041", "text": "흡입력 얼마나 돼요?", "at_ms": 331200 } ] }
```

응답 (실측 예시):
```json
{
  "status": "ok",
  "questions": [
    { "question_id": "q_0001", "comment_id": "c_1041",
      "text": "흡입력 얼마나 돼요?",
      "handled_by": "PRODUCT", "category": "제품 성능 및 사양", "at_ms": 331200,
      "answer": { "text": "최대 흡입력은 20,000Pa입니다.",
                  "grounding": "GROUNDED", "strict": false, "source": "kb_p_005" } },
    { "question_id": "q_0002", "comment_id": "c_1042",
      "text": "완충하면 몇 분 쓸 수 있어요?",
      "handled_by": "UNANSWERABLE", "category": "배터리 및 전원", "at_ms": 333400,
      "answer": null,
      "topics": [ { "category": "배터리", "topic": "배터리 사용시간" } ] }
  ],
  "ignored": [ { "comment_id": "c_1044", "reason": "SMALLTALK" } ]
}
```

FE 반영 규칙:

| 필드 | 시청자 화면 | 판매자 화면 |
|---|---|---|
| `answer` 있음 | 봇 말풍선 (원 댓글 인용 + answer.text) | — |
| `answer.grounding = PARTIAL_GROUNDED` | 확인된 부분만 답변된 것 — 그대로 노출 | `unresolved_topics` 가 집계에 반영됨 |
| `answer: null` (UNANSWERABLE) | **아무것도 노출하지 않음** (폴백 멘트 없음) | 기능 B 집계로 자동 반영 |
| `ignored` | 무표시 | 집계 제외 |
| `answer.strict: true` | **문구 가공 금지** (줄임·꾸밈 불가) | — |

- `handled_by`: `PRODUCT`(상품) / `PLATFORM`(플랫폼·펀딩) / `UNANSWERABLE`(근거 없음)
- `ignored.reason`: `SMALLTALK` / `NOT_QUESTION` / `PERSONAL_INQUIRY`
- 일부 실패 시 `errors[]` 에 comment_id 별로 분리 반환 (성공분은 정상 처리)

---

## 기능 B. 자주 나오는 질문 요약 (Seller Copilot)

AI가 답하지 못한 질문을 관심 유형별로 묶어 판매자에게 제공한다.
별도 입력 없음 — 기능 A 처리 과정에서 자동 집계되며, 조회만 하면 된다.

### B-1. `GET /lives/{live_id}/insights?top_n=5` — 관심사 랭킹

```json
{ "status": "ok",
  "categories": [
    { "category": "배터리", "count": 2,
      "top_topic": "배터리 사용시간", "top_topic_count": 2 } ],
  "top_questions": [
    { "representative_text": "완충하면 몇분쓸수있어요", "count": 1,
      "category": "배터리", "topic": "배터리 사용시간" } ] }
```
- **대표 질문은 AI 생성이 아니라 실제 고객 원문** (최다 등장, 동률 시 짧은 문장)
- FE: 카테고리 카드(건수) + 대표 질문 노출, 5초 폴링 권장

### B-2. `GET /lives/{live_id}/unanswered?top_n=10` — 반복 미답변 목록

```json
{ "status": "ok",
  "unanswered": [
    { "representative_text": "완충하면 몇분쓸수있어요", "count": 2,
      "examples": ["완충하면 몇 분 쓸 수 있어요?", "완충하면 몇분쓸수있어요"],
      "topics": [ { "category": "배터리", "topic": "배터리 사용시간" } ] } ] }
```
- 유사 표현은 병합되어 `count` 누적, `examples` 에 원본 최대 5건
- FE: 반복 횟수 배지 + 원본 펼침 → 판매자가 방송에서 육성 답변

---

## 공통

### 오류 계약

| 상황 | HTTP | code | BE 처리 |
|---|---|---|---|
| 색인 전 comments 호출 | 409 | `NOT_PREPARED` | prepare 선행 후 재호출 |
| 인증 실패 | 401 | `UNAUTHORIZED` | 토큰 확인 |
| 요청 형식 오류 | 422 | (FastAPI validation) | 필수값·형식 점검 |
| 개별 댓글 LLM 실패 | 200 + `errors[]` | `EVIDENCE_UNAVAILABLE` | 해당 건 재시도 — **임의 답변 대체 금지** |

### 운영 주의

- **LLM 속도 제한**: 무료 등급은 분당 15회 — 실방송은 유료 등급 필수. 배치 1건 = 댓글 수만큼 호출 (미답변은 +1~2회)
- **처리 지연**: 댓글 1건 평균 약 1초 (배치는 순차 처리 — 50건 배치면 최대 1분, 실운영 배치 크기는 3초 수신량 기준 권장)
- **상태 저장**: MVP는 인메모리 (프로세스 재시작 시 집계 초기화) — 운영 전환 시 KV/DB 교체 지점이 `api/main.py` 의 `_lives` 로 격리되어 있음
- **테스트용**: `POST /lives/{id}/reset` 으로 라이브 상태 초기화

### 검증 상태 (2026-09-10)

- 전 엔드포인트 실호출 E2E 통과 (409 가드 · 상품/플랫폼 답변 · 미답변 집계 · 반복 병합)
- 분류·답변 품질: O 164건 전 지표 PASS, P Grounding 96%/85% — `docs/EVAL_REPORT.md`
