import { Slack, Github } from "lucide-react";

export default function SourceChip({ source, isActive, onSelect }) {
  if (!source) return null;
  const isSlack = source.type === "slack";

  return (
    <button
      onClick={() => onSelect(source.id)}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        isActive
          ? "border-signal-500/50 bg-signal-500/10 text-signal-600"
          : "border-mist-200 bg-white text-ink-700 hover:bg-mist-50"
      }`}
    >
      {isSlack ? (
        <Slack size={11} className="shrink-0" />
      ) : (
        <Github size={11} className="shrink-0" />
      )}
      <span className="max-w-[140px] truncate">
        {isSlack ? source.channel : `${source.repo} #${source.number}`}
      </span>
    </button>
  );
}
