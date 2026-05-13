import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { System } from "@/lib/amk-api";

const CAPABILITIES = [
  { key: "preview_generation", label: "Preview generation" },
  { key: "text_generation", label: "GenX text/reasoning" },
  { key: "repo_analysis", label: "GenX repo analysis" },
  { key: "image_generation", label: "GenX image media" },
  { key: "video_generation", label: "Qwen video" },
  { key: "voice_generation", label: "Qwen voice/audio" },
  { key: "github_integration", label: "GitHub import/PR" },
  { key: "web_research", label: "Brave research" },
  { key: "stock_media", label: "Pixabay media" },
];

export default function CapabilityStatus({ compact = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      setData(await System.capabilitiesStatus());
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  return (
    <section data-testid="capability-status" className="border border-amk-line bg-amk-panel">
      <div className="flex items-center justify-between border-b border-amk-line px-4 py-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Capability truth</div>
          {!compact && <h2 className="mt-1 font-display text-xl font-semibold tracking-tight text-white">Configured vs available</h2>}
        </div>
        <button onClick={refresh} className="inline-flex h-8 items-center gap-2 border border-amk-line px-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:bg-amk-surface hover:text-white">
          <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>
      <div className={`grid gap-px bg-amk-line ${compact ? "sm:grid-cols-2 lg:grid-cols-3" : "md:grid-cols-2 xl:grid-cols-3"}`}>
        {CAPABILITIES.map(({ key, label }) => {
          const cap = data?.summary?.[key];
          const status = getStatus(cap, key);
          return (
            <div key={key} className="bg-amk-base px-4 py-3">
              <div className="font-mono text-[11px] uppercase tracking-wider text-amk-fg">{label}</div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-wider" style={{ color: status.color }}>
                {status.label}
              </div>
              {!compact && cap?.reason && <p className="mt-2 text-xs leading-5 text-amk-fg3">{cap.reason}</p>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function getStatus(capability, key) {
  if (capability?.available) return { label: "Available", color: "#00E676" };
  if (capability?.coming_soon) return { label: "Coming soon", color: "#A1A1AA" };
  if (key === "preview_generation") return { label: "Available", color: "#00E676" };
  return { label: key === "text_generation" || key === "repo_analysis" ? "Requires setup" : "Not configured", color: "#FFC107" };
}
