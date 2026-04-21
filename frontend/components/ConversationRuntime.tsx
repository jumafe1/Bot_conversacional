"use client";

/**
 * assistant-ui runtime wired to the FastAPI `/api/v1/chat` endpoint.
 *
 * Why a custom adapter? The backend is a request-response API (not a
 * streaming SSE endpoint) and it returns structured metadata (suggestions,
 * tool_calls_used) that we want to surface outside the chat bubble.
 *
 * Design:
 *   - Each user turn → one POST to /api/v1/chat with the stable session_id
 *     from localStorage.
 *   - On response, we return the `answer` text to assistant-ui so it
 *     appears as the assistant message.
 *   - We also publish `suggestions` and `tool_calls_used` on a React
 *     context so sibling components (SuggestionsStrip, ToolsUsedBadge)
 *     can render them without threading props through the runtime.
 */

import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  type ChatModelAdapter,
  type ThreadMessage,
} from "@assistant-ui/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ChatApiError, postChat } from "@/lib/api";
import { getOrCreateSessionId, resetSessionId } from "@/lib/session";

interface ConversationMeta {
  suggestions: string[];
  toolsUsed: string[];
  /** ``null`` until the client has hydrated and read localStorage. */
  sessionId: string | null;
  lastError: string | null;
  isThinking: boolean;
  resetSession: () => void;
}

const ConversationMetaContext = createContext<ConversationMeta | null>(null);

export function useConversationMeta(): ConversationMeta {
  const ctx = useContext(ConversationMetaContext);
  if (!ctx) {
    throw new Error(
      "useConversationMeta must be used inside <ConversationRuntime>.",
    );
  }
  return ctx;
}

function extractUserText(message: ThreadMessage): string {
  // Users message content is an array of blocks (text, image, etc.).
  // We only send text to the Python backend; other modalities aren't
  // supported yet, so we silently drop them.
  if (!("content" in message) || !Array.isArray(message.content)) return "";
  return message.content
    .filter((block): block is { type: "text"; text: string } =>
      block.type === "text",
    )
    .map((block) => block.text)
    .join("\n")
    .trim();
}

export function ConversationRuntime({
  children,
}: {
  children: React.ReactNode;
}) {
  // Start as ``null`` so server-rendered HTML matches the first client
  // render (localStorage is only readable after hydration). The real id is
  // populated in the effect below, before React commits any user
  // interaction handlers.
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [toolsUsed, setToolsUsed] = useState<string[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);

  useEffect(() => {
    setSessionId(getOrCreateSessionId());
  }, []);

  // Ref mirror so the adapter closure sees the latest id without having
  // to re-subscribe the runtime on every state change.
  const sessionIdRef = useRef<string | null>(sessionId);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const adapter: ChatModelAdapter = useMemo(
    () => ({
      async run({ messages, abortSignal }) {
        const lastUser = [...messages]
          .reverse()
          .find((m) => m.role === "user");
        const userText = lastUser ? extractUserText(lastUser) : "";

        if (!userText) {
          return {
            content: [
              {
                type: "text",
                text: "No recibí un mensaje válido. Probá escribir de nuevo.",
              },
            ],
          };
        }

        setIsThinking(true);
        setLastError(null);

        // Fallback if the user somehow submits before the mount effect
        // populated the id (extremely rare — requires sending a message
        // during the first paint). Keeps the backend from seeing an empty
        // session id.
        const effectiveSessionId =
          sessionIdRef.current ?? getOrCreateSessionId();

        try {
          const data = await postChat(
            {
              session_id: effectiveSessionId,
              message: userText,
            },
            { signal: abortSignal },
          );

          setSuggestions(data.suggestions ?? []);
          setToolsUsed(data.tool_calls_used ?? []);

          return {
            content: [{ type: "text", text: data.answer }],
          };
        } catch (error) {
          const message =
            error instanceof ChatApiError
              ? `${error.status}: ${error.detail ?? error.message}`
              : error instanceof Error
                ? error.message
                : "Unknown error";
          setLastError(message);
          setSuggestions([]);
          setToolsUsed([]);
          return {
            content: [
              {
                type: "text",
                text:
                  `⚠️ No pude completar la consulta (${message}). ` +
                  "Revisá que el backend esté corriendo en " +
                  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") +
                  " y probá de nuevo.",
              },
            ],
          };
        } finally {
          setIsThinking(false);
        }
      },
    }),
    [],
  );

  const runtime = useLocalRuntime(adapter);

  const resetSession = useCallback(() => {
    const fresh = resetSessionId();
    setSessionId(fresh);
    setSuggestions([]);
    setToolsUsed([]);
    setLastError(null);
  }, []);

  const metaValue = useMemo<ConversationMeta>(
    () => ({
      suggestions,
      toolsUsed,
      sessionId,
      lastError,
      isThinking,
      resetSession,
    }),
    [suggestions, toolsUsed, sessionId, lastError, isThinking, resetSession],
  );

  return (
    <ConversationMetaContext.Provider value={metaValue}>
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </ConversationMetaContext.Provider>
  );
}
