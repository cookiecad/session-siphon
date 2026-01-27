import type { Message } from "@/lib/typesense";

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  return (
    <div
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[80%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white"
            : isAssistant
              ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
              : "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700"
        }`}
      >
        <div className="mb-1 text-xs font-medium opacity-70">
          {message.role}
        </div>
        <div className="whitespace-pre-wrap break-words font-mono text-sm">
          {message.content}
        </div>
      </div>
    </div>
  );
}
