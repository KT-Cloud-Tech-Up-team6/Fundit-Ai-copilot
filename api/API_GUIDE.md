# Fundit AI Copilot — BE 연동 가이드 (v1)

백엔드 팀 전달용. 기능별 API 계약과 연동 순서를 정리한다.
기계용 스펙: `docs/openapi.json` (Swagger UI: 서버 실행 후 `/docs`)

- **Base Path**: `/api/v1/ai`
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

`live_id` = `streaming.live_sessions.public_id` (UUID)

```json
{
  "product_name": "에어쿡 프로 에어프라이어",
  "product_category": "가전",
  "category_minor": "주방가전",
  "project_display_code": "F0000042",
  "project_public_id": "018f2c1a-3b4e-7a12-9c9d-0a1b2c3d4e5f",
  "knowledge": [
    { "chunk_id": "kb_009", "category": "호환성",
      "text": "iOS 16 이상, Android 12 이상 지원",
      "strict": true, "source": "상품상세 p.12" }
  ],
  "rewards": [
    { "reward_display_code": "R0000001", "name": "얼리버드 패키지",
      "description": "본체 + 전용 바스켓 2종", "price": 89000,
      "is_limited": true, "quantity": 100, "is_early_bird": true,
      "option_groups": [ { "name": "색상", "values": ["화이트", "블랙"] } ] }
  ]
}
```

**필드 매핑 (project-service)**

| AI 필드 | BE 출처 |
|---|---|
| `product_name` | `projects.title` |
| `product_category` / `category_minor` | `projects.category_major` / `category_minor` |
| `project_display_code` | `projects.project_display_code` (F0000001) |
| `rewards[]` | `rewards` + `reward_option_groups` + `reward_option_values` |
| `rewards[].option_groups[].values` | `reward_option_values.value` 목록 |

- `rewards`를 전달하면 **리워드 가격·한정수량·구성·옵션이 자동으로 KB 청크로 변환**되어 리워드 문의에도 정확히 답변한다 (`GET /projects/{id}/rewards` 응답을 그대로 넘기면 됨)
- ⚠️ `rewards` 미전달 시 리워드 관련 질문은 플랫폼 공통 FAQ로 답변되어 **프로젝트별 실제 가격·수량과 다를 수 있음** → 전달 권장
- `strict: true` = 원문 그대로만 제공 (약관·정확 수치)
- 응답: `{ "status": "ready", "product_name": "...", "project_display_code": "F0000042", "chunks": 5, "reward_chunks": 4 }`
- ✅ **동적 KB**: 전달된 정보가 활성 상품 KB로 즉시 교체 — 상품이 바뀌면 이 API만 재호출 (재학습·재배포 불필요)
- ⚠️ MVP 한계: 활성 KB는 프로세스 전역 1개 — 동시 멀티 라이브·멀티 상품은 프로세스 분리 필요

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
    { "comment_id": "1041", "text": "흡입력 얼마나 돼요?", "at_ms": 331200,
      "sender_id": "11111111-1111-7111-8111-111111111111" } ] }
```

**필드 매핑 (chat.chat_messages)**

| AI 필드 | BE 출처 |
|---|---|
| `comment_id` | `chat_messages.id` |
| `text` | `chat_messages.content` |
| `sender_id` | `chat_messages.sender_id` (선택) |
| `at_ms` | `sent_at` − `live_sessions.actual_start_at` (방송 시작 기준 ms) |

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

## 기능 B. 자주 나오는 질문 (집계된 Q&A + 미답변 창)

기능 A 처리 과정에서 자동 집계 — 별도 입력 없이 조회·답변 API만 쓰면 된다.

**집계 규칙**
- 유사 질문은 3단 병합 (정규화 일치 → 단어 유사도 → 관심 토픽 일치), 대표 질문은 **고객 원문**
- 순위 = AI 답변 + 판매자 답변 + 미답변 **합산 누적 횟수**
- **3분 윈도우**가 끝날 때마다 해당 윈도우 TOP3 신규 질문이 '공통 질문'으로 승격.
  **이미 승격된 질문은 다음 윈도우에서 다시 수집되지 않음** (카운트만 누적)

### B-1. `GET /lives/{id}/faq?top_n=10` — 집계된 Q&A (판매자 화면 · 시청자 Q&A 버튼 공용)

```json
{ "window_sec": 180,
  "qna": [
    { "qid": "fq_0002", "representative_text": "타이머 기능 돼요?", "count": 4,
      "category": "앱·원격제어", "answered_by": "SELLER",
      "answered_by_label": "판매자", "answered_at": 1789600000.1,
      "answer": "네, 최대 12시간 예약 타이머가 있습니다.", "promoted": true } ],
  "current_window": { "window_id": 3, "top3": [ "...같은 형식..." ] } }
