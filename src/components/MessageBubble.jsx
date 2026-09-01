import { Sparkles, CornerDownRight } from "lucide-react";
import CitationBadge from "./CitationBadge.jsx";
import SourceChip from "./SourceChip.jsx";
import { getSource } from "../data/sources.js";

// Splits "...shared middleware [1], with tests [2]." into text chunks and
// citation markers so [n] can be rendered as a clickable badge tied to
// citedSourceIds[n-1].
function renderContent(content, citedSourceIds, activeSourceId, onSelectSource) {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return <span key={i}>{part}</span>;

    const index = Number(match[1]) - 1;
    const sourceId = citedSourceIds?.[index];
    if (!sourceId) return <span key={i}>{part}</span>;

    return (
      <CitationBadge
        key={i}
        number={match[1]}
        sourceId={sourceId}
        isActive={activeSourceId === sourceId}
        onSelect={onSelectSource}
      />
    );
  });
}

export default function MessageBubble({ role, content, time, citedSourceIds, suggestions, onSuggestionClick, activeSourceId, onSelectSource, isFollowUp, topicLabel }) {
  const isUser = role === "user";
  const uniqueSourceIds = [...new Set(citedSourceIds ?? [])];

  return (
    <div className={`flex animate-slide-up gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {!isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-signal-400 to-pulse-500">
          <Sparkles size={13} className="text-ink-950" strokeWidth={2.5} />
        </div>
      )}

      <div className={`flex max-w-[75%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        {!isUser && isFollowUp && topicLabel && (
          <div className="mb-1 flex items-center gap-1 px-1 text-[10.5px] font-medium text-ink-600/80">
            <CornerDownRight size={11} className="text-signal-500" />
            Continuing: {topicLabel}
          </div>
        )}

        <div
          className={`rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed shadow-bubble ${
            isUser
              ? "rounded-tr-sm bg-gradient-to-br from-signal-500 to-signal-600 text-white"
              : "rounded-tl-sm border border-mist-200 bg-white text-ink-900"
          }`}
        >
          {isUser ? content : renderContent(content, citedSourceIds, activeSourceId, onSelectSource)}
        </div>

        {!isUser && suggestions?.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5 px-1">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => onSuggestionClick(s)}
                className="rounded-full border border-signal-500/30 bg-signal-500/5 px-2.5 py-1 text-[11px] font-medium text-signal-600 transition-colors hover:bg-signal-500/15"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {!isUser && uniqueSourceIds.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5 px-1">
            {uniqueSourceIds.map((id) => (
              <SourceChip
                key={id}
                source={getSource(id)}
                isActive={activeSourceId === id}
                onSelect={onSelectSource}
              />
            ))}
          </div>
        )}

        <span className="mt-1 px-1 text-[11px] text-ink-600/70">{time}</span>
      </div>
    </div>
  );
}
