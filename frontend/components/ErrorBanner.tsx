"use client";

import { AlertTriangle, X } from "lucide-react";

import { useConversationMeta } from "./ConversationRuntime";

/**
 * Thin warning banner shown when the last POST /api/v1/chat failed. The
 * error message itself is appended to the assistant bubble too, but the
 * banner makes the failure unmissable and surfaces common backend-down
 * issues (ECONNREFUSED, 502, etc.) early.
 */
export function ErrorBanner() {
  const { lastError } = useConversationMeta();

  if (!lastError) return null;

  return (
    <div className="flex items-start gap-2 border-b border-amber-300 bg-amber-50 px-6 py-2 text-xs text-amber-900">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">
        <strong className="mr-1 font-semibold">Backend error:</strong>
        <span className="font-mono">{lastError}</span>
      </div>
      <X className="mt-0.5 h-4 w-4 shrink-0 opacity-50" aria-hidden />
    </div>
  );
}
