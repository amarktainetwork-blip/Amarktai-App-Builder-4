import { Link } from "react-router-dom";
import { ArrowRight, Cpu, GitPullRequest, Network } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const chips = ["28 active agents", "Runtime preview", "Repo workbench", "Versioning", "Rollback", "Capability truth"];

export default function LandingPage() {
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-amk-base text-amk-fg">
      <PublicNav user={user} />
      <section className="border-b border-amk-line">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-16 md:py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <div className="inline-flex h-8 items-center gap-2 border border-amk-line bg-amk-panel px-3 font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg2">
              <span className="pulse-dot bg-amk-accent" /> Private beta
            </div>
            <h1 className="mt-6 font-display text-5xl font-semibold leading-none tracking-tight text-white md:text-7xl">
              Amarktai App Builder
              <span className="block text-amk-fg2">is a private AI</span>
              <span className="block text-amk-accent">software factory.</span>
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-amk-fg2 md:text-lg">
              A command center for approved users to plan, build, preview, repair, version, and export software with specialist agents. Provider-backed AI, media, research, and GitHub actions appear only when their keys are configured.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              {chips.map((chip) => (
                <span key={chip} className="border border-amk-line bg-amk-panel px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-amk-fg2">
                  {chip}
                </span>
              ))}
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/access" className="inline-flex h-12 items-center gap-2 bg-white px-6 font-mono text-xs uppercase tracking-wider text-black hover:bg-zinc-200" data-testid="hero-cta-primary">
                Request Access <ArrowRight className="h-4 w-4" />
              </Link>
              <Link to="/login" className="inline-flex h-12 items-center gap-2 border border-amk-line px-6 font-mono text-xs uppercase tracking-wider text-amk-fg hover:bg-amk-panel" data-testid="hero-cta-secondary">
                Login for approved users
              </Link>
              <Link to="/pipeline" className="inline-flex h-12 items-center gap-2 border border-amk-line px-6 font-mono text-xs uppercase tracking-wider text-amk-fg hover:bg-amk-panel">
                Explore Pipeline
              </Link>
            </div>
          </div>
          <CommandMockup />
        </div>
      </section>

      <section className="border-b border-amk-line py-14">
        <div className="mx-auto grid max-w-7xl gap-px border border-amk-line bg-amk-line px-0 md:grid-cols-3">
          <Signal icon={Network} title="Capability-aware" copy="GenX, Qwen, GitHub, Firecrawl, and Pixabay states are read from real configuration." />
          <Signal icon={Cpu} title="Scoped preview" copy="Live preview uses a short-lived scoped token, not the normal auth JWT in the iframe URL." />
          <Signal icon={GitPullRequest} title="Repo workbench" copy="Public import is available; private repo and PR operations require a configured GitHub PAT." />
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-8 px-5 py-20 lg:grid-cols-[0.8fr_1.2fr]">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Pipeline</div>
          <h2 className="mt-3 font-display text-4xl font-semibold tracking-tight text-white">From prompt to versioned workspace.</h2>
          <p className="mt-4 text-sm leading-6 text-amk-fg2">
            Prompt, mode detection, manager agent, specialist agents, preview, QA, repair, version, then iterate or export.
          </p>
        </div>
        <ol className="grid gap-2 md:grid-cols-2">
          {["Prompt", "Mode detection", "Manager agent", "Specialist agents", "Preview", "QA and repair", "Version", "Iterate or export"].map((stage, index) => (
            <li key={stage} className="border border-amk-line bg-amk-panel p-4">
              <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Stage {String(index + 1).padStart(2, "0")}</div>
              <div className="mt-2 font-display text-xl text-white">{stage}</div>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t border-amk-line bg-amk-panel py-20">
        <div className="mx-auto max-w-3xl px-5 text-center">
          <h2 className="font-display text-4xl font-semibold tracking-tight text-white md:text-6xl">Private beta access is intentional.</h2>
          <p className="mx-auto mt-5 max-w-xl text-base leading-7 text-amk-fg2">
            Request access, get approved, then use a dashboard that tells the truth about what is available, what needs setup, and what is not configured.
          </p>
          <Link to="/access" className="mt-8 inline-flex h-12 items-center gap-2 bg-amk-accent px-7 font-mono text-xs uppercase tracking-wider text-black hover:bg-emerald-300">
            Request Access <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}

function PublicNav({ user }) {
  return (
    <nav data-testid="landing-nav" className="sticky top-0 z-40 border-b border-amk-line bg-amk-base/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-5">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center border border-amk-line bg-amk-panel font-mono text-sm font-bold">A</div>
          <span className="font-display font-semibold tracking-tight text-white">Amarktai App Builder</span>
        </Link>
        <div className="hidden items-center gap-6 font-mono text-xs text-amk-fg2 md:flex">
          <Link to="/features" className="hover:text-white">Features</Link>
          <Link to="/pipeline" className="hover:text-white">Pipeline</Link>
          <Link to="/access" className="hover:text-white">Access</Link>
          <Link to="/contact" className="hover:text-white">Contact</Link>
        </div>
        <Link to={user ? "/dashboard" : "/access"} className="inline-flex h-9 items-center gap-2 bg-white px-4 font-mono text-xs text-black hover:bg-zinc-200">
          {user ? "Open Dashboard" : "Request Access"} <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </nav>
  );
}

function CommandMockup() {
  return (
    <div className="border border-amk-line bg-amk-panel shadow-2xl shadow-black/40">
      <div className="flex h-10 items-center gap-2 border-b border-amk-line bg-amk-base px-3">
        <span className="h-2 w-2 bg-amk-fg3" />
        <span className="h-2 w-2 bg-amk-fg3" />
        <span className="h-2 w-2 bg-amk-fg3" />
        <span className="ml-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">workspace command center</span>
      </div>
      <div className="grid gap-px bg-amk-line md:grid-cols-[0.85fr_1.15fr]">
        <div className="space-y-2 bg-amk-panel p-4">
          {[
            ["Manager", "Routing build plan", "#00E676"],
            ["Designer", "Layout and brand direction", "#2962FF"],
            ["Coder", "Writing files", "#00E676"],
            ["QA", "Repair loop active", "#FFC107"],
          ].map(([agent, status, color]) => (
            <div key={agent} className="border-l-2 bg-amk-base px-3 py-2" style={{ borderColor: color }}>
              <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color }}>{agent}</div>
              <div className="mt-1 font-mono text-[11px] text-amk-fg2">{status}</div>
            </div>
          ))}
        </div>
        <div className="bg-white p-4 text-black">
          <div className="border border-zinc-200 p-4">
            <div className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">Live preview</div>
            <div className="mt-4 grid gap-2">
              <div className="h-8 bg-zinc-900" />
              <div className="grid grid-cols-3 gap-2">
                <div className="h-20 bg-emerald-200" />
                <div className="h-20 bg-zinc-200" />
                <div className="h-20 bg-blue-200" />
              </div>
              <div className="h-16 border border-zinc-200" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Signal({ icon: Icon, title, copy }) {
  return (
    <article className="bg-amk-base p-6">
      <Icon className="h-5 w-5 text-amk-accent" />
      <h3 className="mt-4 font-display text-xl text-white">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-amk-fg2">{copy}</p>
    </article>
  );
}