```
- FE 카드: 질문 + `count`건 + answer + `answered_by_label` + `answered_at`(→ "1분 전")
- `answered_by`: `SELLER`(판매자) / `AI`(AI 라이브 매니저) / `NONE`(미답변)
- 시청자 채팅의 "AI가 자동답변한 채팅입니다" 마커 = 기능 A 응답의 `answer` 존재 여부로 판단

### B-2. `GET /lives/{id}/faq/{qid}/comments` — 누적 건수 클릭 → 원본 채팅 전체 보기

```json
{ "qid": "fq_0002", "count": 4,
  "comments": [ { "comment_id": "c2", "text": "예약 타이머 있어요?", "at_ms": 20000 } ] }
```

### B-3. `GET /lives/{id}/unanswered?top_n=10` — 미답변 질문 창 (질문 요약)

```json
{ "pending":  [ { "qid": "fq_0002", "representative_text": "...", "count": 3 } ],
  "answered": [ { "qid": "fq_0007", "...": "판매자 답변 완료 건" } ] }
```
- 설명 문구: "AI가 자동답변하지 않은 질문 중 상위 누적된 질문들입니다"
- `pending` = 답변 대기 / `answered` = 답변 완료(회색 처리 영역)

### B-4. `GET /lives/{id}/unanswered/{qid}` — 질문 클릭 → 참고정보 + 답변 초안

```json
{ "question": "타이머 기능 돼요?", "count": 3,
  "reference": {
    "chunks": [ { "chunk_id": "kb_p_002", "category": "온도 조절", "text": "..." } ],
    "images": [] },
  "draft": "문의주신 예약 타이머 기능은 현재 확인이 어렵습니다. [판매자 확인 필요: 예약 타이머 탑재 여부]",
  "seller_answer": null }
```
- 상단: `reference` (관련 KB 청크 — 근거가 아니라 판매자 참고용, `images`는 상품 이미지 URL BE 연결 자리)
- 하단: `draft` — **상담사 말투 답변 초안**. 확인 안 된 사실은 `[판매자 확인 필요: ...]`로 비워둠 (임의 생성 금지)

### B-5. `POST /lives/{id}/unanswered/{qid}/answer` — [답변하기]

요청: `{ "answer_text": "네, 최대 12시간 예약 타이머가 있습니다." }`

등록되면 세 가지가 일어난다:
1. 집계된 Q&A에 **판매자 대표 답변**으로 노출
2. **이후 같은/유사 질문은 LLM 없이 이 답변으로 즉시 자동 응답** (`grounding: "SELLER_CONFIRMED"`)
3. Live Knowledge(MCP)에 등록 → 상품 지식으로 축적 (응답의 `live_knowledge_registered`)

### B-6. `GET /lives/{id}/summary?top_n=15` — 방송 종료 후 요약

```json
{ "total_questions": 132, "unique_questions": 41,
  "top_questions": [ "...합산 누적 TOP15..." ],
  "by_category": {
    "펀딩": [ "..." ], "결제": [ "..." ],
    "제품 성능 및 사양": [ "..." ], "앱·원격제어": [ "..." ] } }
