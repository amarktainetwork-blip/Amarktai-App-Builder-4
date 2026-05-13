import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Clock3, Github, ShieldCheck, Sparkles } from "lucide-react";
import CapabilityStatus from "@/components/CapabilityStatus";
import { Projects, System } from "@/lib/amk-api";

export default function DashboardHome() {
  const [projects, setProjects] = useState([]);
  const [readiness, setReadiness] = useState(null);

  useEffect(() => {
    Projects.list().then(setProjects).catch(() => setProjects([]));
    System.readiness().then(setReadiness).catch(() => setReadiness(null));
  }, []);

  const recent = projects.slice(0, 4);
  const last = projects[0];

  return (
    <div className="space-y-6">
      <section className="grid gap-px overflow-hidden border border-amk-line bg-amk-line lg:grid-cols-[1.2fr_0.8fr]">
        <div className="grid-bg bg-amk-base p-6 lg:p-8">
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Overview</div>
          <h1 className="mt-3 max-w-3xl font-display text-3xl font-semibold leading-tight tracking-tight text-white md:text-5xl">
            Private beta command center for AI software production.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-amk-fg2">
            Start a prompt-first build, resume a workspace, import a repo, and verify live capability state before making provider-backed claims.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/dashboard/new" className="inline-flex h-11 items-center gap-2 bg-amk-accent px-5 font-mono text-xs uppercase tracking-wider text-black hover:bg-emerald-300">
              Start new build <Sparkles className="h-4 w-4" />
            </Link>
            <Link to="/dashboard/repo" className="inline-flex h-11 items-center gap-2 border border-amk-line px-5 font-mono text-xs uppercase tracking-wider text-amk-fg hover:bg-amk-panel">
              Import repo <Github className="h-4 w-4" />
            </Link>
          </div>
        </div>

        <div className="bg-amk-panel p-6 lg:p-8">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Private beta status</div>
          <div className="mt-4 grid gap-3">
            <StatusCard label="Backend readiness" value={readiness?.overall || "Unknown"} ok={readiness?.overall === "PASS"} />
            <StatusCard label="Agent workspace" value="Available after login" ok />
            <StatusCard label="Provider keys" value="Shown honestly in Settings" ok />
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="border border-amk-line bg-amk-panel p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Continue</div>
              <h2 className="mt-1 font-display text-xl font-semibold text-white">Last workspace</h2>
            </div>
            <Clock3 className="h-5 w-5 text-amk-fg3" />
          </div>
          {last ? (
            <Link to={`/workspace/${last.id}`} className="mt-5 block border border-amk-line bg-amk-base p-4 hover:bg-amk-surface">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-mono text-sm text-white">{last.name}</div>
                  <div className="mt-1 truncate font-mono text-[10px] text-amk-fg3">{last.prompt}</div>
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-amk-fg3" />
              </div>
            </Link>
          ) : (
            <p className="mt-5 text-sm leading-6 text-amk-fg2">No projects yet. Start with a prompt or import a repository.</p>
          )}
        </div>

        <div className="border border-amk-line bg-amk-panel p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Recent projects</div>
              <h2 className="mt-1 font-display text-xl font-semibold text-white">{projects.length} total</h2>
            </div>
            <Link to="/dashboard/projects" className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white">View all</Link>
          </div>
          <div className="mt-4 grid gap-2">
            {recent.length ? recent.map((project) => (
              <Link key={project.id} to={`/workspace/${project.id}`} className="flex items-center justify-between gap-3 border border-amk-line bg-amk-base px-3 py-2 hover:bg-amk-surface">
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs text-white">{project.name}</div>
                  <div className="truncate font-mono text-[10px] text-amk-fg3">{project.status || "queued"}</div>
                </div>
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-amk-fg3" />
              </Link>
            )) : <p className="text-sm text-amk-fg2">No recent projects.</p>}
          </div>
        </div>
      </section>

      <CapabilityStatus compact />
    </div>
  );
}

function StatusCard({ label, value, ok }) {
  return (
    <div className="border border-amk-line bg-amk-base p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{label}</span>
        <ShieldCheck className="h-3.5 w-3.5" style={{ color: ok ? "#00E676" : "#FFC107" }} />
      </div>
      <div className="mt-1 font-mono text-xs uppercase tracking-wider" style={{ color: ok ? "#00E676" : "#FFC107" }}>{value}</div>
    </div>
  );
}
