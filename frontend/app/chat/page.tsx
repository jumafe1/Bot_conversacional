import { ConversationRuntime } from "@/components/ConversationRuntime";
import { ErrorBanner } from "@/components/ErrorBanner";
import { Header } from "@/components/Header";
import { SuggestionsStrip } from "@/components/SuggestionsStrip";
import { ChatThread } from "@/components/Thread";
import { ToolsUsedBadge } from "@/components/ToolsUsedBadge";

export default function ChatPage() {
  return (
    <ConversationRuntime>
      <main className="flex h-screen w-full flex-col">
        <Header />
        <ErrorBanner />

        <section className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <ChatThread />
          </div>
          <ToolsUsedBadge />
          <SuggestionsStrip />
        </section>
      </main>
    </ConversationRuntime>
  );
}
