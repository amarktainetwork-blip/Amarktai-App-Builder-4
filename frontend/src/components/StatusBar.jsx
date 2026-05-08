import { Cpu, Activity, DollarSign } from "lucide-react";

export default function StatusBar({ project, lastModel, connected }) {
  const tokens = project?.usage?.tokens || 0;
  const cost = project?.usage?.cost_usd || 0;

  return (
    <div data-testid="status-bar" className="h-8 border-t border-emergent-line flex items-center px-4 text-[10px] font-mono text-emergent-fg3 bg-emergent-base justify-between shrink-0">
      <div className="flex items-center gap-4">
        <span className="inline-flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-agent-coder" : "bg-agent-scout"}`} />
          ws: {connected ? "connected" : "offline"}
        </span>
        <span className="hidden sm:inline">project: {project?.id?.slice(0, 8) || "—"}</span>
        <span className="hidden md:inline">status: {project?.status || "—"}</span>
      </div>
      <div className="flex items-center gap-4">
        <span className="inline-flex items-center gap-1">
          <Cpu className="w-3 h-3" strokeWidth={1.5} /> {lastModel || project?.usage?.last_model || "no model yet"}
        </span>
        <span className="inline-flex items-center gap-1">
          <Activity className="w-3 h-3" strokeWidth={1.5} /> tokens: {tokens.toLocaleString()}
        </span>
        <span className="inline-flex items-center gap-1">
          <DollarSign className="w-3 h-3" strokeWidth={1.5} /> {cost.toFixed(4)}
        </span>
      </div>
    </div>
  );
}
