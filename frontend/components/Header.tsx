"use client";

import { Home, RotateCcw, Sparkles } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/cn";
import { useConversationMeta } from "./ConversationRuntime";

export function Header() {
  const { isThinking, sessionId, resetSession } = useConversationMeta();

  return (
    <header className="flex items-center justify-between border-b border-ink-200 bg-white px-6 py-4 shadow-elev-1">
      {/* Logo block is now a Link → takes the user back to the landing. */}
      <Link
        href="/"
        className="group flex items-center gap-3 transition"
        aria-label="Volver al inicio"
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-500 text-white transition group-hover:bg-brand-600">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-ink-900 transition group-hover:text-brand-700">
            Rappi Data Bot
          </h1>
          <p className="text-xs text-ink-500">
            Consultá métricas operativas de 9 mercados LATAM en lenguaje
            natural
          </p>
        </div>
      </Link>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-xs text-ink-500">
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              isThinking ? "animate-pulse bg-brand-500" : "bg-emerald-500",
            )}
            aria-hidden
          />
          <span>{isThinking ? "Procesando…" : "Listo"}</span>
        </div>

        <Link
          href="/"
          className="flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-brand-400 hover:text-brand-600"
          title="Volver al inicio"
        >
          <Home className="h-3.5 w-3.5" />
          Inicio
        </Link>

        <button
          type="button"
          onClick={resetSession}
          className="flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-brand-400 hover:text-brand-600"
          // Title is populated only after hydration (sessionId starts null
          // on the server to avoid a localStorage-based SSR mismatch).
          title={sessionId ? `Session: ${sessionId}` : undefined}
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Nueva conversación
        </button>
      </div>
    </header>
  );
}
