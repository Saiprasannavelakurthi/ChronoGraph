import { Sparkles } from "lucide-react";

export default function TypingIndicator() {
  return (
    <div className="flex animate-slide-up gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-signal-400 to-pulse-500">
        <Sparkles size={13} className="text-ink-950" strokeWidth={2.5} />
      </div>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-mist-200 bg-white px-4 py-3 shadow-bubble">
        <span className="h-1.5 w-1.5 animate-dot-bounce rounded-full bg-ink-600 [animation-delay:-0.24s]" />
        <span className="h-1.5 w-1.5 animate-dot-bounce rounded-full bg-ink-600 [animation-delay:-0.12s]" />
        <span className="h-1.5 w-1.5 animate-dot-bounce rounded-full bg-ink-600" />
      </div>
    </div>
  );
}
