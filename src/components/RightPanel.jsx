import { Waypoints, Quote, X } from "lucide-react";
import SubgraphView from "./SubgraphView.jsx";
import SourcesView from "./SourcesView.jsx";

const TABS = [
  { id: "timeline", label: "Timeline", icon: Waypoints },
  { id: "sources", label: "Sources", icon: Quote },
];

export default function RightPanel({
  isOpen,
  onClose,
  activeTab,
  onTabChange,
  graphNodes,
  graphEdges,
  citedSources,
  activeSourceId,
  onSelectSource,
}) {
  return (
    <aside
      className={`${
        isOpen ? "translate-x-0" : "translate-x-full"
      } fixed inset-y-0 right-0 z-30 flex w-full flex-col border-l border-mist-200 bg-white transition-transform duration-200 ease-out sm:w-[380px] md:static md:w-[380px] md:shrink-0 md:translate-x-0 ${
        isOpen ? "" : "md:hidden"
      }`}
    >
      <div className="flex items-center justify-between border-b border-mist-200 px-3 py-2.5">
        <div className="flex gap-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-signal-500/10 text-signal-600"
                    : "text-ink-600 hover:bg-mist-100 hover:text-ink-800"
                }`}
              >
                <Icon size={13} />
                {tab.label}
                {tab.id === "sources" && citedSources.length > 0 && (
                  <span
                    className={`flex h-3.5 min-w-[14px] items-center justify-center rounded-full px-1 text-[9px] font-semibold ${
                      isActive ? "bg-signal-600 text-white" : "bg-mist-200 text-ink-700"
                    }`}
                  >
                    {citedSources.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-ink-600 transition-colors hover:bg-mist-100 md:hidden"
          aria-label="Close panel"
        >
          <X size={16} />
        </button>
      </div>

      {activeTab === "timeline" ? (
        <SubgraphView nodes={graphNodes} edges={graphEdges} />
      ) : (
        <SourcesView
          citedSources={citedSources}
          activeSourceId={activeSourceId}
          onSelectSource={onSelectSource}
        />
      )}
    </aside>
  );
}
