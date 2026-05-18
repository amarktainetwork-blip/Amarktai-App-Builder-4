import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Bot, ClipboardCheck, Code2, Eye, GitPullRequest, Layers3, Palette, RefreshCcw, Sparkles, Wand2 } from "lucide-react";

const stages = [
  ["Prompt", "Describe the product, workspace, repo change, or launch goal.", Sparkles, "#22D3EE"],
  ["Clarify", "The Builder Engine asks only when ambiguity could break the build.", Wand2, "#3B82F6"],
  ["Plan", "Planner and Scout shape the product route.", Bot, "#8B5CF6"],
  ["Design", "Creative direction becomes layout, copy, sections, and visual treatment.", Palette, "#D946EF"],
  ["Generate", "Coder writes the project files and supporting evidence.", Code2, "#22D3EE"],
  ["Media", "Truth-gated media pipeline persists and labels assets.", Layers3, "#F59E0B"],
  ["Preview", "A live workspace renders the result.", Eye, "#3B82F6"],
  ["QA", "Runtime screenshots, content checks, and blockers surface.", ClipboardCheck, "#10B981"],
  ["Repair", "Failures route back through the right agent.", RefreshCcw, "#F97316"],
  ["Version", "Workspace state is captured for rollback and iteration.", Layers3, "#8B5CF6"],
  ["Export / PR / Deploy gate", "Final output is prepared only when gates allow it.", GitPullRequest, "#10B981"],
];

export default function PipelinePage() {
  return (
    <main className="cinematic-bg min-h-screen text-amk-fg">
      <nav className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <Link to="/" className="font-display text-lg font-semibold tracking-tight text-white">Amarktai App Builder</Link>
        <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
          <Link to="/features" className="hover:text-white">Features</Link>
          <Link to="/access" className="rounded-xl border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Request Access</Link>
        </div>
      </nav>

      <section className="relative mx-auto max-w-7xl px-6 py-16 md:py-24">
        <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Prompt to production</p>
        <h1 className="mt-5 max-w-5xl font-display text-5xl font-semibold leading-tight text-white md:text-7xl">
          Builds that prove themselves before launch.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-8 text-amk-fg2">
          From prompt to preview to pull request, Amarktai Builder routes every step through specialist work, runtime evidence, and final gate checks.
        </p>
      </section>

      <section className="relative mx-auto max-w-6xl px-6 pb-20">
        <div className="relative">
          <div className="absolute left-6 top-0 hidden h-full w-px bg-gradient-to-b from-amk-accent via-amk-violet to-amk-green md:block" />
          <div className="grid gap-4">
            {stages.map(([title, copy, Icon, color], index) => (
              <motion.article
                key={title}
                initial={{ opacity: 0, x: -16 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.035 }}
                className="glass-panel rounded-3xl p-5 md:ml-14"
              >
                <div className="flex flex-col gap-4 md:flex-row md:items-center">
                  <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl border border-amk-line bg-amk-base" style={{ color }}>
                    <Icon className="h-6 w-6" strokeWidth={1.6} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Stage {String(index + 1).padStart(2, "0")}</div>
                    <h2 className="mt-1 font-display text-2xl font-semibold text-white">{title}</h2>
                    <p className="mt-2 text-sm leading-6 text-amk-fg2">{copy}</p>
                  </div>
                </div>
              </motion.article>
            ))}
          </div>
        </div>
        <Link to="/access" className="cta-primary mt-10 inline-flex h-12 items-center gap-2 rounded-2xl px-6 font-mono text-xs uppercase tracking-wider">
          Request private access <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
    </main>
  );
}
