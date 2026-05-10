import { useEffect, useState } from "react";
import { Projects } from "@/lib/amk-api";
import { RefreshCw, ExternalLink, Cpu } from "lucide-react";

const WEBCONTAINER_KEY = process.env.REACT_APP_WEBCONTAINER_API_KEY;

export default function LivePreview({ projectId, refreshKey }) {
  const [bust, setBust] = useState(0);
  const [usingWC] = useState(false); // WebContainer disabled until key is provided
  const url = `${Projects.previewUrl(projectId)}?v=${refreshKey || 0}-${bust}`;

  useEffect(() => { setBust((b) => b + 1); }, [refreshKey]);

  return (
    <div data-testid="live-preview" className="h-full flex flex-col">
      <div className="h-9 border-b border-amk-line bg-amk-base flex items-center justify-between px-3 shrink-0">
        <div className="flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5 text-amk-fg3" strokeWidth={1.5} />
          <span className="font-mono text-[11px] text-amk-fg">Live Preview</span>
          <span className="font-mono text-[10px] text-amk-fg3 uppercase">
            {usingWC ? "webcontainer" : "iframe-render"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <a
            data-testid="open-preview-btn"
            href={url}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5 px-2 h-6 border border-amk-line"
          >
            <ExternalLink className="w-3 h-3" /> open
          </a>
          <button
            data-testid="refresh-preview-btn"
            onClick={() => setBust((b) => b + 1)}
            className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white inline-flex items-center gap-1.5 px-2 h-6 border border-amk-line"
          >
            <RefreshCw className="w-3 h-3" /> reload
          </button>
        </div>
      </div>
      <div className="flex-1 bg-white">
        <iframe
          data-testid="preview-iframe"
          title="preview"
          src={url}
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
        />
      </div>
      {!WEBCONTAINER_KEY && (
        <div className="px-3 py-1.5 border-t border-amk-line bg-amk-base/80 font-mono text-[10px] text-amk-fg3">
          // webcontainer key not set — using lightweight static iframe renderer
        </div>
      )}
    </div>
  );
}
