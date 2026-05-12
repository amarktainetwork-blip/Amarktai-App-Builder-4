import { AGENTS, AGENT_ORDER } from "@/lib/agents";
import { Check, Loader2, AlertTriangle, SkipForward } from "lucide-react";

/**
 * Vertical stepped agent pipeline timeline.
 * Shows: active agent (pulse), completed (check), failed (warning), skipped, idle.
 * Displays the latest event detail text and elapsed time for active/completed agents.
 */
export default function AgentTimeline({ events }) {
  const stateByAgent = {};

  for (const e of events) {
    if (!stateByAgent[e.agent]) stateByAgent[e.agent] = {};
    const s = stateByAgent[e.agent];
    s.latest = e.status;
    s.latestDetail = e.detail || "";
    if (e.status === "started") {
      s.started = true;
      s.startedAt = e.created_at;
    }
    if (e.status === "completed" || e.status === "repaired") {
      s.completed = true;
      s.completedAt = e.created_at;
    }
    if (e.status === "failed") s.failed = true;
    if (e.status === "skipped") s.skipped = true;
  }

  const completedCount = AGENT_ORDER.filter((a) => stateByAgent[a]?.completed).length;
  const hasActive = AGENT_ORDER.some((a) => stateByAgent[a]?.started && !stateByAgent[a]?.completed && !stateByAgent[a]?.failed);

  return (
    <div data-testid="agent-timeline" className="border-b border-amk-line">
      <div className="px-4 pt-3 pb-2 flex items-center justify-between">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-amk-fg3">
          Build Pipeline
        </span>
        <span className="font-mono text-[10px] text-amk-fg3 flex items-center gap-1.5">
          {hasActive && (
            <span className="inline-flex items-center gap-1 text-[#00E676]">
              <span className="pulse-dot bg-[#00E676]" style={{ width: 5, height: 5 }} />
              live
            </span>
          )}
          <span>{completedCount}/{AGENT_ORDER.length}</span>
        </span>
      </div>

      <ol className="px-3 pb-3 space-y-1">
        {AGENT_ORDER.map((id) => {
          const meta = AGENTS[id];
          const st = stateByAgent[id] || {};
          const isActive = st.started && !st.completed && !st.failed && !st.skipped;
          const isDone = st.completed;
          const isFailed = st.failed && !st.completed;
          const isSkipped = st.skipped && !st.completed;

          const accentColor = isFailed ? "#FF5722" : isSkipped ? "#71717A" : meta.color;
          const statusText = isFailed
            ? "failed"
            : isSkipped
            ? "skipped"
            : isDone
            ? "complete"
            : isActive
            ? st.latest === "thinking" ? "thinking…" : st.latest === "repairing" ? "repairing…" : "working…"
            : "idle";

          return (
            <li
              key={id}
              data-testid={`agent-row-${id}`}
              className={`flex items-start gap-3 px-3 py-2 border-l-2 transition-all duration-300 ${
                isActive ? "bg-amk-panel" : ""
              }`}
              style={{
                borderLeftColor:
                  isActive || isDone || isFailed || isSkipped ? accentColor : "transparent",
              }}
            >
              <div className="w-5 mt-0.5 grid place-items-center shrink-0">
                {isActive ? (
                  <span className="pulse-dot" style={{ background: accentColor }} />
                ) : isDone ? (
                  <Check className="w-3.5 h-3.5" strokeWidth={2.5} style={{ color: accentColor }} />
                ) : isFailed ? (
                  <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} style={{ color: accentColor }} />
                ) : isSkipped ? (
                  <SkipForward className="w-3.5 h-3.5" strokeWidth={1.5} style={{ color: accentColor }} />
                ) : (
                  <span className="w-1.5 h-1.5 rounded-full bg-amk-line" aria-hidden />
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span
                    className="font-mono text-xs tracking-tight leading-none"
                    style={{ color: isActive || isDone || isFailed ? accentColor : "#52525B" }}
                  >
                    {meta.label.toUpperCase()}
                  </span>
                  <span className="font-mono text-[9px] text-amk-fg3 uppercase tracking-wider shrink-0">
                    {meta.role}
                  </span>
                </div>

                <div className="flex items-center justify-between mt-0.5">
                  <span className="font-mono text-[10px] text-amk-fg3">
                    {isActive ? (
                      <span className="flex items-center gap-1">
                        <Loader2 className="w-2.5 h-2.5 animate-spin inline" style={{ color: accentColor }} />
                        {statusText}
                      </span>
                    ) : (
                      statusText
                    )}
                  </span>
                </div>

                {/* Latest detail text for active or recently completed */}
                {(isActive || isDone) && st.latestDetail && (
                  <div
                    className="font-mono text-[9px] mt-1 leading-relaxed truncate"
                    style={{ color: isActive ? accentColor : "#52525B", opacity: isActive ? 0.9 : 0.6 }}
                    title={st.latestDetail}
                  >
                    {st.latestDetail}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
