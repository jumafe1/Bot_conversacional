"""
System prompt builder.

Constructs the system prompt injected at the start of every conversation.
The prompt is assembled dynamically so future additions (e.g., current
date, user context) can be included without changing call sites.

Exposes:
    build_system_prompt() -> str

TODO:
    1. Add Rappi business context section:
       - What Rappi is, what verticals it operates (restaurants, super,
         pharmacy, liquors, turbo).
       - Audience: non-technical teams (Strategy, Planning & Analytics, Operations).
    2. Add metric dictionary injection (import from metric_dictionary.py).
    3. Add business term glossary:
       - "zona problemática" → zone where one or more key metrics are below
         acceptable thresholds (define thresholds here or make configurable).
       - "zona de alto rendimiento" → above-threshold zones.
    4. Add behavioral instructions:
       - Always respond in the same language the user writes in.
       - Be concise but complete; use markdown tables for tabular data.
       - Always end with exactly 2–3 follow-up suggestions labeled as
         "**Análisis sugerido:**" (or "**Suggested analysis:**" in English).
       - Do not invent data; if a query returns no results, say so clearly.
       - Call tools when data is needed; do not answer from memory.
    5. Add available countries list (9 LATAM markets).
    6. Add current date injection for temporal context.
"""

from __future__ import annotations

from datetime import date


def build_system_prompt() -> str:
    """Assemble and return the full system prompt string.

    TODO: implement the sections described in the module docstring.
    """
    today = date.today().isoformat()

    # Placeholder — replace with full prompt once structure is decided
    return f"""You are a data analyst assistant for Rappi, a leading Latin American
super-app operating across 9 countries (Colombia, México, Brazil, Argentina,
Chile, Perú, Ecuador, Uruguay, Costa Rica).

Today's date is {today}.

## Your Role
Help non-technical teams (Strategy, Planning & Analytics, Operations) query
operational metrics by calling the available tools. Never answer data questions
from memory — always use the tools to retrieve real data.

## Response Format
- Use markdown tables for tabular results.
- Be concise but complete.
- End every response with a section labeled **Suggested next analyses:** containing
  2–3 relevant follow-up questions the user might want to explore.

## METRIC DICTIONARY
(TODO: inject METRIC_DICTIONARY from metric_dictionary.py here)

## BUSINESS GLOSSARY
- "zona problemática" / "problematic zone": a zone where one or more key metrics
  fall below acceptable thresholds.
- "zona de alto rendimiento" / "high-performing zone": a zone consistently above
  benchmark on the main metrics.
"""
