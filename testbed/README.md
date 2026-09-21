# 라이브 목방송 테스트 환경 (testbed)

목영상 + 실시간 채팅으로 코파일럿의 라이브 동작을 팀이 직접 검증하는 웹앱.
왼쪽 채팅창에 팀원들이 자유롭게 채팅을 치면, 코파일럿이 실시간으로
분류·응답하고 (IGNORE는 무응답), 전 과정이 로그로 남아 리포트가 나온다.

## 로컬 실행

```bash
pip install -r requirements.txt
# .env 에 GEMINI_API_KEY, SITE_PASSWORD 설정
uvicorn testbed.app:app --reload
# http://localhost:8000 접속 → 비밀번호 입장 → [영상 업로드] → [방송 시작]
```

로컬은 저장소가 프로세스 메모리라 서버 재시작 시 로그가 사라진다.
영상 업로드는 서버 디스크(`testbed/uploads/`)에 저장된다.

## Vercel 배포

1. GitHub에 push 후 Vercel에서 리포 import (또는 `npx vercel --prod`)
2. **환경변수** (Vercel 프로젝트 Settings → Environment Variables):
   - `GEMINI_API_KEY` — Gemini API 키 (**유료 등급 프로젝트 권장** — 무료 15회/분으론 팀 채팅 버스트를 못 받음)
   - `SITE_PASSWORD` — 팀 공유 입장 비밀번호
   - `VIDEO_URL` — (선택) 영상 주소를 미리 지정할 때. 화면의 [영상 URL]/[영상 업로드]로 나중에 설정해도 됨
3. **저장소** (필수): Vercel 대시보드 → Storage → **Upstash Redis(KV)** 생성 후 프로젝트에 연결
   → `KV_REST_API_URL`/`KV_REST_API_TOKEN` 이 자동 주입됨. 없으면 서버리스 인스턴스마다
   메모리가 따로 놀아서 채팅이 공유되지 않는다.
4. **영상 업로드용** (선택): Storage → **Blob** 생성 연결 → `BLOB_READ_WRITE_TOKEN` 자동 주입.
   없으면 [영상 URL] 버튼으로 유튜브 비공개 링크나 mp4 주소를 넣으면 된다.

## 테스트 진행 순서

1. 배포 주소 + 비밀번호를 팀에 공유, 각자 닉네임으로 입장
2. 진행자: [영상 업로드] 또는 [영상 URL] 로 목영상 설정
3. 진행자: [방송 시작] → 전원 영상이 같은 시점으로 재생 (라이브 시뮬레이션)
4. 방송 동안 자유롭게 채팅 (질문·잡담·개인문의 섞어서)
5. 종료 후: `python -m testbed.report https://<배포주소> <비밀번호>`
   → `docs/LIVE_TEST_REPORT.md` 생성 (판정 분포·지연·전체 내역 + 수기 검증 칸)

## 예정 (통합 후)

- 판매자 뷰: 자주 반복되는 질문·미답변 질문을 영상 옆 패널로 노출 (P파트 통합 뒤 진행)
