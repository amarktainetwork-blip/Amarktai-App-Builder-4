import { Link } from "react-router-dom";
import { ArrowRight, Bot, ClipboardCheck, Code2, Eye, GitPullRequest, Layers3, RefreshCcw, Sparkles } from "lucide-react";

const stages = [
  ["01", "Prompt", "The approved user describes the product, app, website, API, or repo repair target.", Sparkles],
  ["02", "Mode Detection", "The system detects build mode, ambiguity, pages, media needs, runtime shape, and repo intent.", Layers3],
  ["03", "Manager Agent", "The manager decomposes work, assigns specialist agents, and keeps completion standards visible.", Bot],
  ["04", "Specialist Agents", "Design, code, repo, media, runtime, QA, security, memory, and deployment agents produce real artifacts.", Code2],
  ["05", "Preview", "Previewable output is served through the runtime with a scoped preview token and honest fallback states.", Eye],
  ["06", "QA and Repair", "Validation, coverage, security, and repair loops decide what is finished and what still needs work.", ClipboardCheck],
  ["07", "Version", "Build state is captured so work can be compared, restored, and continued.", RefreshCcw],
  ["08", "Iterate or Export", "Users request changes, continue missing work, or export to GitHub when supported and configured.", GitPullRequest],
];

export default function PipelinePage() {
  return (
    <main className="min-h-screen bg-amk-base text-amk-fg">
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <Link to="/" className="font-display text-lg tracking-tight text-white">Amarktai App Builder</Link>
        <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
          <Link to="/features" className="hover:text-white">Features</Link>
          <Link to="/access" className="border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Request Access</Link>
        </div>
      </nav>

      <section className="mx-auto max-w-7xl px-6 py-16 md:py-24">
        <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Production pipeline</p>
        <h1 className="mt-5 max-w-4xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">
          Prompt to mode detection to manager to specialists to preview to QA to repair to version to iteration.
        </h1>
        <p className="mt-6 max-w-2xl text-base leading-7 text-amk-fg2 md:text-lg">
          This is the product flow the dashboard exposes. Unsupported provider work is not presented as available until setup is complete.
        </p>
      </section>

      <section className="mx-auto max-w-5xl px-6 pb-20">
        <div className="grid gap-3">
          {stages.map(([num, title, copy, Icon]) => (
            <article key={num} className="grid gap-4 border border-amk-line bg-amk-panel p-5 md:grid-cols-[72px_1fr]">
              <div className="grid h-14 w-14 place-items-center border border-amk-line bg-amk-base text-amk-accent">
                <Icon className="h-5 w-5" strokeWidth={1.5} />
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Stage {num}</div>
                <h2 className="mt-1 font-display text-xl text-white">{title}</h2>
                <p className="mt-2 text-sm leading-6 text-amk-fg2">{copy}</p>
              </div>
            </article>
          ))}
        </div>
        <Link to="/access" className="mt-10 inline-flex h-11 items-center gap-2 border border-amk-accent px-5 font-mono text-xs uppercase tracking-[0.2em] text-amk-accent hover:bg-amk-accent hover:text-black">
          Request private access <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
    </main>
  );
}
