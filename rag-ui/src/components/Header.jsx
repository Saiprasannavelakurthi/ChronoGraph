import { Menu, Circle, Waypoints } from "lucide-react";

export default function Header({ title, onToggleSidebar, onToggleGraph, graphOpen }) {
  return (
    <header className="flex items-center justify-between border-b border-mist-200 bg-white/80 px-4 py-3.5 backdrop-blur">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="rounded-md p-1.5 text-ink-700 transition-colors hover:bg-mist-100 md:hidden"
        >
          <Menu size={18} />
        </button>
        <div>
          <h1 className="font-display text-[15px] font-semibold text-ink-950">{title}</h1>
          <div className="flex items-center gap-1.5 text-xs text-ink-600">
            <Circle size={7} className="fill-pulse-500 text-pulse-500" />
            ChronoGraph is online
          </div>
        </div>
      </div>

      <button
        onClick={onToggleGraph}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
          graphOpen
            ? "border-signal-500/40 bg-signal-500/10 text-signal-600"
            : "border-mist-200 text-ink-700 hover:bg-mist-100"
        }`}
      >
        <Waypoints size={14} />
        <span className="hidden sm:inline">{graphOpen ? "Hide graph" : "View graph"}</span>
      </button>
    </header>
  );
}
