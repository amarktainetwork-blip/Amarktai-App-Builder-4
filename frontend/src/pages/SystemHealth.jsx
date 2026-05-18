import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, RefreshCw, Router, ShieldCheck, TerminalSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { System } from "@/lib/amk-api";

export default function SystemHealthPage() {
  const [readiness, setReadiness] = useState(null);
  const [goLive, setGoLive] = useState(null);
  const [router, setRouter] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [readinessResult, goLiveResult, routerResult] = await Promise.allSettled([
        System.readiness(),
        System.goLiveStatus(),
        System.modelRouterStatus(),
      ]);
      setReadiness(readinessResult.status === "fulfilled" ? readinessResult.value : null);
      setGoLive(goLiveResult.status === "fulfilled" ? goLiveResult.value : null);
      setRouter(routerResult.status === "fulfilled" ? routerResult.value : null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const readinessChecks = readiness?.checks || [];
  const goLiveChecks = goLive?.checks || goLive?.self_tests || [];

  return (
    <main className="command-shell min-h-screen text-amk-fg">
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-8 md:py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <Link to="/dashboard" className="cta-secondary inline-flex h-10 items-center gap-2 rounded-2xl px-4 font-mono text-[10px] uppercase tracking-wider">
            <ArrowLeft className="h-3.5 w-3.5" /> Dashboard
          </Link>
          <Button onClick={refresh} disabled={loading} className="h-10 rounded-2xl bg-white px-4 font-mono text-[10px] uppercase tracking-wider text-black hover:bg-amk-accent">
            <RefreshCw className={`mr-2 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh evidence
          </Button>
        </div>

        <section className="premium-card rounded-3xl p-6 md:p-8">
          <div className="grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-amk-accent">Runtime QA and go-live</div>
              <h1 className="mt-3 max-w-4xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">
                Final status comes from evidence, not optimistic labels.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-amk-fg2">
                Readiness, model routing, runtime QA, capability truth, and go-live self-tests stay visible here so launch decisions cannot hide setup gaps.
              </p>
            </div>
            <div className="grid gap-3">
              <StatusTile label="Backend readiness" value={readiness?.overall || "Unknown"} />
              <StatusTile label="Go-live status" value={goLive?.status || goLive?.overall || "Unknown"} />
              <StatusTile label="Model router" value={router ? "Loaded" : "Unknown"} />
            </div>
          </div>
        </section>

        {readiness?.blockers?.length > 0 && (
          <section className="mt-6 rounded-3xl border border-amk-red/40 bg-amk-red/10 p-5">
            <div className="font-mono text-xs uppercase tracking-wider text-amk-red">Launch blockers</div>
            <div className="mt-3 grid gap-2">
              {readiness.blockers.map((blocker, index) => (
                <p key={index} className="rounded-2xl border border-amk-red/20 bg-black/20 p-3 font-mono text-[11px] leading-5 text-red-100">{blocker}</p>
              ))}
            </div>
          </section>
        )}

        <section className="mt-6 grid gap-6 lg:grid-cols-2">
          <EvidencePanel title="Readiness Checks" icon={ShieldCheck} rows={readinessChecks} empty="Readiness has not returned checks yet." />
          <EvidencePanel title="Go-Live / Final Gate" icon={TerminalSquare} rows={goLiveChecks} empty="Go-live self-tests have not returned yet." />
        </section>

        <section className="mt-6 glass-panel rounded-3xl p-5">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-2xl bg-amk-accent/15 text-amk-accent">
              <Router className="h-5 w-5" />
            </div>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Model router</div>
              <h2 className="font-display text-2xl font-semibold text-white">Agent routing remains provider-aware</h2>
            </div>
          </div>
          <pre className="mt-4 max-h-96 overflow-auto rounded-2xl border border-amk-line bg-amk-base/80 p-4 text-xs leading-5 text-amk-fg2">
            {JSON.stringify(router || { status: "not_loaded" }, null, 2)}
          </pre>
        </section>
      </div>
    </main>
  );
}

function StatusTile({ label, value }) {
  const normalized = String(value || "").toLowerCase();
  const color = normalized.includes("pass") || normalized.includes("ok") || normalized.includes("loaded") ? "#10B981" : normalized.includes("fail") || normalized.includes("block") ? "#EF4444" : "#F59E0B";
  return (
    <div className="rounded-3xl border border-amk-line bg-amk-base/70 p-4">
      <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{label}</div>
      <div className="mt-2 font-mono text-xs uppercase tracking-wider" style={{ color }}>{value}</div>
    </div>
  );
}

function EvidencePanel({ title, icon: Icon, rows, empty }) {
  return (
    <div className="glass-panel overflow-hidden rounded-3xl">
      <div className="flex items-center gap-3 border-b border-amk-line p-5">
        <Icon className="h-5 w-5 text-amk-accent" />
        <h2 className="font-display text-2xl font-semibold text-white">{title}</h2>
      </div>
      <div className="divide-y divide-amk-line">
        {rows.length ? rows.map((row, index) => (
          <div key={`${row.name || row.check || "check"}-${index}`} className="grid gap-2 p-4 md:grid-cols-[minmax(0,1fr)_110px]">
            <div>
              <div className="font-mono text-xs text-white">{row.name || row.check || row.id || `Check ${index + 1}`}</div>
              <div className="mt-1 font-mono text-[11px] leading-5 text-amk-fg3">{row.detail || row.message || row.reason || row.description || "No detail returned."}</div>
            </div>
            <StatusBadge value={row.status || row.result || (row.ok === true ? "PASS" : row.ok === false ? "FAIL" : "UNKNOWN")} />
          </div>
        )) : <div className="p-6 text-sm text-amk-fg3">{empty}</div>}
      </div>
    </div>
  );
}

function StatusBadge({ value }) {
  const normalized = String(value || "UNKNOWN").toLowerCase();
  const color = normalized.includes("pass") || normalized === "true" || normalized.includes("ok") ? "#10B981" : normalized.includes("fail") || normalized.includes("block") || normalized === "false" ? "#EF4444" : "#F59E0B";
  return <span className="h-fit rounded-full border px-3 py-1 font-mono text-[10px] uppercase tracking-wider" style={{ color, borderColor: `${color}55`, background: `${color}14` }}>{String(value || "UNKNOWN")}</span>;
}
