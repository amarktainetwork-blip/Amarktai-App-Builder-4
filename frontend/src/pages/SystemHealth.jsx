import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw, ArrowLeft } from "lucide-react";
import Header from "@/components/Header";
import { Button } from "@/components/ui/button";
import { System } from "@/lib/amk-api";

export default function SystemHealthPage() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      setData(await System.readiness());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div className="min-h-screen bg-amk-base">
      <Header rightExtra={
        <button onClick={() => nav("/app")} className="inline-flex items-center gap-1.5 px-3 h-8 border border-amk-line hover:bg-amk-surface font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:text-white">
          <ArrowLeft className="w-3 h-3" /> dashboard
        </button>
      } />
      <main className="max-w-5xl mx-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-2">[ system health ]</div>
            <h1 className="font-display text-3xl font-semibold">Readiness: {data?.overall || "checking"}</h1>
          </div>
          <Button onClick={refresh} disabled={loading} className="bg-white text-black hover:bg-zinc-200 font-mono text-xs">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
          </Button>
        </div>
        {data?.blockers?.length > 0 && (
          <div className="border border-agent-scout bg-amk-panel p-4 mb-5">
            <div className="font-mono text-xs text-agent-scout uppercase mb-2">Blockers</div>
            {data.blockers.map((b, i) => <p key={i} className="font-mono text-[11px] text-amk-fg2">{b}</p>)}
          </div>
        )}
        <div className="border border-amk-line bg-amk-panel">
          {(data?.checks || []).map((c) => (
            <div key={`${c.name}-${c.detail}`} className="grid md:grid-cols-[220px,90px,1fr] gap-3 border-b border-amk-line last:border-b-0 p-3">
              <div className="font-mono text-xs text-white">{c.name}</div>
              <div className={`font-mono text-[10px] uppercase ${c.status === "PASS" ? "text-agent-coder" : c.status === "WARN" ? "text-agent-reviewer" : "text-agent-scout"}`}>{c.status}</div>
              <div className="font-mono text-[11px] text-amk-fg3">{c.detail}</div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
