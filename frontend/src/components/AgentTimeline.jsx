import { AGENTS, AGENT_ORDER } from "@/lib/agents";
import { Check, Loader2 } from "lucide-react";

/**
 * Vertical stepped agent timeline. Highlights the active agent with a colored
 * left border + pulse, completed agents get a check, idle agents are muted.
 */
export default function AgentTimeline({ events }) {
  // Compute current state per agent from event stream.
  const stateByAgent = {};
  for (const e of events) {
    if (!stateByAgent[e.agent]) stateByAgent[e.agent] = {};
    stateByAgent[e.agent].latest = e.status;
    if (e.status === "completed") stateByAgent[e.agent].completed = true;
    if (e.status === "started") stateByAgent[e.agent].started = true;
  }

  return (
    <div data-testid="agent-timeline" className="border-b border-amk-line">
      <div className="px-4 pt-3 pb-2 flex items-center justify-between">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-amk-fg3">
          Agent Pipeline
        </span>
        <span className="font-mono text-[10px] text-amk-fg3">
          {AGENT_ORDER.filter((a) => stateByAgent[a]?.completed).length}/{AGENT_ORDER.length}
        </span>
      </div>
      <ol className="px-3 pb-3 space-y-1">
        {AGENT_ORDER.map((id) => {
          const meta = AGENTS[id];
          const st = stateByAgent[id] || {};
          const isActive = st.started && !st.completed;
          const isDone = st.completed;
          return (
            <li
              key={id}
              data-testid={`agent-row-${id}`}
              className={`flex items-center gap-3 px-3 py-2 border-l-2 ${
                isActive ? "bg-amk-panel" : ""
              }`}
              style={{ borderLeftColor: isActive || isDone ? meta.color : "transparent" }}
            >
              <div className="w-5 grid place-items-center">
                {isActive ? (
                  <span className="pulse-dot" style={{ background: meta.color }} />
                ) : isDone ? (
                  <Check className="w-3.5 h-3.5" strokeWidth={2} style={{ color: meta.color }} />
                ) : (
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-amk-line"
                    aria-hidden
                  />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between">
                  <span
                    className="font-mono text-xs tracking-tight"
                    style={{ color: isActive || isDone ? meta.color : "#71717A" }}
                  >
                    {meta.label.toUpperCase()}
                  </span>
                  <span className="font-mono text-[10px] text-amk-fg3 uppercase tracking-wider">
                    {meta.role}
                  </span>
                </div>
                <div className="font-mono text-[10px] text-amk-fg3 mt-0.5">
                  {isActive ? <span className="ascii-loader"><span className="ascii-dots" /></span>
                    : isDone ? "complete"
                    : "idle"}
                </div>
              </div>
              {isActive && <Loader2 className="w-3 h-3 animate-spin" style={{ color: meta.color }} />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
