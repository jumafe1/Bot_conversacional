"""
Live smoke test of the BotService against the configured LLM provider.

Run from the project root:

    PYTHONPATH=. python scripts/smoke_test_bot.py
    PYTHONPATH=. python scripts/smoke_test_bot.py --only 1 3     # just cases 1 and 3
    PYTHONPATH=. python scripts/smoke_test_bot.py --confirm-cost  # spends real tokens

What it does:
    1. Instantiates a real BotService (real LLMService + MemoryService).
    2. Sends a handful of representative user questions, one per session,
       so every turn starts from an empty memory.
    3. Prints, for each turn:
         - the user message
         - the tools the LLM decided to call (and in what order)
         - the bot's final answer
         - the parsed suggestions
         - per-turn token usage
    4. Prints a grand total at the end so you can eyeball cost.

It does NOT hit the FastAPI endpoint — we exercise the service layer
directly to keep the output readable. If the HTTP path also needs
validating, start the server (`make run`) and curl `/api/v1/chat`.

Safety:
    - Requires an explicit ``--confirm-cost`` flag so running the script by
      accident never bills your OpenAI / Anthropic account.
    - Output includes token counts per turn so you can stop early if the
      prompt is bleeding tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import textwrap
import traceback
from dataclasses import dataclass
from time import perf_counter

# Allow execution as `python scripts/smoke_test_bot.py` as well as with
# `PYTHONPATH=.`. Prepend the project root to sys.path when missing.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@dataclass
class SmokeCase:
    title: str
    message: str
    expected_tools: tuple[str, ...] | None = None  # soft expectation; warn if mismatch


CASES: list[SmokeCase] = [
    SmokeCase(
        title="1. Ranking simple — debería elegir filter_zones",
        message="¿Cuáles son las 5 zonas con mejor Perfect Orders en Colombia?",
        expected_tools=("filter_zones",),
    ),
    SmokeCase(
        title="2. Comparación categórica — debería elegir compare_metrics",
        message=(
            "Compará Perfect Orders entre zonas Wealthy y Non Wealthy en México."
        ),
        expected_tools=("compare_metrics",),
    ),
    SmokeCase(
        title="3. Tendencia temporal — debería elegir get_trend",
        message=(
            "¿Cómo evolucionó Lead Penetration en Colombia durante las últimas "
            "8 semanas?"
        ),
        expected_tools=("get_trend",),
    ),
    SmokeCase(
        title="4. Multivariable — debería elegir multivariate",
        message=(
            "Dame las zonas en Colombia con Perfect Orders menor a 0.9 y "
            "Lead Penetration mayor a 0.3."
        ),
        expected_tools=("multivariate",),
    ),
    SmokeCase(
        title="5. Crecimiento de órdenes — debería elegir orders_growth",
        message="¿Cuáles son las 5 zonas de mayor crecimiento de órdenes en CO?",
        expected_tools=("orders_growth",),
    ),
    SmokeCase(
        title="6. Métrica monetaria — debe respetar scale_note",
        message="¿Cuál es el Gross Profit UE promedio en cada país?",
        expected_tools=("aggregate",),
    ),
    SmokeCase(
        title="7. Pregunta ambigua / fuera de catálogo",
        message="¿Qué zona tiene la mejor experiencia de cliente?",
        expected_tools=None,  # just observe; no hard expectation
    ),
]


BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _banner(text: str, colour: str = BLUE) -> None:
    line = "─" * 78
    print(f"\n{colour}{line}\n{BOLD}{text}{RESET}{colour}\n{line}{RESET}")


def _field(label: str, value: str, colour: str = "") -> None:
    print(f"{BOLD}{label}:{RESET} {colour}{value}{RESET}")


def _wrap(text: str, indent: str = "  ") -> str:
    return textwrap.indent(
        "\n".join(textwrap.fill(line, width=96) for line in text.splitlines()),
        indent,
    )


async def _run_case(bot, case: SmokeCase) -> tuple[int, int]:
    """Run one case and return (input_tokens, output_tokens)."""
    _banner(case.title)
    _field("user", case.message, BLUE)

    session_id = f"smoke-{abs(hash(case.message)) % 10**8}"
    started = perf_counter()
    try:
        response = await bot.process_message(
            session_id=session_id, user_message=case.message
        )
    except Exception as exc:  # noqa: BLE001 — smoke test wants full traceback
        print(f"{RED}{BOLD}ERROR:{RESET} {exc}")
        traceback.print_exc()
        return 0, 0
    elapsed = perf_counter() - started

    tools = response.tool_calls_used or ["(none)"]
    expected = case.expected_tools
    tools_ok = expected is None or any(t in tools for t in expected)
    tools_colour = GREEN if tools_ok else YELLOW
    _field("tools", ", ".join(tools), tools_colour)

    if expected and not tools_ok:
        print(
            f"{YELLOW}  ↳ heads-up: expected one of "
            f"{list(expected)} but got {tools}{RESET}"
        )

    _field("latency", f"{elapsed:.1f}s")

    # Grab usage from the bot's internal memory of the last LLM call via
    # its ``llm`` — not exported; fall back gracefully if missing.
    last = getattr(bot.llm, "_last_usage", None)
    in_tokens = last[0] if last else 0
    out_tokens = last[1] if last else 0

    print(f"{BOLD}answer:{RESET}")
    print(_wrap(response.answer))

    if response.suggestions:
        print(f"{BOLD}suggestions:{RESET}")
        for s in response.suggestions:
            print(f"  • {s}")
    else:
        print(f"{DIM}  (no suggestions block extracted){RESET}")

    return in_tokens, out_tokens


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--confirm-cost",
        action="store_true",
        help="Required — acknowledges the script will spend real tokens.",
    )
    p.add_argument(
        "--only",
        nargs="+",
        type=int,
        metavar="N",
        help="Run only the listed case numbers (1-based).",
    )
    return p.parse_args(argv)


def _install_usage_capture() -> None:
    """Monkey-patch LLMService.chat to remember its last token usage.

    Harmless to ship; makes the smoke script show per-turn token counts
    without polluting the production API.
    """
    from backend.services import llm_service as llm_mod

    original = llm_mod.LLMService.chat

    async def wrapper(self, *args, **kwargs):  # type: ignore[no-redef]
        resp = await original(self, *args, **kwargs)
        self._last_usage = (resp.input_tokens, resp.output_tokens)
        return resp

    llm_mod.LLMService.chat = wrapper  # type: ignore[assignment]


async def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    if not args.confirm_cost:
        print(
            f"{YELLOW}{BOLD}This script calls the real LLM and spends tokens.{RESET}\n"
            "Re-run with --confirm-cost if you really want that.\n"
            "Example: PYTHONPATH=. python scripts/smoke_test_bot.py --confirm-cost"
        )
        return 2

    # Only import the app after the confirmation — avoids accidental client
    # instantiation (and env-var complaints) for users who run with `-h`.
    from backend.core.config import settings  # noqa: WPS433 — intentional
    from backend.services.bot_service import BotService  # noqa: WPS433

    if settings.LLM_PROVIDER == "openai" and not settings.OPENAI_API_KEY:
        print(f"{RED}OPENAI_API_KEY is empty in .env — aborting.{RESET}")
        return 1

    _install_usage_capture()

    print(
        f"{DIM}provider={settings.LLM_PROVIDER}  model={settings.LLM_MODEL}  "
        f"temp={settings.LLM_TEMPERATURE}  max_tokens={settings.LLM_MAX_TOKENS}{RESET}"
    )

    bot = BotService()

    cases = CASES
    if args.only:
        idxs = {n - 1 for n in args.only}
        cases = [c for i, c in enumerate(CASES) if i in idxs]
        if not cases:
            print(f"{RED}No cases match --only {args.only}.{RESET}")
            return 1

    total_in = total_out = 0
    for case in cases:
        in_tok, out_tok = await _run_case(bot, case)
        total_in += in_tok
        total_out += out_tok

    _banner("Grand total", colour=GREEN)
    _field("cases run", str(len(cases)))
    _field("input tokens", str(total_in))
    _field("output tokens", str(total_out))
    _field(
        "rough cost (gpt-4o-mini pricing ≈ $0.15/$0.60 per 1M tokens)",
        f"~${(total_in * 0.15 + total_out * 0.60) / 1_000_000:.4f}",
    )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
