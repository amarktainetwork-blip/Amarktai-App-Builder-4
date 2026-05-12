import { Layers, FileCode2, Eye, EyeOff, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

/**
 * BuildPlanBanner
 *
 * Phase 4: Smart Build Planning. Shows the estimated build plan before
 * agents start coding. Collapses by default; shown as a soft banner.
 *
 * Props:
 *   plan – object from build_plan event
 */
export default function BuildPlanBanner({ plan }) {
  const [expanded, setExpanded] = useState(false);

  if (!plan) return null;

  const {
    complexity = "Moderate",
    estimated_pages = 0,
    estimated_files = 0,
    recommended_stack = "",
    can_preview = true,
    preview_note = "",
    missing_apis = [],
    build_phases = [],
    key_risks = [],
    estimated_quality = "Good",
    plan_summary = "",
  } = plan;

  const complexityColor =
    complexity === "Simple"
      ? "#00E676"
      : complexity === "Moderate"
      ? "#00BCD4"
      : complexity === "Complex"
      ? "#FFC107"
      : "#FF5722";

  return (
    <div
      data-testid="build-plan-banner"
      className="border-b border-[#9C27B0]/30 bg-[#9C27B0]/5 font-mono text-[10px]"
    >
      <button
        type="button"
        data-testid="build-plan-toggle"
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-3 hover:bg-white/5 transition-colors text-left"
      >
        <span className="text-[#9C27B0] uppercase tracking-wider flex items-center gap-1.5">
          <Layers className="w-3 h-3" strokeWidth={1.5} />
          build plan
        </span>
        <span style={{ color: complexityColor }} className="uppercase tracking-wider">
          {complexity}
        </span>
        <span className="text-amk-fg3 flex items-center gap-1">
          <FileCode2 className="w-2.5 h-2.5" strokeWidth={1.5} />
          {estimated_pages}p · {estimated_files}f
        </span>
        {can_preview ? (
          <span className="text-[#00E676] flex items-center gap-1">
            <Eye className="w-2.5 h-2.5" strokeWidth={1.5} />
            preview
          </span>
        ) : (
          <span className="text-amk-fg3 flex items-center gap-1">
            <EyeOff className="w-2.5 h-2.5" strokeWidth={1.5} />
            no preview
          </span>
        )}
        <span className="ml-auto text-amk-fg3 shrink-0">
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </span>
      </button>

      {expanded && (
        <div
          data-testid="build-plan-detail"
          className="px-3 pb-4 space-y-3 border-t border-white/10"
        >
          {plan_summary && (
            <p className="pt-3 text-amk-fg2 leading-relaxed">{plan_summary}</p>
          )}

          <div className="grid grid-cols-2 gap-4">
            {/* Stack */}
            {recommended_stack && (
              <div className="space-y-1">
                <div className="text-[#9C27B0] uppercase tracking-wider">Stack</div>
                <div className="text-amk-fg3">{recommended_stack}</div>
              </div>
            )}

            {/* Estimated quality */}
            {estimated_quality && (
              <div className="space-y-1">
                <div className="text-[#9C27B0] uppercase tracking-wider">Expected Quality</div>
                <div className="text-amk-fg3 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-[#00E676]" strokeWidth={1.5} />
                  {estimated_quality}
                </div>
              </div>
            )}
          </div>

          {/* Build phases */}
          {build_phases.length > 0 && (
            <div className="space-y-1">
              <div className="text-[#9C27B0] uppercase tracking-wider mb-1.5">Phases</div>
              <ol className="space-y-1">
                {build_phases.map((phase, i) => (
                  <li key={i} className="flex items-start gap-2 text-amk-fg3">
                    <span className="shrink-0 text-[#9C27B0]">{i + 1}.</span>
                    <span>{phase}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Missing APIs */}
          {missing_apis.length > 0 && (
            <div className="space-y-1">
              <div className="text-[#FFC107] uppercase tracking-wider flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" strokeWidth={1.5} />
                APIs to simulate
              </div>
              <ul className="flex flex-wrap gap-2">
                {missing_apis.map((api, i) => (
                  <li
                    key={i}
                    className="px-2 py-0.5 border border-[#FFC107]/30 text-[#FFC107]/70 rounded"
                  >
                    {api}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Key risks */}
          {key_risks.length > 0 && (
            <div className="space-y-1">
              <div className="text-amk-fg3 uppercase tracking-wider">Risks</div>
              <ul className="space-y-0.5">
                {key_risks.map((risk, i) => (
                  <li key={i} className="flex items-start gap-1 text-amk-fg3">
                    <span className="shrink-0 text-[#FF5722]">·</span>
                    {risk}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
