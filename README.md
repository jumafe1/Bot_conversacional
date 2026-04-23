# Rappi Conversational Data Bot

Repositorio para explorar metricas operativas de Rappi sobre 9 mercados LATAM a partir de una base Excel procesada a Parquet.

El producto tiene dos flujos principales:

1. **Chat conversacional**: el usuario pregunta en lenguaje natural y el backend usa un LLM con tool calling para consultar DuckDB.
2. **Reporte de insights**: el sistema genera un reporte ejecutivo automatico con hallazgos, graficos y narrativa asistida por LLM.

## Modelo y costos

El backend usa OpenAI por defecto con el modelo `gpt-5.4-mini`:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-mini
```

Tarifa oficial de GPT-5.4 mini consultada en OpenAI API Pricing:

| Tipo de token | Precio |
|---|---:|
| Input | US$0.75 / 1M tokens |
| Cached input | US$0.075 / 1M tokens |
| Output | US$4.50 / 1M tokens |

Fuente: [OpenAI API Pricing](https://openai.com/api/pricing/). Las tarifas pueden cambiar; revisar esa pagina antes de presupuestar produccion.

Medicion practica del proyecto:

- Mas de 20 mensajes al bot conversacional.
- Aproximadamente 8 generaciones de insights automaticos.
- Costo observado: alrededor de US$0.40.

Ese numero es una referencia empirica, no una garantia: depende del largo de las conversaciones, cantidad de tool calls, cache, numero de insights regenerados y longitud de las narrativas.

## Dataset

El archivo de entrada es el mismo Excel habilitado para macros (`.xlsm`) que fue enviado por correo.

Para que el pipeline lo encuentre:

1. Copiar el archivo a `data/raw/`.
2. Renombrarlo como `Bot_datos.xlsx`.
3. Ejecutar `make clean-data`.

No hace falta configurar ese archivo en `.env`. El path del raw file esta fijo en `scripts/clean_data.py` como:

```text
data/raw/Bot_datos.xlsx
```

La variable `DATA_DIR` del `.env` solo apunta a los Parquet ya procesados:

```env
DATA_DIR=data/processed
```

## Setup

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
make install

cp .env.example .env
# Configurar al menos OPENAI_API_KEY

cp /path/to/archivo_recibido_por_correo.xlsm data/raw/Bot_datos.xlsx
make clean-data
make run
```

Backend disponible en:

- `http://localhost:8000`
- `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Frontend disponible en:

- `http://localhost:3000`

## Que hace el sistema

### Chat sobre metricas

Permite consultar datos sin escribir SQL:

- rankings de zonas por metrica
- comparaciones entre grupos
- tendencias semanales
- agregados
- filtros multivariables
- crecimiento de ordenes

Flujo:

```text
pregunta del usuario -> FastAPI -> BotService -> LLMService -> tools -> DuckDB -> respuesta
```

### Reporte automatico de insights

Genera un reporte ejecutivo con cinco secciones:

- anomalias semana contra semana
- tendencias preocupantes
- benchmarking contra peer groups
- correlaciones entre metricas
- oportunidades

El analisis numerico es deterministico; el LLM solo narra hallazgos y recomendaciones.

## Arquitectura

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                         │
│                    Landing / Chat / Insights UI                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
        POST /api/v1/chat          POST /api/v1/insights/*
                 │                           │
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                             │
│                                                                     │
│  Chat path:                                                         │
│  api/v1/chat -> BotService -> LLMService -> tools/registry          │
│                                -> metrics_repository -> DuckDB      │
│                                                                     │
│  Insights path:                                                     │
│  api/v1/insights -> insights/service -> analyzer -> charts          │
│                                         -> narrator                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                   DuckDB in-process sobre Parquet
```

## Stack tecnico

| Capa | Tecnologia | Uso |
|---|---|---|
| Frontend | Next.js 15 + React 19 + assistant-ui | Chat UI, landing e insights UI |
| Backend | FastAPI | API HTTP y composicion de servicios |
| LLM | OpenAI GPT-5.4 mini | Tool calling en chat, narrativa en insights |
| Data engine | DuckDB | Consultas analiticas in-process |
| Data format | Parquet | Tablas procesadas desde Excel |
| Data wrangling | pandas / pyarrow / openpyxl | Limpieza e ingestion |
| Stats | scipy | Detectores para insights |
| Charts | matplotlib | Visualizaciones del reporte |
| Config | pydantic-settings | Variables de entorno tipadas |
| Logging | structlog | Logs estructurados |

## Pipeline de datos

`scripts/clean_data.py` lee `data/raw/Bot_datos.xlsx` y genera:

- `data/processed/metrics_wide.parquet`
- `data/processed/metrics_long.parquet`
- `data/processed/orders_wide.parquet`
- `data/processed/orders_long.parquet`

DuckDB registra esos Parquet como vistas al iniciar la app.

Semantica temporal:

- `L0W_ROLL`: semana mas reciente
- `L1W_ROLL`: hace 1 semana
- ...
- `L8W_ROLL`: hace 8 semanas

No hay fechas absolutas en el dataset; el sistema trabaja con offsets relativos.

## Endpoints principales

### Chat

- `POST /api/v1/chat`
- `GET /api/v1/health`

### Insights

- `POST /api/v1/insights/generate`
- `POST /api/v1/insights/sections/{section_id}/recompute`
- `POST /api/v1/insights/sections/{section_id}/refresh-narrative`
- `GET /api/v1/insights/filter-options`

## Estructura del repo

```text
Bot_conversacional/
├── backend/
│   ├── api/v1/          # chat, health, insights
│   ├── core/            # config, logging, exceptions
│   ├── insights/        # analyzer, charts, narrator, service
│   ├── prompts/         # system prompt + metric dictionary
│   ├── repositories/    # DuckDB access layer
│   ├── schemas/         # contratos Pydantic del chat
│   ├── services/        # bot, llm, memory
│   └── tools/           # herramientas callable por el LLM
├── data/
│   ├── raw/             # Excel de entrada: Bot_datos.xlsx
│   └── processed/       # Parquet generados
├── docs/
├── frontend/
├── scripts/
└── tests/
```

## Herramientas del bot

El chat expone estas herramientas al LLM:

- `filter_zones`
- `compare_metrics`
- `get_trend`
- `aggregate`
- `multivariate`
- `orders_growth`

Todas consultan DuckDB via `metrics_repository`.

## Verificacion

Chequeos ejecutados sobre el estado actual del repo:

- `pytest`: 207 tests pasan.
- `ruff check .`: pasa.
- `npx tsc --noEmit`: pasa.
- `npm run typecheck`: pasa.
- `npm run lint`: hoy no corre de forma no interactiva porque `next lint` abre el asistente de configuracion de ESLint.

## Limitaciones actuales

- La memoria conversacional es in-process; se pierde al reiniciar el backend.
- No hay autenticacion ni autorizacion en la API.
- El lint del frontend no esta configurado para ejecutarse de forma reproducible.
- El reporte de insights cachea en memoria por proceso; no hay cache compartido.
- La capa de presentacion del chat todavia depende de texto/tablas; no hay visualizaciones nativas para resultados de tools.

## Documentacion adicional

- [docs/architecture.md](docs/architecture.md)
- [docs/data_quality_report.md](docs/data_quality_report.md)
- [docs/cleaning_report.md](docs/cleaning_report.md)
- [docs/cost_estimation.md](docs/cost_estimation.md)
- [frontend/README.md](frontend/README.md)
