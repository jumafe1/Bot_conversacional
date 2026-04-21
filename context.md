# Rappi Bot — Context Handoff

> **Este documento existe para que un próximo agente/desarrollador pueda retomar el proyecto sin leer la conversación previa.** Documenta qué se construyó, por qué, qué está pendiente, y cuál es el siguiente incremento planificado.

**Última actualización**: 2026-04-21
**Estado**: Backend + Frontend funcionales. Tests 163/163 passing. Listos para arrancar el módulo **Insights**.

---

## TL;DR en 30 segundos

- **Bot conversacional** que deja a Strategy / Planning & Analytics / Operations consultar métricas operativas de Rappi en 9 países LATAM en lenguaje natural, sin escribir SQL.
- Stack: **FastAPI + DuckDB + Parquet** (backend), **Next.js 15 + assistant-ui + Tailwind** (frontend), **OpenAI gpt-5.4-mini** con function calling (LLM).
- Datos: 11.610 filas de métricas × 13 métricas × 9 países × 9 semanas relativas (L0W..L8W). Órdenes: 1.242 zonas.
- **Lo que ya anda**: 6 tools (filter, compare, trend, aggregate, multivariate, orders_growth) + memoria + sistema de caveats estadísticos + UI de chat funcional.
- **Lo que sigue**: módulo de **Automatic Insights** — una segunda ruta en el frontend que genera un reporte ejecutivo automáticamente con regresiones + gráficos matplotlib + narración LLM.

---

## Tabla de contenidos

