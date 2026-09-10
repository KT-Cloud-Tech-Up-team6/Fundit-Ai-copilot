# Fundit AI Copilot — 세션 컨텍스트

> Claude Code 가 이 폴더를 열 때 자동 로드된다. 이전 세션 결정 기록이므로 지우지 말 것.

## 프로젝트

라이브 커머스/펀딩 방송의 **챗봇 상담 코파일럿**. 시청자 채팅을 분류해
O파트(플랫폼·펀딩 FAQ)와 P파트(상품 RAG)가 답하고, 근거 없는 질문은
판매자 알림으로 보낸다. 목데이터: 로보락 F25 (project 8812, live 9401, 달성률 142%).

## 담당·브랜치 설계 (2026-09-03 통합 완료)

- **원격**: `mvp = github.com/KT-Cloud-Tech-Up-team6/Fundit-Ai-copilot` (**push 대상 팀 리포** — 2026-09-04 생성, 2026-09-10 리네임)
  / `origin = …/live-commerce-copilot-mvp1` (현서 원본, 읽기 전용 — byeol-lab 쓰기 권한 없음)
- **main**: 통합 브랜치 (O+P+webtest 병합 완료, 어댑터·인증 통일 포함)
- **feat/o-part**: 박금별 — O파트 + 공용 구조(shared/orchestrator/api) + eval/o_part
- **feat/p-part**: 심현서 — P파트 RAG (재배치만, **로직 무변경 원칙**) + eval/p_part
- **feat/webtest**: 라이브 목방송 테스트 환경 (완전 분리 폴더)
- push: `git push mvp <브랜치>` (gh CLI 인증 완료 상태)

## 폴더 양식 (통일됨)

```
shared/          파트 간 계약 (schemas + CopilotPart) — 변경 시 팀 합의
orchestrator/    라우터(분류 프롬프트)·서비스·공용 llm 클라이언트(인증 env 통일)
parts/o_part/    O파트: KB 38건 FAQ + 슬롯 치환 (환각 구조 차단) + data/
parts/p_part/    P파트(현서): rag_retriever/rag_answer(3단 Grounding)/
                 unanswered_analyzer/interest_tracker + data/ + part.py(어댑터만 내 코드)
api/             FastAPI (PoC API)
eval/{o_part,p_part}/  파트별 평가 (각자 data/ 포함), eval/results/ 공용(무시됨)
webtest/         라이브 목방송 테스트 웹앱 (영상+채팅+판매자알림+시뮬레이터+리포트)
docs/            EVAL_REPORT.md(O 164건 평가), LIVE_TEST_REPORT.md(세션 리포트)
```

## 핵심 아키텍처

1. 라우터(Gemini)가 댓글 분류: ANSWER(part_id)/IGNORE(사유)/UNANSWERABLE
   - FAQ 색인 있는 파트(O)는 faq_id 까지 매칭, 색인 없는 파트(P)는 주제 라우팅만
     하고 근거 판정은 파트가 자체 수행 (router.py 프롬프트에 명시)
2. O파트: 답변 본문 LLM 생성 금지 — KB 원문 + 동적 슬롯 치환만. strict 는 원문 고정
3. P파트(현서): 규칙 기반 retrieval → Gemini Grounding 3단 판정
   (GROUNDED/PARTIAL_GROUNDED/NO_GROUNDED_INFO) → 어댑터가 ANSWER/UNANSWERABLE 매핑
4. UNANSWERABLE 은 시청자 채팅 폴백 대신 **판매자 알림**(webtest 오른쪽 패널).
   P파트 미답변은 현서 analyzer 로 관심 유형(카테고리·토픽) 분석 + interest_tracker 집계
5. 모델: `gemini-3.5-flash-lite`, 인증은 orchestrator/llm.py 로 통일
   (env: GEMINI_API_KEY 또는 GOOGLE_GENAI_USE_VERTEXAI=1)

## 현서 코드 취급 원칙 (사용자 지시)

- **로직·프롬프트 무변경**. 허용된 수정: 파일 이동에 따른 경로·임포트,
  인증 클라이언트 구성의 공용화(llm.client()) 뿐
- 채팅 필터링(eval/p_part/mvp_live_test.py 의 is_question_comment)과
  자주 묻는 질문 수집(interest_tracker viewer_questions) 반드시 보존

## 평가 현황

- O파트 164건 (P 통합 라우터 기준, 튜닝 6회차, 2026-09-04): **전 지표 PASS**
  — V1 100%/오드롭 0, Macro-F1 99.5, top-1 98.7, EM 98.2, 할루시네이션 0,
  V6 96.4%, 평균 0.98s — docs/EVAL_REPORT.md
- P파트(현서 자체): 100건 리플레이 Grounding 정확도 85% — parts/p_part/README.md
- 라이브 목방송 세션 리포트: `python -m webtest.report http://127.0.0.1:8000 <pw>`
- 비용: 댓글당 ≈$0.0008 (분류 1회 기준. P 경로는 +1~2회 = ≈2~3배)

## 실행

```bash
pip install -r requirements.txt          # .env: GEMINI_API_KEY, SITE_PASSWORD
python -m eval.o_part.smoke_offline      # LLM 없이 O+P 구조 검증
uvicorn webtest.app:app --port 8000      # 라이브 테스트 화면 (비번 기본 team-only)
python -m webtest.simulate               # 가상 시청자 채팅 (방송 시작 감지 후 65건)
python -m eval.o_part.run_eval           # O 평가 (무료 등급: 분당15·일500 한도)
```

## 미결 사항

- [x] 팀 리포 push 완료 — main + feat/* 4개 브랜치 업로드. 리포명은 2026-09-10
      `Fundit-Ai-copilot` 으로 변경 (구 주소는 GitHub 이 자동 리다이렉트)
- [ ] Vercel 배포 (vercel login 필요; webtest/README.md 절차 — KV 필수)
- [ ] 사용자 PC 영상 재생 끊김: 앱 문제 아님(직접 파일 재생도 끊김 확인),
      다른 기기/브라우저 하드웨어 가속으로 우회