```
- 카테고리 = 현서 체계 그대로 (O 8종 한글화: 펀딩·결제·배송·취소환불·리워드·계정앱·쿠폰이벤트·방송 / P 상품 카테고리·관심 토픽)

### B-7. `GET /lives/{id}/insights?top_n=5` — 관심 토픽 랭킹 (보조)

미답변 질문의 관심 유형(카테고리·Topic) 단위 랭킹 — 질문 단위(B-1~6)와 별도로 토픽 관점 요약이 필요할 때 사용.

---

## BE 저장 매핑 (live-service)

AI 응답을 BE 테이블에 그대로 적재할 수 있도록 대응 필드를 함께 제공한다.

### `chat.live_question_summaries` ← `GET /faq`

| 컬럼 | AI 응답 필드 |
|---|---|
| `session_id` | (BE 보유) live_id 로 조회 |
| `summary_text` | `qna[].summary_text` |
| `related_question_count` | `qna[].related_question_count` |
| `is_pinned` | `qna[].is_pinned` (3분 윈도우 TOP3 승격분) |

### `streaming.live_verification_posts` ← `GET /summary`

| 컬럼 | AI 응답 필드 |
|---|---|
| `question_summary` | `verification_posts[].question_summary` |
| `seller_answer` | `verification_posts[].seller_answer` |

- `verification_posts` 는 **답변이 확정된 질문만** 포함 (`answered_by`: SELLER/AI)
- project-service `POST /projects/{id}/live-verifications` 의 `questionSummaryId` 는 AI 의 `qid` 를 사용하면 추적이 이어진다

---

## 공통

### 오류 계약

전사 표준 형식 `{ "code": "...", "message": "...", "detail": null }` 를 따른다.

| 상황 | HTTP | code | BE 처리 |
|---|---|---|---|
| 색인 전 comments 호출 | 409 | `NOT_PREPARED` | prepare 선행 후 재호출 |
| 인증 실패 | 401 | `UNAUTHORIZED` | 토큰 확인 |
| 대상 없음 (qid 등) | 404 | `NOT_FOUND` | ID 확인 |
| 요청 형식 오류 | 422 | `VALIDATION_ERROR` | 필수값·형식 점검 |
| 개별 댓글 LLM 실패 | 200 + `errors[]` | `EVIDENCE_UNAVAILABLE` | 해당 건 재시도 — **임의 답변 대체 금지** |

### 운영 주의

- **LLM 속도 제한**: 무료 등급은 분당 15회 — 실방송은 유료 등급 필수. 배치 1건 = 댓글 수만큼 호출 (미답변은 +1~2회)
- **처리 지연**: 댓글 1건 평균 약 1초 (배치는 순차 처리 — 50건 배치면 최대 1분, 실운영 배치 크기는 3초 수신량 기준 권장)
- **상태 저장**: MVP는 인메모리 (프로세스 재시작 시 집계 초기화) — 운영 전환 시 KV/DB 교체 지점이 `api/main.py` 의 `_lives` 로 격리되어 있음
- **테스트용**: `POST /lives/{id}/reset` 으로 라이브 상태 초기화

### 답변 문체

- 상품 답변은 **K쇼핑 상담 데이터 기반 Counselor Style RAG** 가 적용된 상담사 말투로 나온다 ("조리 용량은 5.5L로 확인됩니다") — 별도 호출 없이 답변 생성 1회에 통합, 사실 정보는 상품 KB 에서만
- 플랫폼 답변·strict 답변은 검증 원문 그대로

### 검증 상태 (2026-09-17)

- 전 엔드포인트 실호출 E2E 통과 (409 가드 · 동적 KB 상품 교체 · 상품/플랫폼 답변 · 유사 병합·윈도우 승격 · 답변 초안 · 판매자 답변 즉시반영 · 요약)
- 분류·답변 품질: O 164건 전 지표 PASS, P Grounding 96%/85% — `docs/EVAL_REPORT.md`
