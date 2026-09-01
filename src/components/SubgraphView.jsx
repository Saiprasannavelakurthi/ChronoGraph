import ReactFlow, { Background, BackgroundVariant, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { nodeTypes } from "../graph/CustomNodes.jsx";

export default function SubgraphView({ nodes, edges }) {
  if (nodes.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-8 text-center text-sm leading-relaxed text-ink-600">
        Send a message — each exchange adds a node to the timeline, with
        related entities branching off it.
      </div>
    );
  }

  return (
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
  );
}
