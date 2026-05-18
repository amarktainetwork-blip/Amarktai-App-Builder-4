import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Bot, Clock3, Code2, Database, Github, Image, LayoutDashboard, MonitorCheck, ShieldCheck, Sparkles } from "lucide-react";
import CapabilityStatus from "@/components/CapabilityStatus";
import { Projects, System } from "@/lib/amk-api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const launchers = [
  ["Website", "landing_page", MonitorCheck],
  ["Web App", "web_app", Code2],
  ["Dashboard", "dashboard", LayoutDashboard],
  ["PWA", "pwa", Sparkles],
  ["API Service", "api_service", Database],
  ["AI Chat/RAG", "ai_chat_rag_app", Bot],
  ["Repo Fix", "repo_fix", Github],
  ["CRM/Admin", "crm_dashboard", LayoutDashboard],
];

export default function DashboardHome() {
  const [projects, setProjects] = useState([]);
  const [readiness, setReadiness] = useState(null);
  const [promptOpen, setPromptOpen] = useState(false);

  useEffect(() => {
    Projects.list().then(setProjects).catch(() => setProjects([]));
    System.readiness().then(setReadiness).catch(() => setReadiness(null));
  }, []);

  const recent = projects.slice(0, 4);
  const last = projects[0];

  return (
    <div className="space-y-6">
      <section className="premium-card rounded-3xl p-6 md:p-8">
        <div className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-amk-accent">Command center</div>
            <h1 className="mt-3 max-w-3xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">What are we building today?</h1>
            <p className="mt-4 max-w-2xl text-base leading-7 text-amk-fg2">Start with a prompt, continue a workspace, or send the Builder Engine into a repo.</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/dashboard/new" className="cta-primary inline-flex h-11 items-center gap-2 rounded-2xl px-5 font-mono text-xs uppercase tracking-wider">
                Start New Build <Sparkles className="h-4 w-4" />
              </Link>
              <Link to="/dashboard/repo" className="cta-secondary inline-flex h-11 items-center gap-2 rounded-2xl px-5 font-mono text-xs uppercase tracking-wider">
                Open Repo Workbench <Github className="h-4 w-4" />
              </Link>
              <Link to="/dashboard/media" className="cta-secondary inline-flex h-11 items-center gap-2 rounded-2xl px-5 font-mono text-xs uppercase tracking-wider">
                Media Studio <Image className="h-4 w-4" />
              </Link>
            </div>
          </div>
          <div className="grid gap-3 rounded-3xl border border-amk-line bg-amk-base/60 p-4">
            {["Plan the work", "Specialists build", "Runtime checks", "Final gate decides"].map((item, index) => (
              <div key={item} className="flex items-center gap-3 rounded-2xl bg-amk-panel/70 p-3">
                <span className="grid h-8 w-8 place-items-center rounded-xl bg-amk-accent/15 font-mono text-[10px] text-amk-accent">0{index + 1}</span>
                <span className="font-mono text-xs uppercase tracking-wider text-white">{item}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-4">
        <StatusCard label="Backend readiness" value={readiness?.overall || "Unknown"} color={readiness?.overall === "PASS" ? "#10B981" : "#F59E0B"} />
        <StatusCard label="Provider truth" value="Truth-gated" color="#22D3EE" />
        <StatusCard label="Runtime QA" value="Evidence based" color="#8B5CF6" />
        <StatusCard label="Final gate" value="No fake green" color="#10B981" />
      </section>

      <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="glass-panel rounded-3xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Active workspace</div>
              <h2 className="mt-1 font-display text-2xl font-semibold text-white">Latest build</h2>
            </div>
            <Clock3 className="h-5 w-5 text-amk-fg3" />
          </div>
          {last ? (
            <div className="mt-5 rounded-3xl border border-amk-line bg-amk-base/70 p-4">
              <div className="font-mono text-sm text-white">{last.name || "Untitled workspace"}</div>
              <div className="mt-2 inline-flex rounded-full border border-amk-line px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{last.status || "queued"}</div>
              {(last.summary || last.prompt) && (
                <p className="mt-4 overflow-hidden text-sm leading-6 text-amk-fg2 [display:-webkit-box] [-webkit-line-clamp:3] [-webkit-box-orient:vertical]">
                  {last.summary || shortPrompt(last.prompt)}
                </p>
              )}
              <div className="mt-5 flex flex-wrap gap-2">
                <Link to={`/workspace/${last.id}`} className="cta-primary inline-flex h-10 items-center gap-2 rounded-2xl px-4 font-mono text-[10px] uppercase tracking-wider">
                  Open workspace <ArrowRight className="h-3.5 w-3.5" />
                </Link>
                {last.prompt && <Button type="button" variant="outline" onClick={() => setPromptOpen(true)} className="h-10 rounded-2xl border-amk-line font-mono text-[10px] uppercase tracking-wider">View prompt</Button>}
              </div>
            </div>
          ) : (
            <div className="mt-5 rounded-3xl border border-dashed border-amk-line bg-amk-base/50 p-6 text-sm leading-6 text-amk-fg2">No projects yet. Start with a prompt or import a repository.</div>
          )}
        </div>

        <div className="glass-panel rounded-3xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Launch a build type</div>
              <h2 className="mt-1 font-display text-2xl font-semibold text-white">Choose the workspace shape</h2>
            </div>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {launchers.map(([label, mode, Icon]) => (
              <Link key={label} to="/dashboard/new" state={{ mode }} className="rounded-3xl border border-amk-line bg-amk-base/70 p-4 transition hover:border-amk-accent hover:bg-amk-accent/10">
                <Icon className="h-5 w-5 text-amk-accent" />
                <div className="mt-4 font-mono text-xs uppercase tracking-wider text-white">{label}</div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <CapabilityStatus compact />

      <section className="glass-panel rounded-3xl p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Recent projects</div>
            <h2 className="mt-1 font-display text-2xl font-semibold text-white">{projects.length} total</h2>
          </div>
          <Link to="/dashboard/projects" className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:text-white">View all</Link>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {recent.length ? recent.map((project) => (
            <Link key={project.id} to={`/workspace/${project.id}`} className="rounded-3xl border border-amk-line bg-amk-base/70 p-4 hover:border-amk-accent">
              <div className="truncate font-mono text-xs text-white">{project.name}</div>
              <div className="mt-2 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{project.status || "queued"}</div>
              {project.prompt && <p className="mt-3 line-clamp-2 text-xs leading-5 text-amk-fg2">{shortPrompt(project.prompt)}</p>}
            </Link>
          )) : <p className="text-sm text-amk-fg2">No recent projects.</p>}
        </div>
      </section>

      <Dialog open={promptOpen} onOpenChange={setPromptOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto rounded-3xl border-amk-line bg-amk-panel text-amk-fg">
          <DialogHeader>
            <DialogTitle className="font-display text-xl text-white">{last?.name || "Workspace prompt"}</DialogTitle>
          </DialogHeader>
          <pre className="whitespace-pre-wrap break-words rounded-2xl border border-amk-line bg-amk-base p-4 text-xs leading-5 text-amk-fg2">{last?.prompt || ""}</pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function shortPrompt(prompt = "") {
  return prompt.length > 180 ? `${prompt.slice(0, 177).trim()}...` : prompt;
}

function StatusCard({ label, value, color }) {
  return (
    <div className="glass-panel rounded-3xl p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{label}</span>
        <ShieldCheck className="h-4 w-4" style={{ color }} />
      </div>
      <div className="mt-2 font-mono text-xs uppercase tracking-wider" style={{ color }}>{value}</div>
    </div>
  );
}
