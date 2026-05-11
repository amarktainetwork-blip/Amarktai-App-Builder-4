import { useEffect, useState } from "react";
import { Projects } from "@/lib/amk-api";
import { RefreshCw, ExternalLink, Cpu, AlertTriangle, Loader2, BookOpen, Wrench, CheckCircle, Terminal } from "lucide-react";

// Modes that show repo structure instead of an iframe
const REPO_STRUCTURE_MODES = new Set([
  "full_stack", "dashboard", "admin_panel", "api_service",
  "automation_bot", "trading_bot_scaffold", "repo_fix",
]);

export default function LivePreview({ projectId, refreshKey, projectStatus, projectError, failedAgent, projectMode, previewStrategy, buildPhase, previewFallback }) {
  const [bust, setBust] = useState(0);
  // NOTE: The preview URL contains a bearer token as a query parameter for iframe auth.
  // TODO: Move to a short-lived preview token or use a dedicated preview origin to reduce
  //       token exposure in browser history and server logs.
  const url = `${Projects.previewUrl(projectId)}&v=${refreshKey || 0}-${bust}`;

  useEffect(() => { setBust((b) => b + 1); }, [refreshKey]);

  const isFailed = projectStatus === "failed" || projectStatus === "cancelled";
  const isRunning = projectStatus === "running" || projectStatus === "queued";
  const showRepoStructure = previewStrategy === "repo_structure"
    || (projectMode && REPO_STRUCTURE_MODES.has(projectMode));

  if (isFailed) {
    return (
      <div data-testid="live-preview" className="h-full flex flex-col">
        <div className="h-9 border-b border-amk-line bg-amk-base flex items-center px-3 shrink-0">
          <Cpu className="w-3.5 h-3.5 text-amk-fg3 mr-2" strokeWidth={1.5} />
          <span className="font-mono text-[11px] text-amk-fg">
            {showRepoStructure ? "Repo Structure" : "Live Preview"}
          </span>
        </div>
        <div className="flex-1 bg-amk-panel flex items-center justify-center p-6">
          <div className="border border-amk-line rounded-md bg-amk-base p-6 max-w-md text-center space-y-3">
            <AlertTriangle className="w-8 h-8 text-red-400 mx-auto" />
            <p className="font-mono text-[13px] text-amk-fg font-semibold">
              {projectStatus === "cancelled" ? "Build Cancelled" : "Build Failed"}
            </p>
            {failedAgent && (
              <p className="font-mono text-[11px] text-amk-fg3">
                Failed agent: <span className="text-red-400">{failedAgent}</span>
              </p>
            )}
            {projectError && (
              <p className="font-mono text-[11px] text-amk-fg2 break-words">{projectError}</p>
            )}
            <p className="font-mono text-[11px] text-amk-fg3">
              No preview files were generated because the build failed.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (isRunning) {
    const isValidating = buildPhase === "validating";
    const isRepairing = buildPhase === "repairing";
    let phaseMsg = showRepoStructure
      ? "Repo structure will appear when agents finish generating files."
      : "Preview will appear when files are generated.";
    let PhaseIcon = Loader2;
    let spinning = true;
    if (isValidating) {
      phaseMsg = "Validating generated app…";
      PhaseIcon = CheckCircle;
      spinning = false;
    } else if (isRepairing) {
      phaseMsg = "Repairing generated app…";
      PhaseIcon = Wrench;
      spinning = false;
    }
    return (
      <div data-testid="live-preview" className="h-full flex flex-col">
        <div className="h-9 border-b border-amk-line bg-amk-base flex items-center px-3 shrink-0">
          <Cpu className="w-3.5 h-3.5 text-amk-fg3 mr-2" strokeWidth={1.5} />
          <span className="font-mono text-[11px] text-amk-fg">
            {showRepoStructure ? "Repo Structure" : "Live Preview"}
          </span>
        </div>
        <div className="flex-1 bg-amk-panel flex items-center justify-center">
          <div className="border border-amk-line rounded-md bg-amk-base p-6 max-w-md text-center space-y-3">
            <PhaseIcon className={`w-7 h-7 text-amk-fg3 mx-auto${spinning ? " animate-spin" : ""}`} />
            <p className="font-mono text-[12px] text-amk-fg2">{phaseMsg}</p>
          </div>
        </div>
      </div>
    );
  }

  // Phase 3: Show preview fallback when it exists and no live preview is possible
  if (previewFallback && !previewFallback.canPreview) {
    return <PreviewFallbackPanel fallback={previewFallback} />;
  }

  if (showRepoStructure) {
    return (
      <div data-testid="live-preview" className="h-full flex flex-col">
        <div className="h-9 border-b border-amk-line bg-amk-base flex items-center px-3 shrink-0">
          <BookOpen className="w-3.5 h-3.5 text-amk-fg3 mr-2" strokeWidth={1.5} />
          <span className="font-mono text-[11px] text-amk-fg">Repo Structure</span>
          <span className="font-mono text-[10px] text-amk-fg3 uppercase ml-2">
            view README and files in the Code tab
          </span>
        </div>
        <div className="flex-1 bg-amk-panel flex items-center justify-center p-6">
          <div className="border border-amk-line bg-amk-base p-6 max-w-md text-center space-y-3">
            <BookOpen className="w-7 h-7 text-amk-fg3 mx-auto" />
            <p className="font-mono text-[12px] text-amk-fg">
              {(projectMode || "").replace(/_/g, " ")} builds don't have a live browser preview.
            </p>
            <p className="font-mono text-[11px] text-amk-fg3 leading-relaxed">
              Open the <strong className="text-white">Code</strong> tab to view the file tree, README.md, and deployment files.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="live-preview" className="h-full flex flex-col">
      <div className="h-9 border-b border-amk-line bg-amk-base flex items-center justify-between px-3 shrink-0">
        <div className="flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5 text-amk-fg3" strokeWidth={1.5} />
          <span className="font-mono text-[11px] text-amk-fg">Live Preview</span>
          <span className="font-mono text-[10px] text-amk-fg3 uppercase">sandboxed iframe</span>
        </div>
        <div className="flex items-center gap-1">
          <a data-testid="open-preview-btn" href={url} target="_blank" rel="noreferrer"
            className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5 px-2 h-6 border border-amk-line">
            <ExternalLink className="w-3 h-3" /> open
          </a>
          <button data-testid="refresh-preview-btn" onClick={() => setBust((b) => b + 1)}
            className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5 px-2 h-6 border border-amk-line">
            <RefreshCw className="w-3 h-3" /> reload
          </button>
        </div>
      </div>
      <div className="flex-1 bg-white">
        {/*
         * Sandbox deliberately omits allow-same-origin to prevent the iframe from
         * accessing the parent's cookies, localStorage, or DOM — even though it is
         * served from the same origin. Having both allow-scripts and allow-same-origin
         * allows a sandboxed document to escape its sandboxing entirely (browser warning).
         * CSS and JavaScript work fine without allow-same-origin because the preview
         * endpoint inlines all assets into a single HTML document.
         * For features that require same-origin access (e.g. localStorage), use the
         * "Open" button below to open the preview in a new tab without sandboxing.
         */}
        <iframe data-testid="preview-iframe" title="preview" src={url}
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-forms allow-popups allow-downloads" />
      </div>
    </div>
  );
}

/**
 * Phase 3: Preview Fallback Panel
 * Shows structured information when live preview is not available.
 */
function PreviewFallbackPanel({ fallback }) {
  return (
    <div data-testid="preview-fallback-panel" className="h-full flex flex-col overflow-auto bg-amk-panel">
      <div className="h-9 border-b border-amk-line bg-amk-base flex items-center px-3 shrink-0">
        <Terminal className="w-3.5 h-3.5 text-amk-fg3 mr-2" strokeWidth={1.5} />
        <span className="font-mono text-[11px] text-amk-fg">Preview Unavailable</span>
        {fallback.detectedType && (
          <span className="ml-2 font-mono text-[10px] text-amk-fg3 uppercase">
            {fallback.detectedType}
          </span>
        )}
      </div>
      <div className="flex-1 p-4 space-y-4 font-mono text-[11px] overflow-auto">
        {/* Reason */}
        <div className="border border-amk-line bg-amk-base p-3 space-y-1">
          <AlertTriangle className="w-4 h-4 text-agent-scout mb-1" strokeWidth={1.5} />
          <p className="text-amk-fg">{fallback.reason}</p>
        </div>

        {/* Stack */}
        {(fallback.detectedStack || []).length > 0 && (
          <FallbackSection label="Detected Stack">
            <div className="flex flex-wrap gap-1">
              {fallback.detectedStack.map((s, i) => (
                <span key={i} className="px-1.5 py-0.5 border border-amk-line text-amk-fg2">{s}</span>
              ))}
            </div>
          </FallbackSection>
        )}

        {/* Next actions */}
        {(fallback.nextActions || []).length > 0 && (
          <FallbackSection label="Next Actions">
            {fallback.nextActions.map((a, i) => (
              <div key={i} className="flex items-start gap-1.5 text-amk-fg2">
                <span className="shrink-0 text-agent-coder">{i + 1}.</span>
                <span>{a}</span>
              </div>
            ))}
          </FallbackSection>
        )}

        {/* Install / Build / Dev commands */}
        {[
          { label: "Install", cmds: fallback.installCommands },
          { label: "Build", cmds: fallback.buildCommands },
          { label: "Dev", cmds: fallback.devCommands },
        ].filter((g) => g.cmds?.length).map(({ label, cmds }) => (
          <FallbackSection key={label} label={`${label} Commands`}>
            {cmds.map((cmd, i) => (
              <code key={i} className="block bg-amk-surface border border-amk-line px-2 py-1 text-amk-fg">
                {cmd}
              </code>
            ))}
          </FallbackSection>
        ))}

        {/* Missing env */}
        {(fallback.missingEnv || []).length > 0 && (
          <FallbackSection label="Required Env Vars">
            <div className="flex flex-wrap gap-1">
              {fallback.missingEnv.map((e, i) => (
                <span key={i} className="px-1.5 py-0.5 border border-agent-scout text-agent-scout">{e}</span>
              ))}
            </div>
          </FallbackSection>
        )}

        {/* Preview blockers */}
        {(fallback.previewBlockers || []).length > 0 && (
          <FallbackSection label="Preview Blockers">
            {fallback.previewBlockers.map((b, i) => (
              <div key={i} className="flex items-start gap-1 text-agent-scout">
                <span className="shrink-0">·</span><span>{b}</span>
              </div>
            ))}
          </FallbackSection>
        )}

        {/* Route map */}
        {(fallback.routeMap || []).length > 0 && (
          <FallbackSection label="Detected Routes">
            {fallback.routeMap.slice(0, 20).map((r, i) => (
              <div key={i} className="text-amk-fg2">
                <code>{r}</code>
              </div>
            ))}
          </FallbackSection>
        )}

        {/* README excerpt */}
        {fallback.readmeExcerpt && (
          <FallbackSection label="README">
            <pre className="text-amk-fg2 whitespace-pre-wrap text-[10px] leading-relaxed">
              {fallback.readmeExcerpt.slice(0, 800)}
            </pre>
          </FallbackSection>
        )}
      </div>
    </div>
  );
}

function FallbackSection({ label, children }) {
  return (
    <div className="space-y-1.5">
      <div className="text-amk-fg3 uppercase tracking-wider text-[10px]">{label}</div>
      <div className="space-y-1 pl-1">{children}</div>
    </div>
  );
}
