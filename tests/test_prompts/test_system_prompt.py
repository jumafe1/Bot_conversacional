"""
Tests for the system prompt builder.

We don't assert exact wording (the prompt will evolve as we tune the bot's
behavior), but we DO assert the invariants that keep the prompt in sync with
the rest of the stack:

    - every canonical metric name appears literally in the text
    - every valid country / zone_type / zone_prioritization / week appears
    - the three non-proportion scale notes are embedded (LLM needs them to
      interpret Gross Profit UE and Lead Penetration correctly)
    - today's date is injected
    - the names of the six tools are all mentioned in the cheatsheet

These are the guarantees the LLM relies on. If someone adds a new metric or
a new country to the dataset, these tests will fail until the prompt picks
it up automatically via the registered sources of truth.
"""

from __future__ import annotations

from datetime import date

from backend.prompts.metric_dictionary import METRIC_DICTIONARY
from backend.prompts.system_prompt import build_system_prompt
from backend.repositories.metrics_repository import (
    VALID_COUNTRIES,
    VALID_WEEK_COLS,
    VALID_ZONE_PRIORITIZATIONS,
    VALID_ZONE_TYPES,
)


def test_returns_non_empty_string() -> None:
    prompt = build_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 500


def test_injects_today_override() -> None:
    prompt = build_system_prompt(today=date(2025, 6, 15))
    assert "2025-06-15" in prompt


def test_every_metric_name_appears() -> None:
    prompt = build_system_prompt()
    for metric in METRIC_DICTIONARY.keys():
        assert metric in prompt, f"Metric missing from prompt: {metric!r}"


def test_every_metric_description_appears() -> None:
    # At least one distinctive fragment per metric — prevents silent drift
    # where a metric name is present but its description is stale.
    prompt = build_system_prompt()
    for metric, info in METRIC_DICTIONARY.items():
        # Use first 40 chars of the description as a unique fingerprint
        fragment = info["description"][:40]
        assert fragment in prompt, f"Description missing for {metric!r}"


def test_non_proportion_scale_notes_present() -> None:
    """Gross Profit UE + Lead Penetration carry scale_note warnings the LLM must see."""
    prompt = build_system_prompt()
    for metric, info in METRIC_DICTIONARY.items():
        if info["scale"] != "proportion":
            assert info["scale_note"] in prompt, (
                f"scale_note missing for non-proportion metric {metric!r}"
            )


def test_every_country_code_appears() -> None:
    prompt = build_system_prompt()
    for country in VALID_COUNTRIES:
        assert f"`{country}`" in prompt, f"Country code missing: {country}"


def test_every_week_column_appears() -> None:
    prompt = build_system_prompt()
    for week in VALID_WEEK_COLS:
        assert week in prompt, f"Week column missing: {week}"


def test_every_zone_type_appears() -> None:
    prompt = build_system_prompt()
    for zt in VALID_ZONE_TYPES:
        assert zt in prompt, f"Zone type missing: {zt}"


def test_every_zone_prioritization_appears() -> None:
    prompt = build_system_prompt()
    for zp in VALID_ZONE_PRIORITIZATIONS:
        assert zp in prompt, f"Zone prioritization missing: {zp}"


def test_all_six_tool_names_mentioned() -> None:
    prompt = build_system_prompt()
    for tool in (
        "filter_zones",
        "compare_metrics",
        "get_trend",
        "aggregate",
        "multivariate",
        "orders_growth",
    ):
        assert tool in prompt, f"Tool name missing from cheatsheet: {tool}"


def test_scale_categories_documented() -> None:
    prompt = build_system_prompt()
    for scale in ("proportion", "monetary", "ratio_unbounded"):
        assert scale in prompt, f"Scale category missing: {scale}"


def test_response_format_section_present() -> None:
    prompt = build_system_prompt()
    # Bilingual closing block label
    assert "Análisis sugerido" in prompt
    assert "Suggested next analyses" in prompt


def test_bilingual_language_instruction() -> None:
    prompt = build_system_prompt().lower()
    # The bot must mirror the user's language; assert the instruction is in.
    assert "match the user's language" in prompt or "match the user language" in prompt


def test_scope_section_present() -> None:
    """The bot must know it is domain-locked to Rappi metrics."""
    prompt = build_system_prompt()
    # Section header
    assert "## Scope" in prompt
    # Key guardrails that protect against off-topic answers
    assert "Out of scope" in prompt
    assert "politely decline" in prompt.lower()
    # Refusal templates in both languages
    assert "Perdón, no puedo ayudarte" in prompt
    assert "Sorry, I can't help with that" in prompt
    # The explicit list must name the most common attempted misuses
    for keyword in (
        "Fitness",
        "coding help",
        "Future predictions",
        "ignore previous instructions",
    ):
        assert keyword in prompt, f"Scope keyword missing: {keyword!r}"


def test_scope_section_appears_before_tool_contract() -> None:
    """Scope must be visible early so the LLM reads it before tool guidance."""
    prompt = build_system_prompt()
    scope_idx = prompt.find("## Scope")
    tool_idx = prompt.find("## Tool-use contract")
    assert scope_idx != -1 and tool_idx != -1
    assert scope_idx < tool_idx, "Scope block must come before the tool-use contract."
