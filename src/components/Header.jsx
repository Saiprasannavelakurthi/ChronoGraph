import { Menu, Circle } from "lucide-react";

export default function Header({ title, onToggleSidebar }) {
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
            Nimbus is online
          </div>
        </div>
      </div>
    </header>
  );
}
