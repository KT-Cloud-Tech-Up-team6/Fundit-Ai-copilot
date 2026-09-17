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
- 상세: `docs/ai_architecture.png`, `docs/EVAL_REPORT.md`, `api/API_GUIDE.md`

## 상품 정보 흐름 — 목데이터가 아닌 실제 입력으로 동작

| 시점 | 경로 | 효과 |
|---|---|---|
| 방송 전 | `POST /api/v1/funding-ai/lives/{id}/prepare` — 판매자가 등록한 실제 상품정보 전달 | **활성 상품 KB 즉시 교체** — 그 상품 기준으로 답변 (재학습·재기동 불필요) |
| 방송 중 | 답변 가능한 질문 | 상품 KB 근거 + 상담사 문체로 실시간 답변 |
| 방송 중 | 답변 못 한 질문 | 관심사 집계 → 판매자 확인 → **MCP Live Knowledge 등록 시 즉시 답변에 반영** (`add_live_product_fact`) |

- 검색: 기존 규칙표(기본 상품 특화)는 무변경, 규칙 미매칭 시에만 일반 단어 매칭 폴백 발동
- 한계: 활성 KB 프로세스 전역 1개 (동시 멀티 라이브는 다음 단계)

## A2A Agent 2종

| | Product Agent (심현서) | Platform Agent (박금별) |
|---|---|---|
| 포트 | :9999 | :9998 |
| Agent Card | `/.well-known/agent-card.json` | `/.well-known/agent-card.json` |
| JSON-RPC | `/a2a/product` | `/a2a/platform` |
| Skill | `product_question_answering` | `platform_question_answering` |
| 입력 | text 질문 (상품 질문 가정) | text 질문 (잡담은 자체 IGNORE) |
| 출력 | grounding_status·answer·source_chunk_ids·unresolved_topics | decision·answer·faq_id·category·strict |
| 실행 | `python -m parts.p_part.agents.product_agent_server` | `python -m parts.o_part.agents.platform_agent_server` |

- 리포 내부에서는 라우터가 두 파트를 in-process 로 연결 (A2A 서버는 외부 오케스트레이션용)
- MCP 서버: `parts/p_part/mcp_servers/product_knowledge_server.py` (공식 KB + Live Knowledge)

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

**작업 흐름 — 평소에는 main 하나로 (매번 병합하지 않는다)**

```
평소 (자기 영역 폴더만 수정할 때) — 브랜치·병합 불필요
  git checkout main
  git pull
  ... parts/p_part/ (현서) 또는 parts/o_part/·api/·webtest/ (금별) 안에서 작업 ...
  git commit && git push
  → 영역 폴더가 서로 안 겹쳐서 충돌이 나지 않는다

큰 변경·실험·공용 영역(shared/·orchestrator/) 건드릴 때만
  main 에서 feat/* 브랜치 분기 → PR → CODEOWNERS 리뷰 → main 머지
```

- **main = 항상 최신 통합본.** 시작 전 `git pull` 만 지키면 된다
- feat/p-part 등 파트 브랜치는 위 "큰 변경" 용도의 상시 브랜치 (현재 전부 main 과 동일 시점)
- 타 영역 폴더는 수정하지 않는다 — 필요하면 상대에게 요청 (`.github/CODEOWNERS` 가 PR 에서 강제)
- 파트 등록은 `CopilotService(parts=[OPart(), PPart()])` 한 줄

## 문서

| 문서 | 내용 |
|---|---|
| `docs/EVAL_REPORT.md` | O파트 164건 평가 리포트 (튜닝 이력 6회차) |
| `docs/LIVE_TEST_REPORT.md` | 라이브 목방송 세션 검증 리포트 |
| `docs/ai_architecture.png` | AI 아키텍처 다이어그램 |
| `parts/p_part/README.md` | P파트 상세 (RAG·관심사 분석 설계) |
| `webtest/README.md` | 라이브 테스트 환경 사용법·배포 |
