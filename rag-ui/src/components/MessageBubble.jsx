import { Sparkles } from "lucide-react";

export default function MessageBubble({ role, content, time }) {
  const isUser = role === "user";

  return (
    <div className={`flex animate-slide-up gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {!isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-signal-400 to-pulse-500">
          <Sparkles size={13} className="text-ink-950" strokeWidth={2.5} />
        </div>
      )}

      <div className={`flex max-w-[75%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed shadow-bubble ${
            isUser
              ? "rounded-tr-sm bg-gradient-to-br from-signal-500 to-signal-600 text-white"
              : "rounded-tl-sm border border-mist-200 bg-white text-ink-900"
          }`}
        >
          {content}
        </div>
        <span className="mt-1 px-1 text-[11px] text-ink-600/70">{time}</span>
      </div>
    </div>
  );
}
