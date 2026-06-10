# Zeropark 프론트엔드 통합 키트 (Phase 3)

기존 Vite + React + TS 프론트에 게이트웨이를 붙이기 위한 포터블 클라이언트와 가이드.
백엔드 변경 없이 그대로 사용 가능. (백엔드는 이미 동기 실행 + SSE 스트리밍을 제공.)

## 1. 설치

1. `zeropark-client.ts`를 프론트의 `src/lib/zeropark.ts`로 복사.
2. `.env`에 게이트웨이 주소 지정:
   ```
   VITE_ZEROPARK_API=http://localhost:8080
   ```
3. 게이트웨이의 CORS 허용 도메인에 프론트 주소 추가(배포 시):
   ```
   ZEROPARK_CORS_ORIGINS=http://localhost:5173,https://your-app.com
   ```

## 2. 게이트웨이 엔드포인트

| Method | Path | 인증 | 용도 |
|---|---|---|---|
| GET | `/health` `/providers` `/modes` `/catalog` | X | 등록 엔진·모드 조회 |
| POST | `/api/v1/auth/login` | X | username/password → JWT |
| POST | `/api/v1/auth/guest/login?role=admin` | X | 개발용 JWT(비번 없이) |
| GET | `/api/v1/auth/google/login` | X | Google OAuth 시작 |
| POST | `/api/v1/tasks` | JWT | 동기 실행 → TaskResult |
| POST | `/api/v1/tasks/stream` | JWT | SSE 스트리밍(실시간 타임라인) |
| POST | `/api/v1/rag/upload` `/api/v1/rag/query` | JWT | RAG |
| GET/PATCH | `/api/v1/admin/*` | JWT(admin) | 사용자·통계 |

## 3. SSE 이벤트 형태 (`/api/v1/tasks/stream`)

각 `data:` 줄은 RunEvent JSON. 순서:

```
{"type":"status","task_id":"...","message":"started","data":{"capability":"slides"}}
{"type":"artifact","task_id":"...","data":{"artifact":{"kind":"deck","uri":"..."}}}
{"type":"done","task_id":"...","data":{"status":"succeeded","result":{ ...TaskResult... }}}
```

엔진이 자체 스트리밍을 지원하면 중간에 `log`/`token`/`source` 이벤트가 더 들어옴(같은 규약).

## 4. React 예시 — 실시간 실행 훅

```tsx
// src/hooks/useTaskStream.ts
import { useState, useCallback } from "react";
import { streamTask, type RunEvent, type TaskResult } from "../lib/zeropark";

export function useTaskStream(token?: string) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [result, setResult] = useState<TaskResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (mode: string, prompt: string, params?: Record<string, unknown>) => {
      setEvents([]); setResult(null); setError(null); setRunning(true);
      try {
        const final = await streamTask(
          { mode, prompt, params, token },
          (e) => setEvents((prev) => [...prev, e]),
        );
        setResult(final);
      } catch (e: any) {
        setError(e.message ?? "failed");
      } finally {
        setRunning(false);
      }
    },
    [token],
  );

  return { run, events, result, running, error };
}
```

```tsx
// 사용 예 (프롬프트 → 모드 → 실행 → 타임라인 + 아티팩트)
function Runner({ token }: { token: string }) {
  const { run, events, result, running } = useTaskStream(token);
  return (
    <div>
      <button disabled={running} onClick={() => run("slides", "회사 소개 덱", { n_slides: 6 })}>
        {running ? "실행 중…" : "슬라이드 생성"}
      </button>
      <ul>{events.map((e, i) => <li key={i}>{e.type} — {e.message ?? ""}</li>)}</ul>
      {result?.artifacts.map((a) => (
        <a key={a.id} href={a.uri ?? "#"}>{a.kind}: {a.title}</a>
      ))}
    </div>
  );
}
```

## 5. 개발 시작(빠른 경로)

```ts
import { guestLogin, getModes, streamTask } from "./lib/zeropark";

const { access_token } = await guestLogin("admin");   // 개발용 토큰
const modes = await getModes();                        // 모드 목록 → 모드 피커
// 프롬프트 박스 제출 시 streamTask(...)로 실행 타임라인 렌더
```

## 6. 다음 (실제 UI 확장)

네 프론트 구조(`src/` 트리, 기존 API 호출 파일)를 알려주면, 위 클라이언트를 네 컴포넌트에
직접 연결(프롬프트 박스·모드 피커·실행 타임라인·아티팩트 패널·로그인)하는 작업을 이어서 할게.
