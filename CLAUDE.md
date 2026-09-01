# LiveFunding Copilot — 세션 컨텍스트 (2026-09-01 대화 기록)

> 이 파일은 Claude Code가 이 폴더를 열 때 자동 로드된다.
> 이전 세션(프로젝트 최초 생성)에서 결정된 내용의 기록이므로 지우지 말 것.

## 프로젝트가 뭔지

라이브 펀딩 AI 플랫폼의 **챗봇 상담 코파일럿**. 시청자 채팅 댓글을 받아
플랫폼·펀딩 질문에 자동 응대하는 PoC.

- 목데이터: 로보락 F25 ACE 가상 펀딩 (project_id 8812, live_id 9401, 달성률 142%)
- 스펙 원본: 사용자가 준 "코파일럿 O파트 목데이터" 문서 (FAQ 38건, 동적 슬롯 8개,
  섹션 9 PoC 질문 세트) → 전부 `parts/o_part/data/`, `eval/questions.json` 에 반영됨

## 담당 분리 (중요 — 협업 전제)

- **사용자(박금별)는 O파트만 담당**: 플랫폼·펀딩 FAQ 응대 (이 저장소에서 구현 완료)
- **P파트(상품 상담) + 55만건 상담데이터 학습은 다른 팀원 담당** → `parts/p_part/` 는
  스텁 + 구현 가이드만 있음. 그 팀원이 자기 브랜치에서 작업 후 머지하는 지점
- 그래서 구조가 **파트 플러그인식 모노레포**:
  - `shared/` — 파트 간 계약 (schemas.py + CopilotPart 추상 클래스). **변경 시 팀 합의 필요**
  - `orchestrator/` — 공용. 등록된 파트들의 manifest()로 분류 프롬프트를 자동 구성하는 라우터
  - `parts/o_part/`, `parts/p_part/` — 각 파트 완전 독립 (자기 데이터·로직 포함)
  - 파트 등록은 `api/main.py` 의 `CopilotService(parts=[OPart(), PPart()])` 한 줄

## 핵심 아키텍처 결정 (환각 차단)

1. **LLM(Gemini Flash-Lite)은 분류만 한다** — 댓글 → `ANSWER(part_id+faq_id) /
   IGNORE(SMALLTALK·NOT_QUESTION·PERSONAL_INQUIRY) / UNANSWERABLE`
2. **답변 본문은 LLM이 생성하지 않는다** — KB `answer_text` + 동적 슬롯 치환만.
   `strict: true` 항목(결제·배송·환불 약관 문구)은 원문 그대로 나감
3. 모델이 없는 faq_id/part_id 를 뱉으면 UNANSWERABLE 로 강등 (router.py `_validate`)
4. 비-strict 답변의 채팅 톤 리라이트는 `O_PART_REPHRASE=1` 옵션. 리라이트 결과의
   숫자 멀티셋이 원문과 다르면 원문으로 되돌림 (part.py `_safe_rephrase`)
5. 동적 슬롯은 기본값(`data/slots.json`) 위에 `PUT /lives/{live_id}/context` 값을 덮어씀

## 모델

- 사용자가 지정: **Gemini 3.5 Flash-Lite** → env `GEMINI_MODEL` 기본값 `gemini-3.5-flash-lite`
- 실제 API 모델 ID가 다르면 `.env` 의 `GEMINI_MODEL` 만 바꾸면 됨 (코드 수정 불필요)
- SDK: `google-genai` (신형), 구조화 출력(response_schema=pydantic) 사용 — `orchestrator/llm.py`

## 현재 상태 (2026-09-01 기준)

- [x] 전체 구조 + O파트 구현 + FastAPI + 평가 스크립트 완성, 초기 커밋됨 (15830d5)
- [x] 오프라인 스모크 통과: `python -m eval.smoke_offline` (KB 38건, 슬롯 치환, 인터페이스)
- [ ] **실제 Gemini 호출 평가 미실행** — `.env` 에 GEMINI_API_KEY 넣고
      `python -m eval.run_eval` 돌려서 섹션별 정확도 확인이 다음 작업
- [ ] 평가 결과 보고 `orchestrator/router.py` 의 PROMPT_TEMPLATE 튜닝
- [ ] **git 원격 없음** — 팀 공유 리포 만들면 remote 추가 후 push 할 것
      (사용자 규칙: 코드 수정 후 항상 commit + push)

## 실행 방법

```bash
pip install -r requirements.txt
copy .env.example .env        # GEMINI_API_KEY 입력
uvicorn api.main:app --reload # API 서버
python -m eval.run_eval       # PoC 질문 세트 정확도 리포트 (API 키 필요)
python -m eval.smoke_offline  # LLM 없이 구조 검증
```

API 흐름: `PUT /lives/9401/context` 로 방송·펀딩 컨텍스트 주입 →
`POST /lives/9401/comments {"text": "..."}` → PartAnswer JSON 반환.
UNANSWERABLE 폴백 멘트는 `orchestrator/service.py` 의 `UNANSWERABLE_FALLBACK`.
