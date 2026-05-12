import { ShieldCheck, ShieldAlert, Paintbrush, Star, AlertTriangle, ChevronDown, ChevronUp, TrendingUp, Accessibility, Search, Smartphone, Zap, Users } from "lucide-react";
import { useState } from "react";

/**
 * ValidationPanel
 *
 * Shows quality/design/security scores and errors in the workspace.
 * Shown when project has a validation result attached.
 *
 * Props:
 *   validation – object from project.last_validation (qualityScore, designScore,
 *                securityScore, qualityOk, designOk, securityOk, canFinalize,
 *                qualityErrors, designErrors, securityErrors, designDirection,
 *                conversionScore, uxScore, accessibilityScore, seoScore,
 *                responsivenessScore, performanceScore + matching error arrays)
 */
export default function ValidationPanel({ validation }) {
  const [expanded, setExpanded] = useState(false);

  if (!validation) return null;

  const {
    qualityScore = 0,
    designScore = 0,
    securityScore = 0,
    qualityOk,
    designOk,
    securityOk,
    canFinalize,
    qualityErrors = [],
    designErrors = [],
    securityErrors = [],
    designDirection,
    contentStats,
    // Phase 3: extended scores
    conversionScore = 0,
    uxScore = 0,
    accessibilityScore = 0,
    seoScore = 0,
    responsivenessScore = 0,
    performanceScore = 0,
    conversionErrors = [],
    uxErrors = [],
    accessibilityErrors = [],
    seoErrors = [],
    responsivenessErrors = [],
    performanceErrors = [],
  } = validation;

  const allOk = qualityOk && designOk && securityOk;

  return (
    <div
      data-testid="validation-panel"
      className={`border-y font-mono text-[10px] ${
        canFinalize
          ? "border-agent-coder/40 bg-agent-coder/5"
          : "border-agent-scout/40 bg-agent-scout/5"
      }`}
    >
      {/* Summary row */}
      <button
        type="button"
        data-testid="validation-panel-toggle"
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-3 hover:bg-white/5 transition-colors"
      >
        <span className={`uppercase tracking-wider ${canFinalize ? "text-agent-coder" : "text-agent-scout"}`}>
          {canFinalize ? "✓ validation passed" : "⚠ validation"}
        </span>
        <ScorePill label="Quality" score={qualityScore} ok={qualityOk} threshold={75} />
        <ScorePill label="Design" score={designScore} ok={designOk} threshold={70} />
        <ScorePill label="Security" score={securityScore} ok={securityOk} threshold={75} />
        <span className="ml-auto text-amk-fg3">
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </span>
      </button>

      {/* Detail panel */}
      {expanded && (
        <div data-testid="validation-detail" className="px-3 pb-3 space-y-3 border-t border-white/10">
          {/* Core scores */}
          <div className="pt-3 grid grid-cols-3 gap-3">
            <ScoreDetail
              label="Quality"
              score={qualityScore}
              ok={qualityOk}
              icon={<Star className="w-3 h-3" strokeWidth={1.5} />}
              errors={qualityErrors}
              threshold={75}
            />
            <ScoreDetail
              label="Design"
              score={designScore}
              ok={designOk}
              icon={<Paintbrush className="w-3 h-3" strokeWidth={1.5} />}
              errors={designErrors}
              threshold={70}
            />
            <ScoreDetail
              label="Security"
              score={securityScore}
              ok={securityOk}
              icon={securityOk ? <ShieldCheck className="w-3 h-3" strokeWidth={1.5} /> : <ShieldAlert className="w-3 h-3" strokeWidth={1.5} />}
              errors={securityErrors}
              threshold={75}
            />
          </div>

          {/* Phase 3: Extended scores */}
          {(conversionScore > 0 || uxScore > 0 || seoScore > 0) && (
            <>
              <div className="text-amk-fg3 uppercase tracking-wider pt-1">Product Scores</div>
              <div className="grid grid-cols-3 gap-3">
                <ScoreDetail
                  label="Conversion"
                  score={conversionScore}
                  ok={conversionScore >= 70}
                  icon={<TrendingUp className="w-3 h-3" strokeWidth={1.5} />}
                  errors={conversionErrors}
                  threshold={70}
                />
                <ScoreDetail
                  label="UX"
                  score={uxScore}
                  ok={uxScore >= 70}
                  icon={<Users className="w-3 h-3" strokeWidth={1.5} />}
                  errors={uxErrors}
                  threshold={70}
                />
                <ScoreDetail
                  label="Accessibility"
                  score={accessibilityScore}
                  ok={accessibilityScore >= 70}
                  icon={<Accessibility className="w-3 h-3" strokeWidth={1.5} />}
                  errors={accessibilityErrors}
                  threshold={70}
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <ScoreDetail
                  label="SEO"
                  score={seoScore}
                  ok={seoScore >= 70}
                  icon={<Search className="w-3 h-3" strokeWidth={1.5} />}
                  errors={seoErrors}
                  threshold={70}
                />
                <ScoreDetail
                  label="Responsive"
                  score={responsivenessScore}
                  ok={responsivenessScore >= 70}
                  icon={<Smartphone className="w-3 h-3" strokeWidth={1.5} />}
                  errors={responsivenessErrors}
                  threshold={70}
                />
                <ScoreDetail
                  label="Performance"
                  score={performanceScore}
                  ok={performanceScore >= 60}
                  icon={<Zap className="w-3 h-3" strokeWidth={1.5} />}
                  errors={performanceErrors}
                  threshold={60}
                />
              </div>
            </>
          )}

          {/* Design direction */}
          {designDirection && (
            <div className="text-amk-fg3">
              <span className="text-amk-fg2">Design direction:</span>{" "}
              <span className="text-amk-fg">{typeof designDirection === "object" ? designDirection.name || designDirection.label || JSON.stringify(designDirection) : designDirection}</span>
            </div>
          )}

          {/* Content stats */}
          {contentStats && (
            <div className="text-amk-fg3">
              {Object.entries(contentStats).map(([k, v]) => (
                <span key={k} className="mr-3">
                  {k}: <span className="text-amk-fg">{String(v)}</span>
                </span>
              ))}
            </div>
          )}

          {/* Finalize gate status */}
          {!canFinalize && (
            <div className="flex items-start gap-1.5 text-agent-scout">
              <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" strokeWidth={1.5} />
              <span>
                Finalize is locked. Quality ≥ 75, Design ≥ 70 and Security ≥ 75 required when security/auth present.
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ScorePill({ label, score, ok, threshold }) {
  const pct = Math.round(score);
  const color = ok ? "#00E676" : score >= threshold * 0.85 ? "#FFC107" : "#FF5722";
  return (
    <span
      data-testid={`score-pill-${label.toLowerCase()}`}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 border border-white/10"
      style={{ color }}
    >
      {label} {pct}
    </span>
  );
}

function ScoreDetail({ label, score, ok, icon, errors, threshold }) {
  const pct = Math.round(score);
  const color = ok ? "#00E676" : score >= threshold * 0.85 ? "#FFC107" : "#FF5722";
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5" style={{ color }}>
        {icon}
        <span className="uppercase tracking-wider">{label}</span>
        <span className="ml-auto font-bold">{pct}</span>
      </div>
      {/* Score bar */}
      <div className="h-1 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(pct, 100)}%`, background: color }}
        />
      </div>
      {/* Errors */}
      {errors.length > 0 && (
        <ul className="space-y-0.5 pt-1">
          {errors.slice(0, 3).map((e, i) => (
            <li key={i} className="text-agent-scout flex items-start gap-1">
              <span className="shrink-0">·</span>
              <span className="line-clamp-2">{e}</span>
            </li>
          ))}
          {errors.length > 3 && (
            <li className="text-amk-fg3">+{errors.length - 3} more</li>
          )}
        </ul>
      )}
    </div>
  );
}


/**
 * ValidationPanel
 *
 * Shows quality/design/security scores and errors in the workspace.
 * Shown when project has a validation result attached.
 *
 * Props:
 *   validation – object from project.last_validation (qualityScore, designScore,
 *                securityScore, qualityOk, designOk, securityOk, canFinalize,
 *                qualityErrors, designErrors, securityErrors, designDirection)
 */
export default function ValidationPanel({ validation }) {
  const [expanded, setExpanded] = useState(false);

  if (!validation) return null;

  const {
    qualityScore = 0,
    designScore = 0,
    securityScore = 0,
    qualityOk,
    designOk,
    securityOk,
    canFinalize,
    qualityErrors = [],
    designErrors = [],
    securityErrors = [],
    designDirection,
    contentStats,
  } = validation;

  const allOk = qualityOk && designOk && securityOk;

  return (
    <div
      data-testid="validation-panel"
      className={`border-y font-mono text-[10px] ${
        canFinalize
          ? "border-agent-coder/40 bg-agent-coder/5"
          : "border-agent-scout/40 bg-agent-scout/5"
      }`}
    >
      {/* Summary row */}
      <button
        type="button"
        data-testid="validation-panel-toggle"
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-3 hover:bg-white/5 transition-colors"
      >
        <span className={`uppercase tracking-wider ${canFinalize ? "text-agent-coder" : "text-agent-scout"}`}>
          {canFinalize ? "✓ validation passed" : "⚠ validation"}
        </span>
        <ScorePill label="Quality" score={qualityScore} ok={qualityOk} threshold={75} />
        <ScorePill label="Design" score={designScore} ok={designOk} threshold={70} />
        <ScorePill label="Security" score={securityScore} ok={securityOk} threshold={75} />
        <span className="ml-auto text-amk-fg3">
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </span>
      </button>

      {/* Detail panel */}
      {expanded && (
        <div data-testid="validation-detail" className="px-3 pb-3 space-y-3 border-t border-white/10">
          {/* Score breakdown */}
          <div className="pt-3 grid grid-cols-3 gap-3">
            <ScoreDetail
              label="Quality"
              score={qualityScore}
              ok={qualityOk}
              icon={<Star className="w-3 h-3" strokeWidth={1.5} />}
              errors={qualityErrors}
              threshold={75}
            />
            <ScoreDetail
              label="Design"
              score={designScore}
              ok={designOk}
              icon={<Paintbrush className="w-3 h-3" strokeWidth={1.5} />}
              errors={designErrors}
              threshold={70}
            />
            <ScoreDetail
              label="Security"
              score={securityScore}
              ok={securityOk}
              icon={securityOk ? <ShieldCheck className="w-3 h-3" strokeWidth={1.5} /> : <ShieldAlert className="w-3 h-3" strokeWidth={1.5} />}
              errors={securityErrors}
              threshold={75}
            />
          </div>

          {/* Design direction */}
          {designDirection && (
            <div className="text-amk-fg3">
              <span className="text-amk-fg2">Design direction:</span>{" "}
              <span className="text-amk-fg">{typeof designDirection === "object" ? designDirection.name || designDirection.label || JSON.stringify(designDirection) : designDirection}</span>
            </div>
          )}

          {/* Content stats */}
          {contentStats && (
            <div className="text-amk-fg3">
              {Object.entries(contentStats).map(([k, v]) => (
                <span key={k} className="mr-3">
                  {k}: <span className="text-amk-fg">{String(v)}</span>
                </span>
              ))}
            </div>
          )}

          {/* Finalize gate status */}
          {!canFinalize && (
            <div className="flex items-start gap-1.5 text-agent-scout">
              <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" strokeWidth={1.5} />
              <span>
                Finalize is locked. Quality ≥ 75, Design ≥ 70 and Security ≥ 75 required when security/auth present.
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ScorePill({ label, score, ok, threshold }) {
  const pct = Math.round(score);
  const color = ok ? "#00E676" : score >= threshold * 0.85 ? "#FFC107" : "#FF5722";
  return (
    <span
      data-testid={`score-pill-${label.toLowerCase()}`}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 border border-white/10"
      style={{ color }}
    >
      {label} {pct}
    </span>
  );
}

function ScoreDetail({ label, score, ok, icon, errors, threshold }) {
  const pct = Math.round(score);
  const color = ok ? "#00E676" : score >= threshold * 0.85 ? "#FFC107" : "#FF5722";
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5" style={{ color }}>
        {icon}
        <span className="uppercase tracking-wider">{label}</span>
        <span className="ml-auto font-bold">{pct}</span>
      </div>
      {/* Score bar */}
      <div className="h-1 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.min(pct, 100)}%`, background: color }}
        />
      </div>
      {/* Errors */}
      {errors.length > 0 && (
        <ul className="space-y-0.5 pt-1">
          {errors.slice(0, 3).map((e, i) => (
            <li key={i} className="text-agent-scout flex items-start gap-1">
              <span className="shrink-0">·</span>
              <span className="line-clamp-2">{e}</span>
            </li>
          ))}
          {errors.length > 3 && (
            <li className="text-amk-fg3">+{errors.length - 3} more</li>
          )}
        </ul>
      )}
    </div>
  );
}
