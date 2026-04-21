"""
LLM-based narrator for the insights report.

Takes the fully-computed :class:`AnalysisResult` and produces the human
prose: an executive summary plus one paragraph + one actionable recommendation
per category.

Design principles:

- **The LLM never does arithmetic.** It receives findings already reduced
  to numbers and labels; its job is verbal packaging only.
- **Structured output.** We use OpenAI's ``response_format={"type":
  "json_object"}`` so the return shape is deterministic — no regex.
- **One call per report.** Every category is narrated in a single LLM turn
  to keep cost predictable (~1-2 cents per report on gpt-5.4-mini).
- **Idempotent on identical inputs.** Given the same findings (and the same
  cached system prompt), the same narrative is produced up to LLM variance.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.core.config import settings
from backend.core.exceptions import LLMProviderError
from backend.insights.schemas import AnalysisResult, NarratorOutput, SectionNarrative

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Eres un analista de datos senior de Rappi. Recibes findings YA COMPUTADOS
estadísticamente sobre las métricas operativas de 9 mercados LATAM. Tu único
trabajo es redactar en español rioplatense claro y conciso — NO haces
matemática, NO inventas números, NO generas findings adicionales.

Para el reporte debes producir:

1. **Resumen ejecutivo** — 3 a 5 bullets en markdown con los hallazgos más
   críticos transversalmente. Sintetizás lo más importante de TODAS las
   categorías, no repetís findings individuales.

2. **Una narrativa y una recomendación por cada una de las 5 categorías**:
   anomalies, trends, benchmarks, correlations, opportunities.

   - **Narrativa**: 2 a 4 oraciones en prosa. Mencioná las zonas y métricas
     específicas que vienen en los findings. Números exactos — no redondeos
     creativos. Si la lista está vacía, decilo honestamente (p.ej. "No se
     detectaron anomalías significativas esta semana").
   - **Recomendación**: una acción concreta, específica y accionable.
     Evitá genéricos tipo "monitorear de cerca". Mejor: "revisar cobertura
     de supply en Chapinero la próxima semana; el drop de Perfect Orders
     probablemente refleja fricción en la última milla."

Reglas duras:

- Usá EXCLUSIVAMENTE los datos que vienen en el JSON de findings.
- **Formato numérico**: porcentajes con 1 decimal (ej. "22.5%"), valores con
  2 decimales (ej. "0.85"), correlaciones con 2 decimales (ej. "r=0.63").
  NUNCA copies pegado un número con 10+ decimales del payload — redondeá.
- Si una zona aparece en un finding con `delta_pct=-22.547`, decilo como
  "cayó 22.5%", no como "~20%" ni "22.547%".
- Para Gross Profit UE (monetario) y Lead Penetration (ratio sin cap de 1),
  no presentes valores como porcentajes a menos que el finding lo indique.
- Cuando una lista tiene 10 findings, no los menciones todos — elegí los 2
  o 3 más representativos.
- Nada de emojis.

Responde SIEMPRE con JSON válido que cumpla el siguiente schema:

{
  "executive_summary": "markdown string",
  "anomalies":       { "narrative": "...", "recommendation": "..." },
  "trends":          { "narrative": "...", "recommendation": "..." },
  "benchmarks":      { "narrative": "...", "recommendation": "..." },
  "correlations":    { "narrative": "...", "recommendation": "..." },
  "opportunities":   { "narrative": "...", "recommendation": "..." }
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def narrate(
    result: AnalysisResult,
    *,
    client: Any | None = None,
    model: str | None = None,
) -> NarratorOutput:
    """Send the analysis to the LLM and return the narrated sections.

    Args:
        result: The deterministic analysis output.
        client: Optional injected async OpenAI client (tests use this to
            avoid hitting the real API). Defaults to a new AsyncOpenAI.
        model: Model override for tests / experiments. Defaults to
            ``settings.LLM_MODEL``.

    Raises:
        LLMProviderError: any failure from the SDK surfaces as this type,
            which the API layer maps to HTTP 502.
    """
    model = model or settings.LLM_MODEL
    client = client or _default_client()

    user_payload = _build_user_payload(result)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=settings.LLM_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 — wrap every SDK failure
        logger.exception("Insights narrator LLM call failed")
        raise LLMProviderError(f"Narrator failed: {exc}") from exc

    content = response.choices[0].message.content or ""
    parsed = _parse_llm_json(content)
    return _to_output(parsed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_client() -> Any:
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def _build_user_payload(result: AnalysisResult) -> dict:
    """Trim + stringify the analysis result for the narrator prompt.

    We only send the top 3-5 findings per category (not all 10), because:
      - The LLM narrates 2-3 zones per section anyway; more would just burn
        tokens.
      - The full data lives in ``InsightsSection.findings`` and the UI
        renders it separately.

    Numbers are rounded here so the LLM never sees 13-decimal artefacts —
    cheap insurance against narratives that paste raw floats verbatim.
    """
    return {
        "metadata": result.metadata.model_dump(),
        "counts": {
            "anomalies": len(result.anomalies),
            "trends": len(result.trends),
            "benchmarks": len(result.benchmarks),
            "correlations": len(result.correlations),
            "opportunities": len(result.opportunities),
        },
        "anomalies": [_round_floats(f.model_dump()) for f in result.anomalies[:5]],
        "trends": [_round_floats(f.model_dump()) for f in result.trends[:5]],
        "benchmarks": [_round_floats(f.model_dump()) for f in result.benchmarks[:5]],
        "correlations": [
            _round_floats(f.model_dump()) for f in result.correlations[:5]
        ],
        "opportunities": [
            _round_floats(f.model_dump()) for f in result.opportunities[:5]
        ],
    }


def _round_floats(d: dict, *, decimals: int = 3) -> dict:
    """Return a shallow copy with every float value rounded to ``decimals``."""
    return {
        k: (round(v, decimals) if isinstance(v, float) else v) for k, v in d.items()
    }


def _parse_llm_json(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(
            f"Narrator returned non-JSON payload: {content[:200]}..."
        ) from exc


def _to_output(parsed: dict) -> NarratorOutput:
    """Map the LLM JSON into our pydantic model, with defensive fallbacks."""
    def section(key: str) -> SectionNarrative:
        raw = parsed.get(key) or {}
        return SectionNarrative(
            narrative=str(raw.get("narrative", "")).strip() or _EMPTY_SECTION_FALLBACK,
            recommendation=str(raw.get("recommendation", "")).strip()
            or _EMPTY_SECTION_FALLBACK,
        )

    return NarratorOutput(
        executive_summary=str(
            parsed.get("executive_summary", _EMPTY_SUMMARY_FALLBACK)
        ).strip(),
        anomalies=section("anomalies"),
        trends=section("trends"),
        benchmarks=section("benchmarks"),
        correlations=section("correlations"),
        opportunities=section("opportunities"),
    )


_EMPTY_SUMMARY_FALLBACK = "_(No se generó un resumen ejecutivo esta corrida.)_"
_EMPTY_SECTION_FALLBACK = "_(No hay narrativa disponible para esta sección.)_"


# ---------------------------------------------------------------------------
# Single-section narrator — used by the interactive /refresh-narrative endpoint
# ---------------------------------------------------------------------------

_SINGLE_SECTION_SYSTEM_PROMPT = """\
Eres un analista de datos senior de Rappi. Recibís findings YA COMPUTADOS
estadísticamente para UNA sola sección del reporte interactivo, junto con
los filtros que el usuario eligió. Tu trabajo es redactar narrativa y
recomendación solo para esa sección — no hagas matemática, no inventes
números, no generes findings adicionales.

