import { useEffect, useState } from "react";
import {
  ChevronDown, ChevronUp, GitBranch, Box, Database, Shield,
  Globe, Cpu, BarChart2, AlertTriangle, CheckCircle, RefreshCw,
} from "lucide-react";
import { Projects } from "@/lib/amk-api";

/**
 * RepoWorkbenchPanel
 *
 * Shows imported-repo analysis results and coverage score.
 *
 * Props:
 *   projectId     – string
 *   project       – project object (must have mode === "repo_fix" or github set)
 *   repoAnalysis  – latest repo profile (from WS event or initial fetch)
 *   coverage      – latest coverage result (from WS event or initial fetch)
 *   onRunPreview  – callback to trigger preview-fallback fetch
 */
export default function RepoWorkbenchPanel({
  projectId,
  project,
  repoAnalysis: analysisOverride,
  coverage: coverageOverride,
  onRunPreview,
  onContinueMissing,
  busy,
}) {
  const [analysis, setAnalysis] = useState(analysisOverride || null);
  const [coverage, setCoverage] = useState(coverageOverride || null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [detailSection, setDetailSection] = useState(null); // "stack" | "commands" | "env" | "routes"

  // Sync when parent receives live events
  useEffect(() => { if (analysisOverride) setAnalysis(analysisOverride); }, [analysisOverride]);
  useEffect(() => { if (coverageOverride) setCoverage(coverageOverride); }, [coverageOverride]);

  // Auto-fetch on mount for imported repos that already have files
  useEffect(() => {
    if (!projectId) return;
    if (project?.mode !== "repo_fix" && !project?.github) return;
    if (analysisOverride && coverageOverride) return; // already provided

    let alive = true;
    setLoading(true);
    Promise.all([
      Projects.repoAnalysis(projectId).catch(() => null),
      Projects.coverage(projectId).catch(() => null),
    ]).then(([a, c]) => {
      if (!alive) return;
      if (a) setAnalysis(a);
      if (c) setCoverage(c);
    }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  if (!analysis && !loading) return null;
  if (project?.mode !== "repo_fix" && !project?.github) return null;

  const covScore = coverage?.coverageScore ?? null;
  const intent = analysis?.detectedUpdateIntent || coverage?.intent || null;
  const covOk = covScore === null || covScore >= 80;

  return (
    <div
      data-testid="repo-workbench-panel"
      className="border-y border-amk-line bg-amk-panel font-mono text-[10px]"
    >
      {/* Header row */}
      <button
        type="button"
        data-testid="repo-workbench-toggle"
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-2 hover:bg-white/5 transition-colors"
      >
        <GitBranch className="w-3 h-3 text-agent-coder shrink-0" strokeWidth={1.5} />
        <span className="uppercase tracking-wider text-agent-coder">Repo Workbench</span>
        {loading && <span className="text-amk-fg3 ml-1">loading…</span>}
        {analysis && (
          <span className="text-amk-fg3 ml-1">
            {analysis.detectedType} · {(analysis.frameworks || []).slice(0, 2).join(", ") || "unknown stack"}
          </span>
        )}
        {covScore !== null && (
          <span
            data-testid="coverage-score-pill"
            className="ml-auto flex items-center gap-1 px-1.5 py-0.5 border border-white/10"
            style={{ color: covOk ? "#00E676" : covScore >= 64 ? "#FFC107" : "#FF5722" }}
          >
            <BarChart2 className="w-2.5 h-2.5" strokeWidth={1.5} />
            Coverage {covScore}/100
          </span>
        )}
        <span className="text-amk-fg3 ml-1">
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </span>
      </button>

      {expanded && analysis && (
        <div className="px-3 pb-3 space-y-3 border-t border-white/10">
          {/* Summary grid */}
          <div className="pt-2 grid grid-cols-2 gap-x-4 gap-y-1">
            <InfoRow icon={<Box className="w-2.5 h-2.5" />} label="Type" value={analysis.detectedType} />
            <InfoRow icon={<Globe className="w-2.5 h-2.5" />} label="Frameworks" value={(analysis.frameworks || []).join(", ") || "—"} />
            <InfoRow icon={<Cpu className="w-2.5 h-2.5" />} label="Languages" value={(analysis.languages || []).slice(0, 3).join(", ") || "—"} />
            <InfoRow icon={<Database className="w-2.5 h-2.5" />} label="Database" value={(analysis.databases || []).join(", ") || "—"} />
            <InfoRow icon={<Shield className="w-2.5 h-2.5" />} label="Auth" value={(analysis.authDetected || []).join(", ") || "—"} />
            <InfoRow icon={<GitBranch className="w-2.5 h-2.5" />} label="Pkg manager" value={analysis.packageManager || "—"} />
            {analysis.frontendPath && (
              <InfoRow icon={null} label="Frontend path" value={analysis.frontendPath} />
            )}
            {analysis.backendPath && (
              <InfoRow icon={null} label="Backend path" value={analysis.backendPath} />
            )}
          </div>

          {/* Preview strategy */}
          {analysis.previewStrategy && (
            <div className="flex items-center gap-1.5">
              <span className="text-amk-fg3">Preview strategy:</span>
              <span className="text-amk-fg">{analysis.previewStrategy}</span>
              {(analysis.previewBlockers || []).length > 0 && (
                <AlertTriangle className="w-2.5 h-2.5 text-agent-scout ml-1" strokeWidth={1.5} />
              )}
            </div>
          )}

          {/* Preview blockers */}
          {(analysis.previewBlockers || []).length > 0 && (
            <div className="space-y-0.5">
              <span className="text-agent-scout uppercase tracking-wider">Preview blockers</span>
              {analysis.previewBlockers.map((b, i) => (
                <div key={i} className="flex items-start gap-1 text-agent-scout">
                  <span className="shrink-0">·</span><span>{b}</span>
                </div>
              ))}
            </div>
          )}

          {/* Coverage detail */}
          {coverage && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <BarChart2 className="w-2.5 h-2.5 shrink-0" strokeWidth={1.5}
                  style={{ color: covOk ? "#00E676" : "#FF5722" }} />
                <span className="uppercase tracking-wider" style={{ color: covOk ? "#00E676" : "#FF5722" }}>
                  Coverage {covScore}/100
                </span>
                {intent && <span className="text-amk-fg3">({intent})</span>}
              </div>
              {/* Score bar */}
              <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${Math.min(covScore ?? 0, 100)}%`,
                    background: covOk ? "#00E676" : covScore >= 64 ? "#FFC107" : "#FF5722",
                  }}
                />
              </div>
              {!covOk && (
                <div className="flex items-start gap-1 text-agent-scout">
                  <AlertTriangle className="w-2.5 h-2.5 mt-0.5 shrink-0" strokeWidth={1.5} />
                  <span>Coverage &lt; 80 — finalize is locked for {intent || "this intent"}.</span>
                </div>
              )}
              {(coverage.missingRequirements || []).length > 0 && (
                <div className="space-y-0.5">
                  <span className="text-amk-fg3">Missing requirements:</span>
                  {coverage.missingRequirements.slice(0, 6).map((m, i) => (
                    <div key={i} className="flex items-start gap-1 text-amk-fg2">
                      <span className="shrink-0">·</span><span>{m}</span>
                    </div>
                  ))}
                  {onContinueMissing && coverage.missingRequirements.length > 0 && (
                    <button
                      type="button"
                      data-testid="continue-missing-requirements-btn"
                      disabled={busy}
                      onClick={() => onContinueMissing(coverage.missingRequirements)}
                      className="mt-1 px-2 py-0.5 border border-agent-coder text-[9px] uppercase tracking-wider text-agent-coder bg-agent-coder/10 hover:bg-agent-coder/20 disabled:opacity-50 transition-colors"
                    >
                      Continue building missing requirements
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Collapsible detail sections */}
          <div className="flex flex-wrap gap-1.5 pt-1">
            {[
              analysis.installCommands?.length && "commands",
              analysis.envRequired?.length && "env",
              analysis.routeMap?.length && "routes",
              analysis.riskNotes?.length && "risks",
            ].filter(Boolean).map((section) => (
              <button
                key={section}
                type="button"
                onClick={() => setDetailSection(detailSection === section ? null : section)}
                className={`px-2 py-0.5 border text-[9px] uppercase tracking-wider transition-colors ${
                  detailSection === section
                    ? "border-agent-coder text-agent-coder bg-agent-coder/10"
                    : "border-amk-line text-amk-fg3 hover:border-amk-fg2"
                }`}
              >
                {section}
              </button>
            ))}
            {onRunPreview && (
              <button
                type="button"
                onClick={onRunPreview}
                className="px-2 py-0.5 border border-amk-line text-[9px] uppercase tracking-wider text-amk-fg3 hover:border-agent-coder hover:text-agent-coder flex items-center gap-1 transition-colors"
              >
                <RefreshCw className="w-2 h-2" strokeWidth={1.5} />
                Run Preview
              </button>
            )}
          </div>

          {detailSection === "commands" && (
            <CommandList
              groups={[
                { label: "Install", cmds: analysis.installCommands },
                { label: "Build", cmds: analysis.buildCommands },
                { label: "Dev", cmds: analysis.devCommands },
                { label: "Test", cmds: analysis.testCommands },
              ]}
            />
          )}
          {detailSection === "env" && analysis.envRequired?.length > 0 && (
            <div className="space-y-0.5">
              <span className="text-amk-fg3 uppercase tracking-wider">Required env vars</span>
              <div className="flex flex-wrap gap-1 pt-0.5">
                {analysis.envRequired.map((e, i) => (
                  <span key={i} className="px-1.5 py-0.5 bg-amk-surface border border-amk-line text-amk-fg2">
                    {e}
                  </span>
                ))}
              </div>
            </div>
          )}
          {detailSection === "routes" && analysis.routeMap?.length > 0 && (
            <div className="space-y-0.5">
              <span className="text-amk-fg3 uppercase tracking-wider">Detected routes</span>
              {analysis.routeMap.slice(0, 20).map((r, i) => (
                <div key={i} className="text-amk-fg2 flex items-start gap-1">
                  <span className="shrink-0">·</span><code>{r}</code>
                </div>
              ))}
            </div>
          )}
          {detailSection === "risks" && analysis.riskNotes?.length > 0 && (
            <div className="space-y-0.5">
              <span className="text-agent-scout uppercase tracking-wider">Risk notes</span>
              {analysis.riskNotes.map((r, i) => (
                <div key={i} className="flex items-start gap-1 text-agent-scout">
                  <span className="shrink-0">·</span><span>{r}</span>
                </div>
              ))}
            </div>
          )}

          {/* Recommended plan */}
          {analysis.recommendedPlan && (
            <div className="text-amk-fg3 pt-1 border-t border-white/5">
              <span className="text-amk-fg2">Recommended plan: </span>
              {analysis.recommendedPlan}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function InfoRow({ icon, label, value }) {
  if (!value) return null;
  return (
    <div className="flex items-center gap-1 min-w-0">
      {icon && <span className="text-amk-fg3 shrink-0">{icon}</span>}
      <span className="text-amk-fg3 shrink-0">{label}:</span>
      <span className="text-amk-fg truncate">{value}</span>
    </div>
  );
}

function CommandList({ groups }) {
  return (
    <div className="space-y-1">
      {groups.filter((g) => g.cmds?.length).map(({ label, cmds }) => (
        <div key={label} className="space-y-0.5">
          <span className="text-amk-fg3 uppercase tracking-wider">{label}</span>
          {cmds.map((cmd, i) => (
            <code key={i} className="block bg-amk-surface border border-amk-line px-2 py-0.5 text-amk-fg">
              {cmd}
            </code>
          ))}
        </div>
      ))}
    </div>
  );
}
