import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";
import TypingIndicator from "./TypingIndicator.jsx";

const SUGGESTIONS = [
  "Summarize this thread",
  "Draft a follow-up email",
  "Explain this error message",
  "Give me three headline ideas",
];

export default function ChatWindow({ messages, isTyping, onSuggestion }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isTyping]);

  return (
    <div className="scroll-thin flex-1 overflow-y-auto px-4 py-6 md:px-8">
      <div className="mx-auto flex max-w-2xl flex-col gap-5">
        {messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} time={m.time} />
        ))}

        {isTyping && <TypingIndicator />}

        {messages.length === 1 && !isTyping && (
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => onSuggestion(s)}
                className="rounded-xl border border-mist-200 bg-white px-4 py-3 text-left text-sm text-ink-800 shadow-bubble transition-colors hover:border-signal-500/40 hover:bg-mist-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
