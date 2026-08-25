import ReactFlow, { Background, BackgroundVariant, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { Waypoints, X } from "lucide-react";
import { nodeTypes } from "../graph/CustomNodes.jsx";

export default function GraphPanel({ nodes, edges, isOpen, onClose, apiConnected }) {
  return (
    <aside
      className={`${
        isOpen ? "translate-x-0" : "translate-x-full"
      } fixed inset-y-0 right-0 z-30 flex w-full flex-col border-l border-mist-200 bg-white transition-transform duration-200 ease-out sm:w-[380px] md:static md:w-[380px] md:shrink-0 md:translate-x-0 ${
        isOpen ? "" : "md:hidden"
      }`}
    >
      <div className="flex items-center justify-between border-b border-mist-200 px-4 py-3.5">
        <div className="flex items-center gap-2">
          <Waypoints size={16} className="text-signal-600" />
          <div>
            <div className="flex items-center gap-1.5">
              <h2 className="font-display text-[14px] font-semibold text-ink-950">ChronoGraph</h2>
              {apiConnected ? (
                <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-700">Live</span>
              ) : (
                <span className="rounded-full bg-mist-200 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-ink-500">Simulated</span>
              )}
            </div>
            <p className="text-[11px] text-ink-600">
              {apiConnected ? "Real graph-ready triples from data-ingestion" : "Chat entities extracted per turn (API offline)"}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-ink-600 transition-colors hover:bg-mist-100 md:hidden"
          aria-label="Close graph panel"
        >
          <X size={16} />
        </button>
      </div>

      {nodes.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-8 text-center text-sm leading-relaxed text-ink-600">
          Send a message — each exchange adds a node to the timeline, with
          related entities branching off it.
        </div>
      ) : (
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.35 }}
            proOptions={{ hideAttribution: true }}
            minZoom={0.3}
            maxZoom={1.5}
            nodesDraggable={false}
            nodesConnectable={false}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#E3E6EE" />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>
        </div>
      )}
    </aside>
  );
}
