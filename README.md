# Live Commerce Copilot

라이브 커머스/펀딩 방송의 **채팅 상담 코파일럿**.
판매자가 일일이 답변할 수 없는 라이브 채팅 질문에 AI가 근거 기반으로 대신 답변하고,
답하지 못한 질문은 **고객 관심사로 정리해 판매자에게 실시간 제공**한다.

- 시청자: 질문 후 평균 1초 내 자동 답변
- 판매자: AI가 못 답한 질문만 관심 유형·반복 횟수로 정리된 알림 수신 → 방송 중 육성 답변
- 원칙: **근거 없는 답변 생성 0건** — 답변 본문은 LLM이 생성하지 않고 검증된 KB만 사용

## 담당 구성

| 영역 | 담당 | 내용 |
|---|---|---|
| P파트 (상품) | 심현서 | 상품 KB RAG — 검색 + Grounding 3단 판정, 미답변 관심사 분석·집계 |
| O파트 (플랫폼·펀딩) | 박금별 | FAQ 38건 + 동적 슬롯 치환 (LLM 답변 생성 금지) |
| 공용 구조·통합 | 공동 | 오케스트레이터(라우터), 파트 계약, 라이브 테스트 환경, 평가 하네스 |

## 폴더 구조

```
shared/          파트 간 계약 (schemas + CopilotPart) — 변경 시 팀 합의
orchestrator/    라우터(LLM 분류 전용) · 서비스 · 공용 LLM 클라이언트
parts/
├── o_part/      플랫폼·펀딩 FAQ 응대 + data/ (FAQ·슬롯)
└── p_part/      상품 RAG (retriever/answer/analyzer/tracker) + data/ (상품 KB)
api/             FastAPI PoC API
eval/
├── o_part/      O 평가 (164건 세트 + 자동 채점)
├── p_part/      P 평가 (50건 RAG + 100건 리플레이 + CLI 테스트)
└── results/     평가 결과 누적 (gitignore)
webtest/         라이브 목방송 테스트 환경 (영상+채팅+판매자 알림+시뮬레이터+리포트)
docs/            설계 문서 · 평가 리포트 · 아키텍처 다이어그램
```

## 아키텍처 (요약)

```
[LIVE 전]  판매자 상품정보 → KB 구축 (정제·strict 태깅·검수) → O/P KB

[LIVE 중]  채팅 → 라우터(Gemini 분류 전용)
   ├─ 잡담·개인문의 → 드롭
   ├─ 플랫폼 질문 → O파트: FAQ 원문 + 실시간 값 치환
   └─ 상품 질문   → P파트: KB 검색 → Grounding 판정
        ├─ 근거 있음 → 답변 (부분 근거는 확인분만)
        └─ 근거 없음 → 관심사 분석·집계 → 판매자 Copilot 화면
```

- 모델: **Gemini 3.5 Flash-Lite** 단일 (temperature 0, 구조화 출력)
- 상세: `docs/ai_architecture.png`, `docs/EVAL_REPORT.md`

## 검증 결과 (2026-09-04)

| 지표 | 목표 | 실측 |
|---|---|---|
| 할루시네이션 | 0건 | **0건** |
| 답변불가 탐지율 | ≥95% | 96.4% |
| 라벨 Macro-F1 / FAQ top-1 | ≥90% | 99.5% / 98.7% |
| P Grounding 정확도 | — | 96.0% (50건) / 85% (100건) |
| 평균 응답 지연 | <1.5초 | 0.98초 |
| 비용 | — | 채팅 1건 1.4~4.7원, 방송 1건(1천 채팅) 약 2,100원 |

## 실행 방법

```bash
pip install -r requirements.txt
copy .env.example .env            # GEMINI_API_KEY 입력

python -m eval.o_part.smoke_offline   # LLM 없이 구조 검증 (O+P)
uvicorn webtest.app:app --port 8000   # 라이브 목방송 테스트 화면
python -m webtest.simulate            # 가상 시청자 채팅 시뮬레이터
python -m eval.o_part.run_eval        # O 평가 (164건 자동 채점)
python -m eval.p_part.evaluate_rag    # P RAG 평가 (50건)
python -m eval.p_part.mvp_replay_test # P 리플레이 (100건)
```

라이브 테스트: 접속 → 비밀번호 입장 → [영상 업로드/URL] → [방송 시작] →
채팅이 실시간 분류·응답되고, 종료 후 `python -m webtest.report <url> <pw>` 로 검증 리포트 생성.

## 브랜치 전략

| 브랜치 | 용도 |
|---|---|
| `main` | 통합 브랜치 — 파트 브랜치 머지 + 통합 글루(어댑터·라우터 위임) |
| `feat/p-part` | P파트 작업 (심현서) |
| `feat/o-part` | O파트 + 공용 구조 작업 (박금별) |
| `feat/webtest` | 라이브 테스트 환경 |

- 파트 추가/수정은 자기 브랜치의 `parts/<파트>/` 안에서 → main으로 머지
- `shared/` 변경은 팀 합의 후에만
- 파트 등록은 `CopilotService(parts=[OPart(), PPart()])` 한 줄

## 문서

| 문서 | 내용 |
|---|---|
| `docs/EVAL_REPORT.md` | O파트 164건 평가 리포트 (튜닝 이력 6회차) |
| `docs/LIVE_TEST_REPORT.md` | 라이브 목방송 세션 검증 리포트 |
| `docs/ai_architecture.png` | AI 아키텍처 다이어그램 |
| `parts/p_part/README.md` | P파트 상세 (RAG·관심사 분석 설계) |
| `webtest/README.md` | 라이브 테스트 환경 사용법·배포 |
