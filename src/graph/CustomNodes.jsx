import { Handle, Position } from "reactflow";
import { Clock3 } from "lucide-react";

export function TurnNode({ data }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-signal-600/40 bg-gradient-to-br from-signal-500 to-signal-600 px-3 py-1.5 text-white shadow-bubble">
      <Handle type="target" position={Position.Left} id="spine-in" className="!h-2 !w-2 !border-0 !bg-signal-600" />
      <Clock3 size={12} strokeWidth={2.5} />
      <div className="flex flex-col leading-tight">
        <span className="text-[10px] font-semibold">{data.label}</span>
        <span className="text-[9px] text-white/70">{data.time}</span>
      </div>
      <Handle type="source" position={Position.Right} id="spine-out" className="!h-2 !w-2 !border-0 !bg-signal-600" />
      <Handle type="source" position={Position.Bottom} id="entity-out" className="!h-2 !w-2 !border-0 !bg-signal-600" />
    </div>
  );
}

export function EntityNode({ data }) {
  return (
    <div className="rounded-lg border border-mist-300 bg-white px-2.5 py-1 text-[11px] font-medium text-ink-800 shadow-bubble">
      <Handle type="target" position={Position.Top} id="entity-in" className="!h-2 !w-2 !border-0 !bg-pulse-500" />
      {data.label}
    </div>
  );
}

export const nodeTypes = { turnNode: TurnNode, entityNode: EntityNode };
