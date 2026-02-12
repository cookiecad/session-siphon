import { getConversationById, getConversationMessages } from "@/lib/typesense";
import { MessageBubble } from "@/components/MessageBubble";
import Link from "next/link";

interface ConversationPageProps {
  params: Promise<{ id: string }>;
}

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function formatSource(source: string): string {
  const sourceNames: Record<string, string> = {
    claude_code: "Claude Code",
    codex: "Codex",
    vscode_copilot: "VS Code Copilot",
    gemini_cli: "Gemini CLI",
  };
  return sourceNames[source] || source;
}

/**
 * Extract the Claude Code session UUID from a raw_path.
 * Main sessions: .../projects/<encoded-path>/<session-uuid>.jsonl
 * Subagents: .../projects/<encoded-path>/<session-uuid>/subagents/<agent-id>.jsonl
 */
function extractClaudeSessionId(rawPath: string, conversationId: string): string {
  const subagentMatch = rawPath.match(
    /\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/subagents\//
  );
  if (subagentMatch) {
    return subagentMatch[1];
  }
  // For main sessions, the conversation_id is already the UUID
  return conversationId;
}

function getSessionId(source: string, conversationId: string, rawPath: string): string | null {
  switch (source) {
    case "claude_code":
      return extractClaudeSessionId(rawPath, conversationId);
    default:
      return conversationId;
  }
}

function getResumeHint(source: string, sessionId: string): string | null {
  switch (source) {
    case "claude_code":
      return `claude --resume ${sessionId}`;
    case "codex":
      return `codex --resume ${sessionId}`;
    case "gemini_cli":
      return `gemini --session ${sessionId}`;
    default:
      return null;
  }
}

export default async function ConversationPage({
  params,
}: ConversationPageProps) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);

  // The URL id is the composite document ID (e.g., "claude_code:p16:agent-a3f6a2b")
  // Look up the conversation to get the actual conversation_id field
  const conversation = await getConversationById(decodedId);
  const conversationId = conversation?.conversation_id ?? decodedId;

  const results = await getConversationMessages(conversationId, { perPage: 250 });
  const messages = results.hits.map((hit) => hit.document);

  if (messages.length === 0) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-black">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Conversation not found
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            No messages found for this conversation ID.
          </p>
          <Link
            href="/"
            className="mt-4 inline-block text-blue-600 hover:underline dark:text-blue-400"
          >
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  const firstMessage = messages[0];
  const lastMessage = messages[messages.length - 1];
  const sessionId = getSessionId(firstMessage.source, conversationId, firstMessage.raw_path);
  const resumeHint = sessionId ? getResumeHint(firstMessage.source, sessionId) : null;

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-black">
      <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white px-4 py-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
              &larr; Back
            </Link>
            <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              Conversation
            </h1>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm text-zinc-600 dark:text-zinc-400">
            <div>
              <span className="font-medium">Source:</span>{" "}
              {formatSource(firstMessage.source)}
            </div>
            {sessionId && (
              <div>
                <span className="font-medium">Session:</span>{" "}
                <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs dark:bg-zinc-800">
                  {sessionId}
                </code>
              </div>
            )}
            <div>
              <span className="font-medium">Machine:</span>{" "}
              <span className="font-mono text-xs">{firstMessage.machine_id}</span>
            </div>
            <div>
              <span className="font-medium">Project:</span>{" "}
              <span className="font-mono text-xs">{firstMessage.project}</span>
            </div>
            <div>
              <span className="font-medium">Started:</span>{" "}
              {formatTimestamp(firstMessage.ts)}
            </div>
            <div>
              <span className="font-medium">Last message:</span>{" "}
              {formatTimestamp(lastMessage.ts)}
            </div>
            <div>
              <span className="font-medium">Messages:</span> {messages.length}
            </div>
          </div>
          {resumeHint && (
            <div className="mt-2 text-xs text-zinc-500 dark:text-zinc-500">
              Resume:{" "}
              <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono dark:bg-zinc-800">
                {resumeHint}
              </code>
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-4 py-6">
          <div className="flex flex-col gap-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
