import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  TrendingUp,
  DollarSign,
  Search,
  Layers,
  AlertCircle,
  Zap,
  ArrowRight,
  Star,
} from "lucide-react";

/**
 * AdvisorPanel
 *
 * Phase 2: AI Product Advisor panel. Displays after build completes.
 * Shows improvement suggestions, quick wins, weak UX patterns, SEO,
 * monetization, and scaling suggestions from the advisor agent.
 *
 * Props:
 *   advisor – object from project.advisor_result
 */
export default function AdvisorPanel({ advisor }) {
  const [expanded, setExpanded] = useState(false);

  if (!advisor) return null;

  const {
    overall_rating = "Good",
    summary = "",
    priority_action = "",
    quick_wins = [],
    weak_ux_patterns = [],
    ux_improvements = [],
    conversion_improvements = [],
    monetization_suggestions = [],
    seo_suggestions = [],
    scaling_suggestions = [],
  } = advisor;

  const ratingColor =
    overall_rating === "Excellent"
      ? "#00E676"
      : overall_rating === "Good"
      ? "#00BCD4"
      : overall_rating === "Fair"
      ? "#FFC107"
      : "#FF5722";

  return (
    <div
      data-testid="advisor-panel"
      className="border-y border-[#00BCD4]/30 bg-[#00BCD4]/5 font-mono text-[10px]"
    >
      {/* Summary row */}
      <button
        type="button"
        data-testid="advisor-panel-toggle"
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-3 hover:bg-white/5 transition-colors"
      >
        <span className="text-[#00BCD4] uppercase tracking-wider flex items-center gap-1.5">
          <Star className="w-3 h-3" strokeWidth={1.5} />
          product advisor
        </span>
        <span
          className="px-1.5 py-0.5 border border-white/10 uppercase tracking-wider"
          style={{ color: ratingColor }}
        >
          {overall_rating}
        </span>
        {priority_action && (
          <span className="text-amk-fg3 truncate flex-1 hidden sm:block">
            {priority_action}
          </span>
        )}
        <span className="ml-auto text-amk-fg3 shrink-0">
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </span>
      </button>

      {/* Detail panel */}
      {expanded && (
        <div
          data-testid="advisor-detail"
          className="px-3 pb-4 space-y-4 border-t border-white/10"
        >
          {/* Summary */}
          {summary && (
            <p className="pt-3 text-amk-fg2 leading-relaxed">{summary}</p>
          )}

          {/* Priority action */}
          {priority_action && (
            <div className="flex items-start gap-2 bg-[#00BCD4]/10 border border-[#00BCD4]/20 px-3 py-2 rounded">
              <ArrowRight className="w-3 h-3 mt-0.5 text-[#00BCD4] shrink-0" strokeWidth={2} />
              <div>
                <span className="text-[#00BCD4] uppercase tracking-wider mr-2">Priority action:</span>
                <span className="text-amk-fg">{priority_action}</span>
              </div>
            </div>
          )}

          {/* Grid of suggestion categories */}
          <div className="grid grid-cols-2 gap-4">
            {quick_wins.length > 0 && (
              <SuggestionGroup
                icon={<Zap className="w-3 h-3" strokeWidth={1.5} />}
                label="Quick Wins"
                color="#00E676"
                items={quick_wins}
              />
            )}
            {weak_ux_patterns.length > 0 && (
              <SuggestionGroup
                icon={<AlertCircle className="w-3 h-3" strokeWidth={1.5} />}
                label="Weak UX Patterns"
                color="#FFC107"
                items={weak_ux_patterns}
              />
            )}
            {ux_improvements.length > 0 && (
              <SuggestionGroup
                icon={<Layers className="w-3 h-3" strokeWidth={1.5} />}
                label="UX Improvements"
                color="#00BCD4"
                items={ux_improvements}
              />
            )}
            {conversion_improvements.length > 0 && (
              <SuggestionGroup
                icon={<TrendingUp className="w-3 h-3" strokeWidth={1.5} />}
                label="Conversion"
                color="#9C27B0"
                items={conversion_improvements}
              />
            )}
            {monetization_suggestions.length > 0 && (
              <SuggestionGroup
                icon={<DollarSign className="w-3 h-3" strokeWidth={1.5} />}
                label="Monetization"
                color="#FF9800"
                items={monetization_suggestions}
              />
            )}
            {seo_suggestions.length > 0 && (
              <SuggestionGroup
                icon={<Search className="w-3 h-3" strokeWidth={1.5} />}
                label="SEO"
                color="#2962FF"
                items={seo_suggestions}
              />
            )}
          </div>

          {scaling_suggestions.length > 0 && (
            <SuggestionGroup
              icon={<Layers className="w-3 h-3" strokeWidth={1.5} />}
              label="Scaling"
              color="#71717A"
              items={scaling_suggestions}
              horizontal
            />
          )}
        </div>
      )}
    </div>
  );
}

function SuggestionGroup({ icon, label, color, items, horizontal = false }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 uppercase tracking-wider" style={{ color }}>
        {icon}
        {label}
      </div>
      <ul className={horizontal ? "flex flex-wrap gap-x-4 gap-y-1" : "space-y-1"}>
        {items.slice(0, 4).map((item, i) => (
          <li key={i} className="flex items-start gap-1 text-amk-fg3">
            <span className="shrink-0" style={{ color }}>·</span>
            <span className="leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
