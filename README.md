# Rappi Conversational Data Bot

A natural-language interface that lets non-technical teams (Strategy, Planning & Analytics, Operations) query operational metrics across 9 LATAM countries without writing SQL.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend (Next.js)                      │
│                         assistant-ui chat                        │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP POST /api/v1/chat
┌─────────────────────────────▼───────────────────────────────────┐
│                     FastAPI Backend                              │
│  ┌────────────┐   ┌─────────────┐   ┌──────────────────────┐   │
│  │ api/v1     │──▶│ bot_service │──▶│    llm_service       │   │
│  │ chat.py    │   │ orchestrate │   │ (OpenAI / Anthropic) │   │
│  └────────────┘   └──────┬──────┘   └──────────────────────┘   │
│                          │ tool calls (function calling)        │
│              ┌───────────▼───────────┐                          │
│              │     tools/registry    │                          │
│              │  filter · compare     │                          │
│              │  trend · aggregate    │                          │
│              └───────────┬───────────┘                          │
│                          │ SQL via DuckDB                       │
│              ┌───────────▼───────────┐                          │
│              │  metrics_repository   │                          │
│              └───────────┬───────────┘                          │
│                          │                                      │
│              ┌───────────▼───────────┐                          │
│              │  DuckDB (in-process)  │                          │
│              │  *.parquet in data/   │                          │
│              └───────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| LLM | OpenAI GPT-5.4 mini (tool use) | Native function calling, structured outputs |
| Orchestration | Direct API (no LangChain) | Full control, easier debugging, fewer abstractions |
| Database | DuckDB + Parquet | Zero-infra, columnar, fast aggregations on ~millions of rows |
| Backend | FastAPI | Async-native, Pydantic integration, OpenAPI docs for free |
| Config | Pydantic Settings | Type-safe env parsing, zero boilerplate |
| Logging | structlog | Structured JSON logs, easy to ship to any sink |

---

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd Bot_conversacional

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
make install

# 4. Configure environment
cp .env.example .env
# Edit .env and set at minimum OPENAI_API_KEY

# 5. Place the raw data file
cp /path/to/Bot_datos.xlsx data/raw/

# 6. Run data cleaning pipeline (generates parquet files)
make clean-data

# 7. Start the API server
make run
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)

# 8. (Optional) Start the chat UI
cd frontend
cp .env.local.example .env.local
make frontend-install              # one-off: npm install
make frontend-dev                  # → http://localhost:3000
```

---

## Project Structure

```
Bot_conversacional/
├── backend/
│   ├── api/v1/          # HTTP endpoints (chat, health)
│   ├── core/            # Config, logging, exceptions
│   ├── prompts/         # System prompt + metric dictionary
│   ├── repositories/    # DuckDB data access layer
│   ├── schemas/         # Pydantic request/response models
│   ├── services/        # Business logic (bot, llm, memory)
│   └── tools/           # LLM-callable tools (filter, compare, trend...)
├── frontend/            # Next.js 15 + assistant-ui chat UI
│   ├── app/             #   App Router pages (layout, home)
│   ├── components/      #   ConversationRuntime, Thread, Suggestions, Header
│   └── lib/             #   api client, session id, class helper
├── scripts/             # Data ingestion, EDA, live LLM smoke test
├── tests/               # pytest test suite
└── docs/                # Architecture, data quality, cost estimates
```

---

## Running Tests

```bash
make test         # full suite
pytest -k "chat"  # filter by name
pytest -v         # verbose output
```

---

## Key Technical Decisions


---

## Known Limitations & Next Steps

- Memory is in-process (dict-based). For multi-session persistence, replace `memory_service.py` with Redis or a DB-backed store.
- Tool results are returned as plain DataFrames serialized to JSON. A formatting layer (markdown tables, charts) would improve UX.
- No authentication on the API. Add JWT or API key middleware before any production exposure.
- The Automatic Insights system (30% of the original brief) is not implemented.
