import { Link } from "react-router-dom";
import { ArrowRight, BrainCircuit, Code2, GitBranch, Image, ShieldCheck, Sparkles } from "lucide-react";

const features = [
  { icon: BrainCircuit, title: "Agent production team", copy: "Manager, strategist, creative director, designer, coders, repo engineer, media, QA, security and deployment agents coordinate the build instead of acting like disconnected prompts." },
  { icon: Code2, title: "Apps, SaaS and websites", copy: "Create landing pages, multi-page sites, PWAs, dashboards, admin systems, APIs and full-stack scaffolds through one guided workspace." },
  { icon: GitBranch, title: "Repo workbench", copy: "Import GitHub repos, detect stacks, analyse gaps, repair builds, review diffs and prepare PRs without leaving the dashboard." },
  { icon: Image, title: "Media and brand engine", copy: "Generate or reuse logos, SVGs, stock media, AI media where configured, icons and brand assets with honest capability states." },
  { icon: ShieldCheck, title: "Runtime truth and QA", copy: "Sandbox previews, validation, security checks, accessibility/SEO scoring and repair loops keep the system honest about what actually works." },
  { icon: Sparkles, title: "Premium by default", copy: "Cheap mode optimises routing cost, not design quality. Every product still has to pass premium layout, typography and responsiveness standards." },
];

export default function FeaturesPage() {
  return (
    <main className="min-h-screen bg-amk-base text-amk-fg overflow-hidden">
      <section className="border-b border-amk-line bg-[radial-gradient(circle_at_top_right,rgba(0,230,118,0.14),transparent_34%),linear-gradient(180deg,#07110d,#050706)]">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link to="/" className="font-display text-lg tracking-tight text-white">Amarktai Builder</Link>
          <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
            <Link to="/pipeline" className="hover:text-white">Pipeline</Link>
            <Link to="/access" className="border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Request Access</Link>
          </div>
        </nav>
        <div className="mx-auto max-w-7xl px-6 py-20 md:py-28">
          <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Private capability showcase</p>
          <h1 className="mt-5 max-w-4xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">
            Everything the builder can actually do, shown without fake claims.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-amk-fg2 md:text-lg">
            Amarktai coordinates specialist AI agents, real runtime previews, repo repair, media tooling, versioning and strict validation inside one product-building command center.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {features.map(({ icon: Icon, title, copy }) => (
            <article key={title} className="group border border-amk-line bg-amk-panel/70 p-6 transition hover:-translate-y-1 hover:border-amk-accent/60 hover:bg-amk-panel">
              <Icon className="h-6 w-6 text-amk-accent" strokeWidth={1.5} />
              <h2 className="mt-5 font-display text-xl text-white">{title}</h2>
              <p className="mt-3 text-sm leading-6 text-amk-fg2">{copy}</p>
              <div className="mt-5 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3">
                Capability-aware <ArrowRight className="h-3 w-3" />
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
