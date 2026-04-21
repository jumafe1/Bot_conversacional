"use client";

/**
 * Opinionated chat thread built on the assistant-ui primitive API.
 *
 * We compose the primitives directly (rather than using the packaged
 * `Thread` component) so the styling matches the rest of the app and we
 * can render markdown with our own Tailwind typography settings.
 */

import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type TextMessagePartComponent,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import { Bot, Send, User } from "lucide-react";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";

const WELCOME_MESSAGE =
  "Hola 👋 Soy el bot de datos de Rappi. Preguntame sobre métricas " +
  "operativas (Perfect Orders, Lead Penetration, Gross Profit UE, etc.), " +
  "filtrá por país, ciudad o zona, o pedime comparaciones y tendencias.";

const STARTER_PROMPTS = [
  "Top 5 zonas por Perfect Orders en Colombia",
  "Comparar Perfect Orders: Wealthy vs Non Wealthy en México",
  "Gross Profit UE promedio por país",
  "Tendencia de Lead Penetration en CO últimas 8 semanas",
];

export function ChatThread() {
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col bg-white">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-6 py-6">
        <ThreadPrimitive.Empty>
          <WelcomeScreen />
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            AssistantMessage,
          }}
        />
      </ThreadPrimitive.Viewport>

      <Composer />
    </ThreadPrimitive.Root>
  );
}

function WelcomeScreen() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center py-12 text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-500 text-white shadow-elev-2">
        <Bot className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold text-ink-900">
        ¿Qué querés analizar hoy?
      </h2>
      <p className="mt-2 max-w-md text-sm text-ink-600">{WELCOME_MESSAGE}</p>

      <div className="mt-6 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {STARTER_PROMPTS.map((prompt) => (
          <StarterPrompt key={prompt} text={prompt} />
        ))}
      </div>
    </div>
  );
}

function StarterPrompt({ text }: { text: string }) {
  return (
    <ThreadPrimitive.Suggestion
      prompt={text}
      method="replace"
      autoSend
      className="rounded-lg border border-ink-200 bg-ink-50 px-4 py-3 text-left text-sm text-ink-700 transition hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700"
    >
      {text}
    </ThreadPrimitive.Suggestion>
  );
}

// ---------------------------------------------------------------------------
// Message bubbles
// ---------------------------------------------------------------------------

function UserMessage() {
  return (
    <MessagePrimitive.Root className="mx-auto mb-4 flex w-full max-w-3xl gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-100 text-ink-700">
        <User className="h-4 w-4" />
      </div>
      <div className="flex-1 rounded-2xl rounded-tl-sm bg-ink-100 px-4 py-2.5 text-sm text-ink-900">
        <MessagePrimitive.Content
          components={{ Text: PlainText }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="mx-auto mb-4 flex w-full max-w-3xl gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-500 text-white">
        <Bot className="h-4 w-4" />
      </div>
      <div
        className={cn(
          "aui-md flex-1 rounded-2xl rounded-tl-sm bg-white px-4 py-3 text-sm text-ink-900",
          "prose prose-sm max-w-none prose-p:my-1 prose-table:my-2 prose-headings:font-semibold",
          "ring-1 ring-ink-200/60",
        )}
      >
        <MessagePrimitive.Content
          components={{ Text: MarkdownText }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

// ---------------------------------------------------------------------------
// Content renderers
// ---------------------------------------------------------------------------

// Plain text (user bubble) — just renders the `text` field of the part.
const PlainText: TextMessagePartComponent = ({ text }) => (
  <span className="whitespace-pre-wrap">{text}</span>
);

// Markdown text (assistant bubble) — MarkdownTextPrimitive reads the text
// from assistant-ui context, so we don't pass it explicitly.
const MarkdownText: TextMessagePartComponent = () => (
  <MarkdownTextPrimitive remarkPlugins={[remarkGfm]} />
);

// ---------------------------------------------------------------------------
// Composer (input + send)
// ---------------------------------------------------------------------------

function Composer() {
  return (
    <ComposerPrimitive.Root className="flex items-end gap-2 border-t border-ink-200 bg-white px-6 py-4">
      <ComposerPrimitive.Input
        placeholder="Ej: top 10 zonas por Perfect Orders en México..."
        rows={1}
        autoFocus
        className={cn(
          "flex-1 resize-none rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-sm text-ink-900 shadow-sm",
          "placeholder:text-ink-400 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200",
        )}
      />
      <ComposerPrimitive.Send
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500 text-white shadow-elev-1 transition",
          "hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40",
        )}
      >
        <Send className="h-4 w-4" />
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  );
}
