import { Link } from "react-router-dom";
import { ArrowRight, Bot, ClipboardCheck, Code2, Eye, GitPullRequest, Layers3, RefreshCcw, Rocket, Sparkles } from "lucide-react";

const stages = [
  ["01", "Prompt", "The user describes the product, repo repair, app, website or advanced visual experience."],
  ["02", "Intent + mode", "The system detects build mode, ambiguity, required pages, tools, media and runtime needs."],
  ["03", "Manager Agent", "The manager decomposes work, assigns specialist agents and blocks incomplete completion."],
  ["04", "Creative direction", "Brand, typography, layout, motion and media direction are planned before code is generated."],
  ["05", "Code + media", "Frontend, backend, logo, media, repo and motion agents produce files through capability-aware tooling."],
  ["06", "Sandbox preview", "Generated output is built and previewed through the runtime sandbox when previewable."],
  ["07", "QA + repair", "Validation, visual QA, security, accessibility and performance checks drive repair loops."],
  ["08", "Version + iterate", "Each build creates a version, supports rollback and keeps project memory for future iterations."],
];

const icons = [Sparkles, Layers3, Bot, Eye, Code2, Rocket, ClipboardCheck, RefreshCcw];

export default function PipelinePage() {
  return (
    <main className="min-h-screen bg-amk-base text-amk-fg">
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <Link to="/" className="font-display text-lg tracking-tight text-white">Amarktai Builder</Link>
        <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
          <Link to="/features" className="hover:text-white">Features</Link>
          <Link to="/access" className="border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Request Access</Link>
        </div>
      </nav>

      <section className="mx-auto max-w-7xl px-6 py-16 md:py-24">
        <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Production pipeline</p>
        <h1 className="mt-5 max-w-4xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">
          A real AI software factory, not a one-shot template generator.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-amk-fg2 md:text-lg">
          Every serious build moves through planning, specialist agents, runtime preview, validation, repair, versioning and iteration. The dashboard must show this in real time.
        </p>
      </section>

      <section className="mx-auto max-w-5xl px-6 pb-20">
        <div className="relative space-y-4 before:absolute before:left-6 before:top-8 before:h-[calc(100%-4rem)] before:w-px before:bg-amk-line md:before:left-8">
          {stages.map(([num, title, copy], index) => {
            const Icon = icons[index] || GitPullRequest;
            return (
              <article key={num} className="relative flex gap-5 rounded-2xl border border-amk-line bg-amk-panel/70 p-5 md:p-6">
                <div className="relative z-10 grid h-12 w-12 shrink-0 place-items-center rounded-xl border border-amk-line bg-amk-base text-amk-accent">
                  <Icon className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Stage {num}</div>
                  <h2 className="mt-1 font-display text-xl text-white">{title}</h2>
                  <p className="mt-2 text-sm leading-6 text-amk-fg2">{copy}</p>
                </div>
              </article>
            );
          })}
        </div>
        <Link to="/access" className="mt-10 inline-flex items-center gap-2 border border-amk-accent px-5 py-3 font-mono text-xs uppercase tracking-[0.2em] text-amk-accent hover:bg-amk-accent hover:text-black">
          Request private access <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
    </main>
  );
}