- **narrative**: 2 a 4 oraciones en prosa rioplatense, mencionando zonas y
  métricas específicas de los findings. Números exactos con redondeo
  razonable (porcentajes 1 decimal, valores 2 decimales, r con 2 decimales).
  Si la lista de findings viene vacía, decilo honestamente e interpretá el
  porqué en el contexto de los filtros que el usuario aplicó.
- **recommendation**: una acción concreta y accionable. Evitá genéricos.
  Si no hay findings, sugerí qué filtro diferente probar.

Hacé referencia explícita a los filtros aplicados para que quede claro qué
slice se está narrando (ej. "Con el filtro Perfect Orders + últimas 5
semanas..."). Nada de emojis.

Responde SIEMPRE con JSON válido:

{
  "narrative": "...",
  "recommendation": "..."
}
"""


_SECTION_DESCRIPTIONS: dict[str, str] = {
    "anomalies": "anomalías (zonas con mayor cambio entre dos semanas)",
    "trends": "tendencias (series con deterioro significativo)",
    "benchmarks": "benchmarking (zonas por debajo de sus pares)",
    "correlations": "correlación entre dos métricas",
    "opportunities": "oportunidades (zonas con momentum positivo)",
}


async def narrate_single_section(
    *,
    section_id: str,
    filters: dict,
    findings: list[dict],
    client: Any | None = None,
    model: str | None = None,
) -> SectionNarrative:
    """Re-narrate one section with user-chosen filters.

    Unlike the batch ``narrate()``, this function does not require a full
    ``AnalysisResult`` — the interactive endpoint already has the section's
    findings on hand and sends them directly.

    Raises:
        LLMProviderError: mapped to HTTP 502 upstream.
    """
    model = model or settings.LLM_MODEL
    client = client or _default_client()

    user_payload = {
        "section": section_id,
        "section_description": _SECTION_DESCRIPTIONS.get(section_id, section_id),
        "filters_applied": filters,
        "n_findings": len(findings),
        "findings": [_round_dict_floats(f) for f in findings[:5]],
    }

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SINGLE_SECTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=settings.LLM_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Single-section narrator call failed")
        raise LLMProviderError(f"Section narrator failed: {exc}") from exc

    content = response.choices[0].message.content or ""
    parsed = _parse_llm_json(content)
    return SectionNarrative(
        narrative=str(parsed.get("narrative", "")).strip() or _EMPTY_SECTION_FALLBACK,
        recommendation=str(parsed.get("recommendation", "")).strip()
        or _EMPTY_SECTION_FALLBACK,
    )


def _round_dict_floats(d: dict, *, decimals: int = 3) -> dict:
    """Same idea as ``_round_floats`` but for arbitrary dict payloads."""
    return {
        k: (round(v, decimals) if isinstance(v, float) else v) for k, v in d.items()
    }
