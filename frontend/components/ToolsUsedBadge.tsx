"use client";

import { Wrench } from "lucide-react";

import { useConversationMeta } from "./ConversationRuntime";

/**
 * Tiny observability strip: shows which tools the LLM invoked for the
 * latest answer. Useful during demos to make the "function calling"
 * architecture legible to stakeholders.
 */
export function ToolsUsedBadge() {
  const { toolsUsed } = useConversationMeta();

  if (!toolsUsed.length) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-6 py-2 text-[11px] text-ink-500">
      <Wrench className="h-3 w-3" />
      <span className="font-medium text-ink-600">Herramientas consultadas:</span>
      {toolsUsed.map((tool, i) => (
        <span
          key={`${tool}-${i}`}
          className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[10px] text-ink-700"
        >
          {tool}
        </span>
      ))}
    </div>
  );
}
