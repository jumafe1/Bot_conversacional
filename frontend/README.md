# Rappi Data Bot — Frontend

Next.js 15 + [`assistant-ui`](https://github.com/assistant-ui/assistant-ui) chat UI that talks to the FastAPI backend at `POST /api/v1/chat`.

## Prerequisites

- Node **≥ 18.18** (Next 15 recommends ≥ 20).
- The FastAPI backend running on `http://localhost:8000` (or set `NEXT_PUBLIC_API_URL`).

## Setup

```bash
cd frontend
cp .env.local.example .env.local  # adjust NEXT_PUBLIC_API_URL if the backend isn't on :8000
npm install
npm run dev                       # http://localhost:3000
```

Start the backend in a separate terminal:

```bash
# from project root
make run                          # uvicorn on :8000
```

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Next dev server with hot reload |
| `npm run build` | Production build |
| `npm run start` | Run the prod build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | Next's built-in lint |

## Layout

```
frontend/
├── app/
│   ├── layout.tsx           # <html> + <body>, global styles
│   ├── page.tsx             # composes Header + ChatThread + SuggestionsStrip
│   └── globals.css          # Tailwind base + assistant-ui markdown tweaks
├── components/
│   ├── ConversationRuntime.tsx   # assistant-ui adapter → POST /api/v1/chat
│   ├── Thread.tsx                # primitive-based chat thread + composer
│   ├── Header.tsx                # title + live/thinking indicator + reset
│   ├── SuggestionsStrip.tsx      # follow-up pills from response.suggestions
│   ├── ToolsUsedBadge.tsx        # shows which backend tools ran this turn
│   └── ErrorBanner.tsx           # surfaces backend errors visibly
├── lib/
│   ├── api.ts                # typed `postChat` client + ChatApiError
│   ├── cn.ts                 # Tailwind classnames helper (clsx + twMerge)
│   └── session.ts            # stable session_id in localStorage
└── tailwind.config.ts        # brand/ink color tokens + prose plugin
```

## How it talks to the backend

`components/ConversationRuntime.tsx` implements a custom `ChatModelAdapter` for
assistant-ui. On every user turn:

1. Extract the latest user text from the assistant-ui message list.
2. POST it to `${NEXT_PUBLIC_API_URL}/api/v1/chat` together with the stable
   `session_id` from `localStorage`.
3. Return `response.answer` to assistant-ui so it renders the bubble.
4. Publish `response.suggestions` and `response.tool_calls_used` on a React
   context so `<SuggestionsStrip />` and `<ToolsUsedBadge />` can render them
   outside the message bubble without threading props through the runtime.

Errors become an `ErrorBanner` + an in-bubble fallback message so the user
always gets feedback.

## Customising

- **Change the accent color** — edit `brand` in `tailwind.config.ts`.
- **Add streaming** — swap the `postChat` fetch for SSE and switch the
  adapter to yield an async iterable of `{ content }` chunks. The backend
  does not stream today.
- **Show tool call details inline** — the backend's tool result lives in
  memory only during one turn; to display it in the UI you'd need to also
  return the tool metadata from `/api/v1/chat` (trivial: extend
  `ChatResponse` with a `tool_turns: list[...]` field).
