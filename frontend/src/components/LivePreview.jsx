import { useEffect, useState } from "react";
import { Projects } from "@/lib/amk-api";
import { RefreshCw, ExternalLink, Cpu, AlertTriangle, Loader2 } from "lucide-react";

export default function LivePreview({ projectId, refreshKey, projectStatus, projectError, failedAgent }) {
  const [bust, setBust] = useState(0);
  const url = `${Projects.previewUrl(projectId)}&v=${refreshKey || 0}-${bust}`;

  useEffect(() => { setBust((b) => b + 1); }, [refreshKey]);

  const isFailed = projectStatus === "failed" || projectStatus === "cancelled";
  const isRunning = projectStatus === "running" || projectStatus === "queued";

  if (isFailed) {
    return (
      <div data-testid="live-preview" className="h-full flex flex-col">
        <div className="h-9 border-b border-amk-line bg-amk-base flex items-center px-3 shrink-0">
          <Cpu className="w-3.5 h-3.5 text-amk-fg3 mr-2" strokeWidth={1.5} />
          <span className="font-mono text-[11px] text-amk-fg">Live Preview</span>
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
    return (
      <div data-testid="live-preview" className="h-full flex flex-col">
        <div className="h-9 border-b border-amk-line bg-amk-base flex items-center px-3 shrink-0">
          <Cpu className="w-3.5 h-3.5 text-amk-fg3 mr-2" strokeWidth={1.5} />
          <span className="font-mono text-[11px] text-amk-fg">Live Preview</span>
        </div>
        <div className="flex-1 bg-amk-panel flex items-center justify-center">
          <div className="border border-amk-line rounded-md bg-amk-base p-6 max-w-md text-center space-y-3">
            <Loader2 className="w-7 h-7 text-amk-fg3 mx-auto animate-spin" />
            <p className="font-mono text-[12px] text-amk-fg2">
              Preview will appear when files are generated.
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
          {/* TODO: use a separate preview origin to avoid allow-same-origin requirement */}
          <span className="font-mono text-[10px] text-amk-fg3 uppercase">authenticated iframe</span>
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
        {/* allow-same-origin is required for the preview token auth; TODO: move to separate origin */}
        <iframe data-testid="preview-iframe" title="preview" src={url}
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-forms allow-popups allow-same-origin" />
      </div>
    </div>
  );
}
