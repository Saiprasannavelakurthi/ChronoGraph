import { Plus, MessageSquare, Settings, Sparkles } from "lucide-react";

export default function Sidebar({ conversations, activeId, onSelect, onNewChat, isOpen }) {
  return (
    <aside
      className={`${
        isOpen ? "translate-x-0" : "-translate-x-full"
      } fixed inset-y-0 left-0 z-30 flex w-72 flex-col bg-ink-950 text-mist-100 transition-transform duration-200 ease-out md:static md:translate-x-0`}
    >
      {/* Brand */}
      <div className="flex items-center gap-2 px-5 pb-4 pt-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-signal-400 to-pulse-500">
          <Sparkles size={16} className="text-ink-950" strokeWidth={2.5} />
        </div>
        <span className="font-display text-[15px] font-semibold tracking-tight">ChronoGraph</span>
      </div>

      {/* New chat */}
      <div className="px-3">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-lg border border-ink-700 bg-ink-900 px-3 py-2.5 text-sm font-medium text-mist-100 transition-colors hover:border-signal-500/50 hover:bg-ink-800"
        >
          <Plus size={16} />
          New chat
        </button>
      </div>

      {/* Conversation list */}
      <nav className="scroll-thin mt-4 flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
        <p className="px-2 pb-2 pt-2 text-[11px] font-semibold uppercase tracking-wider text-ink-600">
          Recent
        </p>
        {conversations.map((c) => (
          <button
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={`group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-left text-sm transition-colors ${
              activeId === c.id
                ? "bg-ink-800 text-mist-50"
                : "text-mist-300 hover:bg-ink-900 hover:text-mist-100"
            }`}
          >
            <MessageSquare
              size={15}
              className={activeId === c.id ? "text-signal-400" : "text-ink-600 group-hover:text-ink-600"}
            />
            <span className="flex-1 truncate">{c.title}</span>
            <span className="shrink-0 text-[11px] text-ink-600">{c.timestamp}</span>
          </button>
        ))}
       </nav>
    </aside>
  );
}
