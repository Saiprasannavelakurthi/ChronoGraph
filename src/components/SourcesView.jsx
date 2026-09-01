import { Slack, Github, Quote } from "lucide-react";

function SourceDetailCard({ source }) {
  const isSlack = source.type === "slack";

  return (
    <div className="rounded-xl border border-signal-500/30 bg-signal-500/[0.04] p-4">
      <div className="flex items-center gap-2">
        <div
          className={`flex h-7 w-7 items-center justify-center rounded-lg ${
            isSlack ? "bg-[#4A154B]" : "bg-ink-950"
          }`}
        >
          {isSlack ? (
            <Slack size={13} className="text-white" />
          ) : (
            <Github size={13} className="text-white" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold text-ink-950">
            {isSlack ? source.channel : `${source.repo} · PR #${source.number}`}
          </p>
          <p className="text-[11px] text-ink-600">
            {source.author} · {source.time}
          </p>
        </div>
      </div>

      {!isSlack && (
        <p className="mt-2.5 text-[13px] font-medium text-ink-900">{source.title}</p>
      )}

      <div className="mt-2.5 flex gap-2 rounded-lg bg-white px-3 py-2.5">
        <Quote size={13} className="mt-0.5 shrink-0 text-signal-500" />
        <p className="text-[12.5px] leading-relaxed text-ink-800">{source.excerpt}</p>
      </div>

      <p className="mt-2.5 text-[10.5px] text-ink-600">
        This is the exact passage the answer was grounded in.
      </p>
    </div>
  );
}

function SourceListRow({ source, isActive, onSelect }) {
  const isSlack = source.type === "slack";
  return (
    <button
      onClick={() => onSelect(source.id)}
      className={`flex w-full items-start gap-2 rounded-lg border px-3 py-2 text-left transition-colors ${
        isActive ? "border-signal-500/40 bg-signal-500/5" : "border-mist-200 bg-white hover:bg-mist-50"
      }`}
    >
      {isSlack ? (
        <Slack size={13} className="mt-0.5 shrink-0 text-[#4A154B]" />
      ) : (
        <Github size={13} className="mt-0.5 shrink-0 text-ink-900" />
      )}
      <div className="min-w-0">
        <p className="truncate text-[12px] font-medium text-ink-900">
          {isSlack ? source.channel : `${source.repo} #${source.number}`}
        </p>
        <p className="truncate text-[11px] text-ink-600">
          {isSlack ? source.excerpt : source.title}
        </p>
      </div>
    </button>
  );
}

export default function SourcesView({ citedSources, activeSourceId, onSelectSource }) {
  if (citedSources.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-8 text-center text-sm leading-relaxed text-ink-600">
        Ask about the auth refactor, onboarding emails, or the flaky Cypress
        test — cited Slack messages and PRs will show up here.
      </div>
    );
  }

  const active = citedSources.find((s) => s.id === activeSourceId) ?? citedSources[citedSources.length - 1];

  return (
    <div className="scroll-thin flex-1 space-y-4 overflow-y-auto p-4">
      <div>
        <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-600">
          Selected source
        </p>
        <SourceDetailCard source={active} />
      </div>

      <div>
        <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-600">
          Cited this conversation ({citedSources.length})
        </p>
        <div className="space-y-1.5">
          {citedSources.map((s) => (
            <SourceListRow
              key={s.id}
              source={s}
              isActive={active.id === s.id}
              onSelect={onSelectSource}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
