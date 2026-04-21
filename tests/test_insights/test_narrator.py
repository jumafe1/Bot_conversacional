"""Tests for ``backend.insights.narrator`` using a mocked OpenAI client."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.exceptions import LLMProviderError
from backend.insights.narrator import narrate
from backend.insights.schemas import (
    AnalysisMetadata,
    AnalysisResult,
    AnomalyFinding,
    NarratorOutput,
)


def _empty_analysis() -> AnalysisResult:
    return AnalysisResult(
        metadata=AnalysisMetadata(
            total_zones=100,
            countries=["CO", "MX"],
            n_metrics=13,
            week_window="L0W_ROLL..L8W_ROLL",
        ),
        anomalies=[],
        trends=[],
        benchmarks=[],
        correlations=[],
        opportunities=[],
    )


def _fake_client_returning(payload: dict | str) -> MagicMock:
    """Build a mock AsyncOpenAI whose .chat.completions.create returns ``payload``."""
    content = payload if isinstance(payload, str) else json.dumps(payload)
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


async def test_narrate_parses_well_formed_response() -> None:
    payload = {
        "executive_summary": "- Hallazgo 1\n- Hallazgo 2",
        "anomalies": {"narrative": "Cayó 22% en Chapinero.", "recommendation": "Revisar supply."},
        "trends": {"narrative": "N/A", "recommendation": "—"},
        "benchmarks": {"narrative": "UY está 2σ abajo.", "recommendation": "Focus UY."},
        "correlations": {"narrative": "LP y PO correlacionan 0.6.", "recommendation": "Investigar link."},
        "opportunities": {"narrative": "Pereira +15%.", "recommendation": "Duplicar inversión."},
    }
    client = _fake_client_returning(payload)

    out = await narrate(_empty_analysis(), client=client, model="gpt-test")
    assert isinstance(out, NarratorOutput)
    assert "Hallazgo 1" in out.executive_summary
    assert out.anomalies.narrative == "Cayó 22% en Chapinero."
    assert out.opportunities.recommendation == "Duplicar inversión."

    # The system prompt + findings were sent to the SDK.
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["model"] == "gpt-test"
    assert "max_completion_tokens" in kwargs


async def test_narrate_handles_missing_sections_gracefully() -> None:
    # LLM returns partial JSON — we should still produce a NarratorOutput
    # with fallback strings rather than crashing.
    partial = {
        "executive_summary": "Solo resumen, sin secciones.",
    }
    out = await narrate(_empty_analysis(), client=_fake_client_returning(partial))
    assert "Solo resumen" in out.executive_summary
    # Every section has SOMETHING even though the LLM didn't send it.
    for s in (out.anomalies, out.trends, out.benchmarks, out.correlations, out.opportunities):
        assert s.narrative and s.recommendation


async def test_narrate_raises_on_non_json_response() -> None:
    client = _fake_client_returning("this is not JSON at all")
    with pytest.raises(LLMProviderError, match="non-JSON"):
        await narrate(_empty_analysis(), client=client)


async def test_narrate_wraps_sdk_errors() -> None:
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(LLMProviderError, match="Narrator failed"):
        await narrate(_empty_analysis(), client=client)


async def test_narrate_trims_findings_to_top_5() -> None:
    """User payload sent to the LLM carries at most 5 findings per category."""
    analysis = _empty_analysis()
    analysis.anomalies = [
        AnomalyFinding(
            zone=f"Z{i}", city="C", country="CO", metric="Perfect Orders",
            current=1.0, previous=2.0, delta_pct=-50.0, direction="down",
        )
        for i in range(10)
    ]
    payload = {
        "executive_summary": "",
        "anomalies": {"narrative": "x", "recommendation": "x"},
        "trends": {"narrative": "x", "recommendation": "x"},
        "benchmarks": {"narrative": "x", "recommendation": "x"},
        "correlations": {"narrative": "x", "recommendation": "x"},
        "opportunities": {"narrative": "x", "recommendation": "x"},
    }
    client = _fake_client_returning(payload)

    await narrate(analysis, client=client)
    user_msg = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    body = json.loads(user_msg)
    assert len(body["anomalies"]) == 5
    assert body["counts"]["anomalies"] == 10  # full count preserved in metadata
