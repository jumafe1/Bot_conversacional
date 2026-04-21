"use client";

import { useComposerRuntime } from "@assistant-ui/react";
import { Lightbulb } from "lucide-react";

import { useConversationMeta } from "./ConversationRuntime";

/**
 * Pills with the LLM's follow-up suggestions. Clicking one inserts it into
 * the composer and submits immediately — saves the user a round of typing
 * and steers them toward questions the bot can actually answer.
 */
export function SuggestionsStrip() {
  const { suggestions, isThinking } = useConversationMeta();
  const composer = useComposerRuntime();

  if (!suggestions.length || isThinking) return null;

  const send = (text: string) => {
    // The assistant-ui composer API: set text, then trigger send.
    composer.setText(text);
    composer.send();
  };

  return (
    <div className="border-t border-ink-100 bg-ink-50/60 px-6 py-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-500">
        <Lightbulb className="h-3.5 w-3.5" />
        Análisis sugerido
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => send(s)}
            className="group max-w-full truncate rounded-full border border-ink-200 bg-white px-3 py-1.5 text-xs text-ink-700 shadow-elev-1 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700"
            title={s}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
