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

## 검증 계획 (2026-09-01 사용자 제공 — 팀 공동 검증 계획서에서 발췌)

- O파트 담당 지표: V1 오드롭률 ≤3%·드롭 정확도 ≥95% / V4 라벨 Macro-F1 ≥90%,
  FAQ top-1 ≥90%, Exact Match ≥85% / **V5 할루시네이션 0건(절대 기준)** /
  V6 NO_GROUNDED_INFO 탐지율 ≥95% / V9 평균 지연 <1.5초 / V10 1,000건 비용 산정
- `eval/run_eval.py` 가 위 지표를 전부 계산해 목표 대비 PASS/FAIL 표 +
  `eval/results/report_*.json` 을 남기도록 구현됨. 목표치는 파일 상단 `TARGETS`.
- V8(유사 질문 정규화·병합)과 미답변 질문 큐 집계는 현서 담당과 공동 — 미착수
- 향후 목 댓글 250건 세트로 확장 + 3종 모델 비교(750 호출) 예정 (13-2 프로토콜)
- **API 비용은 GCP 무료 크레딧으로 진행하기로 함** — API 키 발급 시 GCP 프로젝트에
  연결하거나, Vertex 경로(`GOOGLE_GENAI_USE_VERTEXAI=1`) 사용. `.env.example` 참고

## 현재 상태 (2026-09-01 기준)

- [x] 전체 구조 + O파트 구현 + FastAPI + 평가 스크립트 완성, 초기 커밋됨 (15830d5)
- [x] 오프라인 스모크 통과: `python -m eval.smoke_offline` (KB 38건, 슬롯 치환, 인터페이스)
  (Windows 콘솔에서 한글 깨지면 `PYTHONIOENCODING=utf-8` 로 실행)
- [x] 평가 스크립트를 검증 계획 지표(V1·V4·V5·V6·V9·V10)에 맞게 재작성,
      `orchestrator/llm.py` 에 토큰 사용량 집계 + Vertex AI 인증 경로 추가
- [ ] **실제 Gemini 호출 평가 미실행** — `.env` 에 GEMINI_API_KEY 넣고
      `python -m eval.run_eval` 돌려서 지표 확인이 다음 작업
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