- [Arquitectura actual](#arquitectura-actual)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Incrementos ya entregados](#incrementos-ya-entregados)
- [Convenciones de código del proyecto](#convenciones-de-código-del-proyecto)
- [Stack, versiones y gotchas críticos](#stack-versiones-y-gotchas-críticos)
- [Cómo correr todo](#cómo-correr-todo)
- [Próximo incremento: módulo Insights](#próximo-incremento-módulo-insights)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Estilo de interacción del usuario](#estilo-de-interacción-del-usuario)

---

## Arquitectura actual

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 15 + assistant-ui)          │
│                    http://localhost:3000                         │
└─────────────────────────────┬───────────────────────────────────┘
                              │ POST /api/v1/chat
┌─────────────────────────────▼───────────────────────────────────┐
│  FastAPI backend — http://localhost:8000                         │
│                                                                  │
│  api/v1/chat.py                                                  │
│      ↓ Depends(get_bot_service)                                  │
│  services/bot_service.py                                         │
│      ↓ tool-use loop (max 5 iterations)                          │
│      ├─── services/llm_service.py ── OpenAI/Anthropic            │
│      ├─── services/memory_service.py ── in-process dict          │
│      └─── tools/registry.py ── dispatch(name, args)              │
│                ↓                                                 │
│         tools/*.py ── 6 handlers                                 │
│                ↓                                                 │
│         repositories/metrics_repository.py                       │
│                ↓                                                 │
│         DuckDB in-memory (views sobre parquets)                  │
└──────────────────────────────────────────────────────────────────┘
```

**Flujo de un turno**:
1. Usuario envía mensaje al frontend.
2. Frontend hace `POST /api/v1/chat` con `{session_id, message}`.
3. `BotService.process_message` arma `[system_prompt, ...history, user_message]`.
4. Loop LLM ↔ tools: máx 5 iteraciones, cada tool_call se despacha a un handler que ejecuta SQL contra DuckDB.
5. Cuando el LLM devuelve texto final, se parsean las sugerencias del bloque `**Análisis sugerido:**`.
6. Memoria guarda sólo `user` + `assistant` final (nunca tool_calls / tool_results).
7. Frontend renderiza markdown + badge con tools consultadas + pills de sugerencias clickeables.

---

## Estructura del proyecto

```
Bot_conversacional/
├── backend/
│   ├── api/v1/
│   │   ├── chat.py              # POST /api/v1/chat (Depends-based DI)
│   │   └── health.py            # GET /api/v1/health
│   ├── core/
│   │   ├── config.py            # Settings pydantic (lee .env)
│   │   ├── exceptions.py        # RappiBotError base, +3 subclases
│   │   └── logging.py           # configure_logging()
│   ├── prompts/
│   │   ├── metric_dictionary.py # 13 métricas canónicas + scale_note
│   │   └── system_prompt.py     # build_system_prompt() dinámico
│   ├── repositories/
│   │   ├── database.py          # db singleton, registra parquets como views
│   │   └── metrics_repository.py # 7 funciones de consulta con validación
│   ├── schemas/
│   │   └── chat.py              # ChatRequest, ChatResponse pydantic
│   ├── services/
│   │   ├── bot_service.py       # orquestador del tool-use loop
│   │   ├── llm_service.py       # wrapper async OpenAI + Anthropic
│   │   └── memory_service.py    # in-process dict con sliding window 20
│   ├── tools/
│   │   ├── _caveats.py          # 5 detectores estadísticos (Nivel 2)
│   │   ├── _utils.py            # format_response/error_response/empty_response
│   │   ├── registry.py          # TOOLS_REGISTRY + dispatch() + get_openai_tools_schema()
│   │   ├── filter_zones.py
│   │   ├── compare_metrics.py
│   │   ├── get_trend.py
│   │   ├── aggregate.py
│   │   ├── multivariate.py
│   │   └── orders_growth.py
│   └── main.py                  # FastAPI app, startup/shutdown events
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx             # Home (actualmente el chat; MUDAR a /chat cuando arranque el landing)
│   │   └── globals.css
│   ├── components/
│   │   ├── ConversationRuntime.tsx  # adapter a assistant-ui + context de metadata
│   │   ├── Thread.tsx                # primitivas de chat (no usa el <Thread> default)
│   │   ├── Header.tsx                # título + status dot + reset button
│   │   ├── SuggestionsStrip.tsx      # pills clickeables con follow-ups
│   │   ├── ToolsUsedBadge.tsx        # badge con tools consultadas
│   │   └── ErrorBanner.tsx           # errores del backend visibles
│   ├── lib/
│   │   ├── api.ts               # postChat tipado + ChatApiError
│   │   ├── cn.ts                # clsx + twMerge
│   │   └── session.ts           # session_id persistente en localStorage
│   ├── package.json
│   ├── tailwind.config.ts       # brand + ink palettes, typography plugin
│   ├── tsconfig.json
│   └── next.config.mjs
├── data/
│   ├── raw/                     # Bot_datos.xlsx (gitignored)
│   └── processed/               # parquets (gitignored)
│       ├── metrics_wide.parquet
│       ├── metrics_long.parquet
│       ├── orders_wide.parquet
│       └── orders_long.parquet
├── scripts/
│   ├── clean_data.py            # Excel → parquet pipeline
│   ├── explore_data.py          # EDA profiler
│   └── smoke_test_bot.py        # live test contra el LLM real
├── tests/
│   ├── test_api/test_chat.py
│   ├── test_prompts/test_system_prompt.py
│   ├── test_repositories/test_metrics_repository.py
│   ├── test_services/
│   │   ├── test_llm_service.py
│   │   ├── test_bot_service.py
│   │   └── test_memory_service.py
│   └── test_tools/
│       ├── test_caveats.py
│       └── test_handlers.py
├── .env.example
├── Makefile                     # targets: install, run, test, smoke-bot, frontend-dev, frontend-build
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── README.md
└── context.md                   # ESTE archivo
```

---

## Incrementos ya entregados

### Incremento 0 — Tools + Registry (pre-existente)

- `metrics_repository.py` con 7 funciones de alto nivel (validadas).
- 6 handlers en `tools/` que son thin wrappers del repositorio.
- `tools/registry.py` con TOOLS_REGISTRY + dispatch síncrono + schemas OpenAI.
- **Contrato uniforme de respuesta**: cada tool devuelve `{summary: str, data: list[dict], metadata: dict}`. Errores de validación convertidos a `{..., metadata: {error: True, reason: ...}}` en lugar de excepciones — el LLM puede recuperarse.

### Incremento 1 — System Prompt

`backend/prompts/system_prompt.py` construido dinámicamente desde las fuentes de verdad (`METRIC_DICTIONARY`, `VALID_COUNTRIES`, `VALID_WEEK_COLS`, etc.). Incluye:

1. Identidad ("Rappi's internal Data Analyst Assistant").
2. **Scope strict** — rechaza fitness/coding/predicciones/role-play con plantillas de refusal bilingües.
3. Fecha de hoy + semantics de semanas (L0W..L8W).
4. Mercados (9), dimensiones de zona, inventario de 13 métricas con scale_note.
5. **Tool-use contract de 7 reglas**, incluyendo la #7 que fuerza surfacing de `metadata.caveats`.
6. Response format: bilingüe, tablas markdown, cierre obligatorio con sugerencias.

Tamaño: ~13k chars, ~3.3k tokens.

### Incremento 2 — LLMService

`backend/services/llm_service.py` es wrapper async sobre OpenAI y Anthropic. Detalles importantes:

- **Formato canónico interno** = OpenAI (messages con `role`, `content`, `tool_calls`, `tool_call_id`).
- Path Anthropic convierte en el borde: extrae `system` como kwarg separado, transforma tool_calls a bloques `tool_use`, tool results a bloques `tool_result` dentro de un user turn.
- Schemas se traducen con `_openai_tool_to_anthropic`.
- **Malformed JSON** en arguments → `LLMProviderError` (el bot_service lo dejaba propagar, pero `dispatch` igual maneja la ausencia de keys).
- **Inyección de cliente** (`LLMService(client=mock)`) para tests sin red.
- **Manejo del API de GPT-5.x**: usa `max_completion_tokens` en lugar de `max_tokens`, y **omite `temperature`** para modelos que empiezan con `gpt-5` / `o1` / `o3` / `o4` (esas familias solo aceptan la temperatura default).

### Incremento 3 — BotService + MemoryService + Endpoint

- `memory_service.py` — in-process dict, sliding window de 20 mensajes, aislamiento por `session_id`. Solo guarda roles `user` y `assistant`.
- `bot_service.py` — loop LLM↔tools con:
  - `MAX_TOOL_ITERATIONS = 5`
  - Si se agota el presupuesto, una llamada final **sin tools** fuerza texto.
  - Errores del dispatch se convierten en tool_results estructurados (no rompen el turno).
  - Parser de sugerencias: regex permisiva que acepta ES/EN, bullets `-/*/•/1.`, con o sin `**`. Cap 5.
- `api/v1/chat.py` — endpoint con `Depends(get_bot_service)` y `lru_cache(maxsize=1)` para instancia singleton. Errores `RappiBotError` mapeados a códigos HTTP específicos.

### Incremento 4 — Frontend Next.js + assistant-ui

- **Versión de assistant-ui**: `^0.12.25` (la `0.11.58` tenía un bug de `this` en `RemoteThreadListHookInstanceManager`; 0.12 refactorizó esa ruta).
- `ConversationRuntime.tsx` — `ChatModelAdapter` custom que llama el backend via `postChat`. Publica `suggestions` / `toolsUsed` / `sessionId` en un context para sibling components.
- `Thread.tsx` — usa primitivas (`ThreadPrimitive`, `MessagePrimitive`, `ComposerPrimitive`, `MarkdownTextPrimitive`), no el componente `<Thread>` empaquetado, porque el default no casa con el styling del resto.
- Landing page actualmente muestra el chat en `/`.
- **SSR safety**: `sessionId` arranca como `null` (no se lee localStorage durante render), se popula en `useEffect` post-mount. Evita hydration mismatch.
- `tailwind.config.ts` importa `typography` con `import` estándar (NO `require` — Node 25 ESM estricto rompe si se mezcla).

### Incremento 5 — Sistema de caveats estadísticos (Nivel 2)

**Filosofía**: los LLMs no razonan, patrón-matchean. En lugar de enseñarle al bot "a pensar como analista", detectamos mecánicamente los problemas estadísticos en Python y los metemos en `metadata.caveats`. El system prompt tiene una regla que fuerza al LLM a surfacarlos antes de dar conclusiones.

**5 detectores** en `backend/tools/_caveats.py`:

| Detector | Dispara cuando | Handler que lo usa |
|---|---|---|
| `low_denominator` | Base < 20 en ratios porcentuales | `orders_growth` |
| `small_sample` | n < 5 en aggregate global | `aggregate` (sin group_by) |
| `small_sample_in_group` | Grupo con n < 10 | `aggregate` (con group_by), `compare_metrics` |
| `high_variance` | CV ≥ 0.3 en serie temporal | `get_trend` |
| `narrow_result` | < 3 zonas en query multi-condición | `multivariate` |

**Caps**: máx 5 caveats por respuesta, máx 10 row indices enumerados por caveat.

**Contrato del caveat**:
```python
{
    "type": str,          # identificador estable
    "detail": str,        # una oración explicando al usuario
    "affected_rows": list[int] | None,  # indices en `data`, None si es global
}
```

El contrato en el prompt está en `_TOOL_USE_CONTRACT` regla 7 (`backend/prompts/system_prompt.py`).

---

## Convenciones de código del proyecto

### Python

- **Type hints modernas**: `list[str]`, `dict[str, Any]`, `str | None` (no `Optional`, no `typing.List`).
- **Docstrings explican el "por qué"**, no el "qué". Ej: no "Returns True when x is positive" sino "Guards against division-by-zero downstream when this sneaks in as a rate denominator".
- **Sin comentarios-ruido**: nunca `# Increment counter`, `# Return result`. Solo cuando el código no se explica solo (trade-offs, constraints externos, bugs conocidos de upstream).
- **Sin emojis en código ni prompts** (excepto si el usuario lo pide explícito). El prompt puede usarlos en plantillas de refusal pero nunca en lógica.
- **Errores estructurados, no excepciones**, en el borde con el LLM. El LLM necesita recibir algo legible para auto-corregirse.
- **Validación en el repository, no en los handlers**. Los handlers son thin.
- **Imports ordenados**: stdlib, third-party, local (ruff isort-style).

### TypeScript / React

- **"use client"** solo cuando es estrictamente necesario (hooks, state).
- **Context API** para compartir state entre componentes hermanos (no prop drilling).
- **Inyección de dependencias** vía props / context / FastAPI `Depends`, siempre testable.
- **Hydration-safe**: nada que lea `window` o `localStorage` dentro de `useState(() => ...)`.

### Tests

- **Por módulo**: `tests/test_<subdir>/test_<module>.py`.
- **Mocks en el borde** (SDK clients, endpoints HTTP), no en lógica de negocio.
- **Tests contra datos reales** cuando el costo es bajo (repository, handlers integration contra parquets reales).
- **Nunca testear wording exacto** del LLM ni de prompts — testear invariantes (keywords presentes, shapes correctos, propiedades cumplidas).

### Commits / changes

- El usuario prefiere **mensajes en español** pero el **código en inglés**.
- Prefiere incrementos chicos con tests + validación end-to-end antes de avanzar.
- Es muy sensible al over-engineering; los "parches" vs "soluciones generales" son una discusión recurrente. Siempre justificar cuándo aplicar cada uno.

---

## Stack, versiones y gotchas críticos

### Python 3.11.14 (via pyenv)

```
# Dependencias actuales (requirements.txt)
fastapi, uvicorn[standard]
pydantic, pydantic-settings, python-dotenv
openai (2.32.0), anthropic (0.96.0)
duckdb, pandas, pyarrow, openpyxl
structlog
```

### Node 25.8.2 / npm 11.11.1

```json
// frontend/package.json — versiones importantes
"@assistant-ui/react": "^0.12.25",        // NO usar 0.11.x, bug de `this`
"@assistant-ui/react-markdown": "^0.12.0",
"next": "^15.2.0",
"react": "^19.0.0",
"tailwindcss": "^3.4.17"
```

### Gotchas encontradas y resueltas

1. **`max_tokens` deprecated en GPT-5.x / o-series** → `llm_service` usa `max_completion_tokens`.
2. **Temperature solo acepta default en GPT-5.x** → `_openai_supports_custom_temperature(model)` filtra y omite el kwarg.
3. **assistant-ui 0.11.58 `this` bug** → upgrade a 0.12.25. La API pública de `useLocalRuntime` no cambió.
4. **Hydration mismatch por localStorage** → `sessionId: null` en server, populate post-mount.
5. **Node 25 ESM estricto + `require()` en `.ts`** → todo plugin de Tailwind se importa con `import`, nunca `require`.
6. **httpx ≥ 0.28 sacó `AsyncClient(app=...)`** → usar `ASGITransport(app=app)` en fixtures de test.
7. **Next 15 `.next/` cache corrupt tras hot-reload fallido** → `rm -rf .next` cuando aparecen errores tipo "Cannot find module './778.js'".

### Variables de entorno (`.env`)

```bash
OPENAI_API_KEY=
LLM_PROVIDER=openai               # | anthropic
LLM_MODEL=gpt-5.4-mini            # gpt-5.x / gpt-4o / etc.
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.1               # ignorado para GPT-5.x / o-series
DATA_DIR=data/processed
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:3000"]
```

Frontend:
```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Cómo correr todo

### Setup inicial

```bash
# Backend
python -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env
# → editar .env, agregar OPENAI_API_KEY real
make clean-data                # genera parquets desde data/raw/Bot_datos.xlsx

# Frontend
cd frontend
cp .env.local.example .env.local
npm install
cd ..
```

### Correr

```bash
# Terminal 1 — backend
make run                       # → http://localhost:8000
                               # → http://localhost:8000/docs

# Terminal 2 — frontend
make frontend-dev              # → http://localhost:3000
```

**Nota**: `make` solo funciona desde la raíz del proyecto. Si estás en un subdirectorio, usar `make -C /path/to/Bot_conversacional <target>`.

### Testing

```bash
make test                      # pytest full suite (actualmente 163 passed)
make smoke-bot                 # live test contra LLM real, gasta tokens
make smoke-bot CASES="1 3"    # solo casos 1 y 3

cd frontend
npm run typecheck              # tsc --noEmit
npm run build                  # Next production build
```

### Estado actual de tests

```
163 passed in 0.42s
  25 repository tests (contra parquets reales)
  32 handlers integration tests
  20 caveats unit tests
  15 system prompt invariants
  26 llm_service (mocked)
  17 bot_service (mocked LLM, real dispatch)
   8 memory_service
   6 api integration (mocked bot)
  14 otros
```

---

## Próximo incremento: módulo Insights

**Objetivo del brief** (del screenshot original):
1. **Identificación automática de insights** en 5 categorías:
   - Anomalías: zonas con cambios >10% WoW
   - Tendencias preocupantes: métricas deteriorándose 3+ semanas seguidas
   - Benchmarking: zonas similares (mismo país/tipo) con performance divergente
   - Correlaciones: relaciones entre métricas
   - Oportunidades: general
2. **Reporte ejecutivo estructurado**:
   - Resumen ejecutivo (top 3-5 hallazgos críticos)
   - Detalle por categoría
   - Recomendaciones accionables
3. **Formato**: Markdown (elegido sobre PDF/HTML por simplicidad).

### Decisiones del usuario sobre scope

- **Versión A**: corre sobre los parquets ya cargados, **sin upload**.
- **Regresiones cuando tengan sentido** (trends, correlaciones).
- **Gráficos con matplotlib** embebidos como base64 PNG.
- **El LLM NO hace matemática**. Recibe findings estructurados y solo los narra. Misma estrategia que con los caveats.

### Arquitectura del módulo

```
backend/insights/
├── __init__.py
├── analyzer.py     # análisis determinístico (scipy/sklearn/pandas)
├── charts.py       # matplotlib → base64 PNG
├── narrator.py     # 1 llamada LLM, findings → markdown
├── service.py      # orquesta todo
└── schemas.py      # pydantic InsightsReport, InsightsSection
```

**Endpoint**: `POST /api/v1/insights/generate` → `InsightsReport`.

**Response shape tentativa**:
```python
class InsightsSection(BaseModel):
    id: Literal["executive_summary", "anomalias", "tendencias",
                "benchmarking", "correlaciones", "oportunidades"]
    title: str
    narrative: str              # markdown del LLM
    findings: list[dict]        # datos crudos (top N por categoría)
    chart_png_base64: str | None  # imagen embebida
    recommendation: str         # acción concreta sugerida

class InsightsReport(BaseModel):
    generated_at: datetime
    data_snapshot: dict         # total_zones, n_countries, etc.
    sections: list[InsightsSection]
```

### Detectores del analyzer (deterministas)

Implementados en `analyzer.py` — cada uno devuelve `list[Finding]` con datos crudos.

| Categoría | Algoritmo | Threshold sugerido |
|---|---|---|
| **Anomalías** | Para cada `(zone, metric)`, `delta = (L0W_ROLL - L1W_ROLL) / L1W_ROLL`. Flag si `|delta| > 0.10`. Rankear top 10 por `|delta|`. | 10% WoW |
| **Tendencias** | `scipy.stats.linregress` sobre los 9 puntos semanales. Flag si `p_value < 0.05` AND `slope < 0` AND al menos 3 semanas seguidas de bajada. Top 10 por fuerza de decline (t-statistic). | p<0.05, slope<0 |
| **Benchmarking** | Para cada `(country, zone_type)` cell, computar mean/std por métrica. Flag zonas con z-score < -1.5 en al menos 1 métrica. Top 10 por peor z-score. | z < -1.5 |
| **Correlaciones** | Pearson sobre los 13 metrics × todas las zonas (L0W_ROLL). Top 5 pares con `|r| > 0.5`. Para el #1, regresión lineal + R² para el gráfico. | \|r\| > 0.5 |
| **Oportunidades** | Inverso de anomalías: zonas con delta > +10% Y valor absoluto saliendo del bottom quartile (no empezar desde ruido). Top 10. | +10% WoW, quartile ≥ 2 |

### Charts (matplotlib)

Cada sección tiene 1 gráfico, 800×450 px, `plt.tight_layout()`, embedded como base64 PNG:

1. **Anomalías**: scatter de todas las zonas en eje X=valor actual, Y=delta%. Highlight los top 10 outliers con labels.
2. **Tendencias**: line chart con los 3 series más declinantes (weeks eje X, value eje Y), annotated con slope.
3. **Benchmarking**: boxplot por país (métrica más afectada), outliers resaltados en rojo con nombre.
4. **Correlaciones**: heatmap 13×13 con `seaborn.heatmap` o `matplotlib.pcolormesh`. Diagonal y triángulo superior ocultos.
5. **Regresión lineal del correlation #1**: scatter + recta + R² en el título.

### Narrator (LLM)

**1 sola llamada** con todos los findings estructurados como input JSON. Prompt específico:

```
Eres un analista de datos de Rappi. Recibes findings YA COMPUTADOS
estadísticamente. Tu trabajo es ÚNICAMENTE redactar en español natural,
no calcular. Para cada sección:

1. Una narrativa de 2-4 oraciones explicando el hallazgo.
2. Una recomendación accionable específica (no genérica).

No inventes datos. No uses números que no estén en los findings.
Formato: JSON con {executive_summary, sections: [{id, narrative, recommendation}]}
```

Usa `response_format: json_object` de OpenAI para estructura garantizada.

### Cacheo

Los reportes son caros (matplotlib + LLM ≈ 30-60s). In-memory cache con TTL de 10 min:

```python
@lru_cache  # no — TTL manual
_cache: dict[str, tuple[InsightsReport, datetime]] = {}
# Key = "" (global) o f"country={country}" si se agrega filtro por país
```

### Frontend (paso 6)

**Routing**:
- `/` → landing nueva con dos cards.
- `/chat` → chat actual (mudar `app/page.tsx` a `app/chat/page.tsx`).
- `/insights` → página nueva.

**Landing** (`app/page.tsx` nuevo):
- Card 1: "Chatear con los datos" → link a `/chat`, icono `MessageSquare`.
- Card 2: "Generar reporte de insights" → link a `/insights`, icono `BarChart3`.

**Insights page**:
- Al montar: `POST /api/v1/insights/generate`.
- Loading state con pasos ("Analizando… Graficando… Narrando…").
- Error state con botón de retry.
- Success: render secciones en orden, cada una con título, narrativa markdown, imagen embebida, recomendación destacada.
- Header con botón "Descargar markdown" que concatena todas las secciones.

### Plan de ejecución acordado (6 pasos)

| # | Paso | Tiempo | Visible |
|---|---|---|---|
| 1 | Landing + split `/chat` + stub `/insights` | 30 min | Sí |
| 2 | `analyzer.py` + tests | 2-3 hs | No |
| 3 | `charts.py` + tests visuales | 1-2 hs | No |
| 4 | `narrator.py` | 1 hs | No |
| 5 | Endpoint + smoke | 30 min | Sí |
| 6 | Página `/insights` real | 2 hs | Sí |

Total: ~8-10 horas. Plan aprobado por el usuario.

**En este punto del proyecto** se acordó: **arrancar con el paso 1** (landing + routing), pausa para revisión, después correr pasos 2-5 de un tirón, cerrar con paso 6.

### Dependencias nuevas a agregar en requirements.txt

```
matplotlib
scikit-learn
scipy
```

---

## Limitaciones conocidas

### Funcionales

- **No hay upload de archivos**. Versión A del Insights: corre sobre parquets cargados.
- **No hay analytical joins** entre tools (no puede garantizar que "las Wealthy con alto LP" y "el promedio de GP UE" hablan de las mismas zonas).
- **No hay ranking multi-métrica con pesos** (score combinado).
- **Max 9 semanas de datos** (L0W..L8W). No hay fechas absolutas.
- **Unidad mínima = zona**. No hay datos de courier / merchant / usuario.
- **No hay detección de anomalías formal** en los handlers (el módulo Insights lo va a agregar).
- **Bot no se entera del scale drift**: si cambia el `METRIC_DICTIONARY` sin tests, los schemas enum del tool se desincronizan silenciosamente.

### Operacionales

- **Memoria in-process**: un worker ok, múltiples workers no comparten sesiones.
- **Sin autenticación**: endpoint abierto.
- **Sin rate limiting**: un usuario puede saturar el backend / gastar tokens.
- **Sin cache de queries**: mismas preguntas en minutos hacen doble llamada al LLM.
- **Sin streaming**: respuestas largas tardan 6-10s sin feedback visual.
- **Tool budget = 5 iteraciones** por turno; queries complejas cross-país pueden cortarse.

### LLM-as-analyst

- Los caveats (Nivel 2) cubren 5 pitfalls estadísticos. Cualquier otro (Simpson's paradox, cherry-picking del top 1, correlación espuria fuera de las métricas del catálogo) queda al criterio del modelo.
- No hay crítica post-generación (Nivel 3) que audite la respuesta antes de mandarla al usuario.

---

## Estilo de interacción del usuario

Notas para el próximo agente sobre cómo comunicarse con Julián:

- **Idioma**: prefiere español conversacional. Rioplatense u ok. Código en inglés, docstrings en inglés. Solo usa emojis cuando el usuario los pide explícitamente.
- **Concisión sobre floridez**. Va directo al punto. No le sirven los rodeos.
- **Le gusta saber el "por qué"** de cada decisión técnica, no solo el "qué". Valora que expliques trade-offs.
- **Es muy sensible al over-engineering**. Siempre justificar cuándo aplicar un parche puntual vs una solución estructural. El debate "Nivel 1 vs Nivel 2 vs Nivel 3" aparece recurrentemente.
- **Es honesto y espera honestidad**. Si el bot alucina o el stack tiene una debilidad, prefiere que se lo digan directo con la validación empírica. Ejemplo: cuando validamos con DuckDB el claim de "525% crecimiento", el feedback de "matemáticamente correcto pero analíticamente engañoso" fue bien recibido.
- **Le gusta ver los incrementos funcionando**. Pausas cortas entre pasos, cada uno con tests pasando. No "un gran bloque al final".
- **Toma decisiones rápido** cuando le presentás opciones claras con trade-offs. Evitar listar 10 alternativas; proponer 2-3 y dar tu recomendación.
- **Valida contra realidad**. Cuando le diste números estadísticos o hallazgos, estuvo dispuesto a pedir que queries directo a DuckDB para verificar. Construir esas validaciones es más valioso que reportar.
- **Es pragmático**. Prefiere "funciona bien para 80% de los casos y es honesto sobre el 20% restante" sobre "perfecto en teoría pero complejo".

---

## Checklist rápido para arrancar el próximo chat

- [ ] Leer este archivo completo.
- [ ] Correr `make test` — tienen que pasar 163 tests.
- [ ] Correr `make run` en una terminal, `make frontend-dev` en otra. Abrir http://localhost:3000 y verificar que el chat anda.
- [ ] (Opcional) `make smoke-bot CASES="1 3"` para validar end-to-end con LLM real (gasta ~$0.005).
- [ ] Ubicarte en el próximo incremento: **módulo Insights**, plan de 6 pasos arriba, arrancar por el paso 1.
- [ ] Si el usuario pide algo que parece salirse del scope actual, revisar la sección "Limitaciones conocidas" antes de prometer algo.

---

## Comandos frecuentes (cheat sheet)

```bash
# Desde la raíz siempre:
cd /Users/jumafe/Desktop/personal_things/Bot_conversacional

# Backend
make install                # pip install -r requirements-dev.txt
make clean-data             # Excel → parquet (corre una sola vez)
make run                    # uvicorn :8000 con reload
make test                   # pytest full suite
make smoke-bot              # live test contra LLM (gasta tokens)

# Frontend
make frontend-install       # npm install (una vez)
make frontend-dev           # next dev :3000
make frontend-build         # next build (producción)

# Testing backend puntual
PYTHONPATH=. pytest tests/test_services/test_llm_service.py -v

# Debug manual contra DuckDB
PYTHONPATH=. python -c "
import duckdb
con = duckdb.connect(':memory:')
con.execute(\"CREATE VIEW m AS SELECT * FROM 'data/processed/metrics_wide.parquet'\")
print(con.execute('SELECT COUNT(*) FROM m').fetchone())
"

# Dispatch directo de una tool (sin LLM)
PYTHONPATH=. python -c "
import json
from backend.tools.registry import dispatch
r = dispatch('filter_zones', {'metric': 'Perfect Orders', 'country': 'CO', 'limit': 3})
print(json.dumps(r, indent=2, default=str))
"

# Ruff / vulture (si hace falta)
~/.local/bin/ruff check backend/ scripts/ tests/
~/.local/bin/vulture backend/ --min-confidence 80

# Limpiar cache Next corrupto
cd frontend && rm -rf .next node_modules/.cache && cd ..
```

---

*Fin del handoff. Última modificación: 2026-04-21 tras acordar el módulo Insights.*
