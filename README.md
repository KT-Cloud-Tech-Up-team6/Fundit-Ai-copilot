# Fundit AI Copilot

라이브 커머스/펀딩 방송의 **채팅 상담 코파일럿**.
판매자가 일일이 답변할 수 없는 라이브 채팅 질문에 AI가 근거 기반으로 대신 답변하고,
답하지 못한 질문은 **고객 관심사로 정리해 판매자에게 실시간 제공**한다.

- 시청자: 질문 후 평균 1초 내 자동 답변
- 판매자: AI가 못 답한 질문만 관심 유형·반복 횟수로 정리된 알림 수신 → 방송 중 육성 답변
- 원칙: **근거 없는 답변 생성 0건** — 답변 본문은 LLM이 생성하지 않고 검증된 KB만 사용

## 담당 구성

| 영역 | 담당 | 내용 |
|---|---|---|
| P파트 (상품) | 심현서 | 상품 KB RAG — 검색 + Grounding 3단 판정, **상담사 문체 RAG(K쇼핑)**, 미답변 관심사 분석·집계, A2A Product Agent, MCP Live Knowledge |
| O파트 (플랫폼·펀딩) | 박금별 | FAQ 38건 + 동적 슬롯 치환 (LLM 답변 생성 금지), A2A Platform Agent |
| 공용 구조·통합 | 공동 | 오케스트레이터(라우터), 파트 계약, **동적 상품 KB(prepare)**, BE API, 라이브 테스트 환경, 평가 하네스 |

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
[LIVE 전]  판매자 상품정보 → POST /prepare → 활성 상품 KB 교체 (동적 — 재학습 불필요)

[LIVE 중]  채팅 → 라우터(Gemini 분류 전용)
   ├─ 잡담·개인문의 → 드롭
   ├─ 플랫폼 질문 → O파트: FAQ 원문 + 실시간 값 치환
   └─ 상품 질문   → P파트: KB 검색(규칙+일반 폴백) → Grounding 판정
        │            + Counselor Style RAG (상담사 말투 — 사실은 KB 에서만)
        ├─ 근거 있음 → 상담사 문체 답변 (부분 근거는 확인분만)
        └─ 근거 없음 → 관심사 분석·집계 → 판매자 Copilot 화면
```

- 모델: **Gemini 3.5 Flash-Lite** 단일 (temperature 0, 구조화 출력)
- **A2A**: Product Agent(현서, :9999)·Platform Agent(:9998) — Agent Card + JSON-RPC,
  실행 `python -m parts.p_part.agents.product_agent_server` / `parts.o_part.agents.platform_agent_server`
- **MCP**: `parts/p_part/mcp_servers/product_knowledge_server.py` — Live Knowledge (판매자 확인 정보 축적)
- 상세: `docs/ai_architecture.png`, `docs/EVAL_REPORT.md`, `api/API_GUIDE.md`

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

## 브랜치 전략 — 영역 소유권

| 브랜치 | 소유자 | 작업 범위 |
|---|---|---|
| `main` | 공동 (머지만) | 통합 결과 — 직접 커밋 금지, 파트 브랜치에서 머지 |
| `feat/p-part` | **심현서 전용** | `parts/p_part/` + `eval/p_part/` (상품 RAG·문체·관심사·A2A·MCP) |
| `feat/o-part` | **박금별 전용** | `parts/o_part/` + `eval/o_part/` + 공용(api·webtest·docs) |
| `feat/webtest` | 박금별 | 라이브 테스트 환경 |
| `feat/kshopping-style` | **심현서** | K쇼핑 상담사 학습 데이터 — `parts/p_part/data/kshopping_style/` + 구축 파이프라인(`scripts/`) + 문체 검색기. 코퍼스는 전 상품 공통 고정 |
| `feat/a2a-agent` | 참고용 | 현서 a2a 원본 사본 (읽기용) |

**규칙**
- 모든 브랜치는 현재 **최신 main 과 동일 시점**으로 맞춰져 있음 — 각자 자기 브랜치에서 `git pull` 후 시작
- **자기 영역 폴더만 수정** — 타 영역·`shared/`·`orchestrator/` 변경은 상대방 확인 후
  (`.github/CODEOWNERS` 로 PR 리뷰어 자동 지정됨)
- 작업 흐름: 자기 브랜치에서 커밋 → main 으로 머지 (충돌 최소화: 폴더가 겹치지 않음)
- 파트 등록은 `CopilotService(parts=[OPart(), PPart()])` 한 줄

## 문서

| 문서 | 내용 |
|---|---|
| `docs/EVAL_REPORT.md` | O파트 164건 평가 리포트 (튜닝 이력 6회차) |
| `docs/LIVE_TEST_REPORT.md` | 라이브 목방송 세션 검증 리포트 |
| `docs/ai_architecture.png` | AI 아키텍처 다이어그램 |
| `parts/p_part/README.md` | P파트 상세 (RAG·관심사 분석 설계) |
| `webtest/README.md` | 라이브 테스트 환경 사용법·배포 |
