# 실증 시나리오 데이터

실제 상품정보·질문 리스트·방송 영상으로 라이브 테스트를 돌리고,
그 채팅 로그를 하이라이트 쇼츠 실증까지 이어 붙이기 위한 입력 폴더다.

용량이 큰 파일(영상)과 팀 공유가 필요 없는 산출물은 git 에 올리지 않는다
(`.gitignore` 참고). 상품정보·질문셋은 팀 공유 대상이라 커밋한다.

```
testbed/scenario/
├── product/    상품정보 (AI 답변 근거)
├── questions/  질문 리스트 (가상 시청자가 칠 채팅)
├── video/      방송 영상 (gitignore)
└── exports/    실행 결과 — 채팅 로그·리포트 (gitignore)
```

---

## product/ — 상품정보

AI 가 상품 질문에 답할 근거다. **여기 없는 내용은 답하지 않는다**(환각 차단).

넣을 파일: `product.json`

```json
{
  "product_name": "로보락 F25",
  "product_category": "가전",
  "category_minor": "생활가전",
  "project_display_code": "F0000042",
  "knowledge": [
    { "chunk_id": "kb_001", "category": "제품 성능 및 사양",
      "text": "최대 흡입력은 20,000Pa입니다.",
      "strict": true, "source": "상품상세 p.14" }
  ],
  "rewards": [
    { "reward_display_code": "R0000001", "name": "얼리버드 패키지",
      "description": "본체 + 전용 바스켓 2종",
      "price": 389000, "is_limited": true, "quantity": 50, "is_early_bird": true,
      "option_groups": [ { "name": "색상", "values": ["화이트", "블랙"] } ] }
  ]
}
```

- `knowledge[]`: 상세페이지 본문을 문장 단위로 쪼갠 것. 수치·조건이 정확해야 한다
- `rewards[]`: BE `GET /projects/{id}/rewards` 응답을 그대로 넣어도 된다
- `strict: true`: 약관·정확 수치 — 문구를 바꾸지 않고 원문 그대로 답변에 쓴다

펀딩 실시간 값(마감일·달성률)은 `context.json` 으로 따로 둔다:

```json
{ "funding": { "deadline": "2026-09-15T23:59:59+09:00",
               "achieved_rate": 142, "target_amount": 30000000 },
  "broadcast": { "end_at": "2026-09-01T20:10:00+09:00", "vod_enabled": true },
  "extra_slots": { "early_bird_left": 6 } }
```

---

## questions/ — 질문 리스트

가상 시청자가 방송 중 칠 채팅이다. 아래 두 형식 모두 인식한다.

**형식 A — 시각까지 지정** (`questions.json`)

```json
[
  { "at_ms": 10000, "text": "흡입력 얼마나 돼요?" },
  { "at_ms": 25000, "text": "얼리버드 몇 개 남았어요?", "nickname": "구름토끼" }
]
```

**형식 B — 텍스트만** (`questions.txt`, 한 줄에 하나)

```
흡입력 얼마나 돼요?
얼리버드 몇 개 남았어요?
잘 보고 있어요~
```

시각이 없으면 러너가 방송 길이에 맞춰 3~8초 간격으로 자동 배치한다.
잡담·인사도 섞어 두면 AI 의 드롭 판정까지 함께 검증된다.

---

## video/ — 방송 영상

- `broadcast.mp4` 로 넣으면 러너가 자동으로 잡는다
- H.264 mp4 권장. 다른 코덱이면 재생이 끊길 수 있다
- 용량이 크므로 git 에 올리지 않는다

---

## exports/ — 실행 결과

세션이 끝나면 아래가 쌓인다. 하이라이트 쇼츠 실증의 입력이 된다.

| 파일 | 내용 | 용도 |
|---|---|---|
| `chat_log.json` | 전체 채팅 + AI 판정 (`at_ms` 포함) | 하이라이트의 질문 집중 구간 분석 입력 |
| `session_raw.json` | 세션 원본 (`/api/export` 응답) | 재분석·재현용 |
| `report.md` | 판정 분포·지연·질문 내역 | 검증 리포트 |
