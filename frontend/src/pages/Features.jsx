import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Bot, Boxes, Code2, Film, GitPullRequest, MonitorCheck, ShieldCheck, Workflow } from "lucide-react";
import CapabilityStatus from "@/components/CapabilityStatus";

const sections = [
  ["Build types", "Websites, web apps, dashboards, PWAs, APIs, AI chat/RAG, admin tools, and repo-fix workspaces.", Boxes],
  ["Agent system", "Planner, Scout, Architect, Designer, Coder, Media Director, Motion, Runtime QA, Reviewer, and Final Gate.", Bot],
  ["Media system", "Truth-gated media pipeline for images, video, voice/avatar-ready surfaces, stock, upload, and fallback labels.", Film],
  ["Repo workbench", "From prompt to preview to pull request: import, analyze, plan, edit, diff, commit, and PR.", GitPullRequest],
  ["Runtime QA and final gate", "Builds that prove themselves before launch with screenshots, runtime reports, blockers, warnings, and repair loops.", ShieldCheck],
  ["Capability truth", "Every capability is truth-gated. Discovery is not the same as execution.", MonitorCheck],
];

const buildTypes = ["Website", "Landing Page", "Web App", "PWA", "Dashboard", "API Service", "AI Chat/RAG", "Repo Fix"];

export default function FeaturesPage() {
  return (
    <main className="cinematic-bg min-h-screen text-amk-fg">
      <PublicMiniNav />
      <section className="relative mx-auto max-w-7xl px-6 py-16 md:py-24">
        <div className="max-w-4xl">
          <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Capability architecture</p>
          <h1 className="mt-5 font-display text-5xl font-semibold leading-tight text-white md:text-7xl">
            A production loop for software, media, repos, QA, and launch gates.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-amk-fg2">
            Aiva does not just generate files - it runs the production loop. Plan, design, build, preview, test, repair, version, and prepare for launch.
          </p>
        </div>
      </section>

      <section className="relative mx-auto max-w-7xl px-6 pb-16">
        <div className="grid gap-4 lg:grid-cols-3">
          {sections.map(([title, copy, Icon], index) => (
            <motion.article
              key={title}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.04 }}
              className="premium-card rounded-3xl p-6"
            >
              <Icon className="h-6 w-6 text-amk-accent" />
              <h2 className="mt-5 font-display text-2xl font-semibold text-white">{title}</h2>
              <p className="mt-3 text-sm leading-6 text-amk-fg2">{copy}</p>
            </motion.article>
          ))}
        </div>
      </section>

      <FeatureBand title="Build types" icon={Workflow}>
        <div className="flex flex-wrap gap-3">
          {buildTypes.map((item) => <span key={item} className="status-pill text-amk-fg">{item}</span>)}
        </div>
      </FeatureBand>

      <FeatureBand id="media" title="Media system" icon={Film}>
        <div className="grid gap-3 md:grid-cols-4">
          {["AI media when providers are live", "Hero video and motion layers", "Uploaded asset library", "Fallbacks and rate limits labeled"].map((item) => (
            <div key={item} className="rounded-2xl border border-amk-line bg-amk-base/70 p-4 text-sm leading-6 text-amk-fg2">{item}</div>
          ))}
        </div>
      </FeatureBand>

      <FeatureBand id="repo" title="Repo workbench" icon={GitPullRequest}>
        <div className="grid gap-2 md:grid-cols-7">
          {["Import", "Analyze", "Plan", "Edit", "Diff", "Commit", "PR"].map((item, index) => (
            <div key={item} className="rounded-2xl border border-amk-line bg-amk-base/70 p-4">
              <div className="font-mono text-[10px] text-amk-fg3">0{index + 1}</div>
              <div className="mt-2 font-display text-lg text-white">{item}</div>
            </div>
          ))}
        </div>
      </FeatureBand>

      <section className="relative mx-auto max-w-7xl px-6 pb-20">
        <CapabilityStatus />
        <Link to="/access" className="cta-primary mt-8 inline-flex h-12 items-center gap-2 rounded-2xl px-6 font-mono text-xs uppercase tracking-wider">
          Request Access <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
    </main>
  );
}

function PublicMiniNav() {
  return (
    <nav className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
      <Link to="/" className="font-display text-lg font-semibold tracking-tight text-white">Amarktai App Builder</Link>
      <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
        <Link to="/pipeline" className="hover:text-white">Pipeline</Link>
        <Link to="/access" className="rounded-xl border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Request Access</Link>
      </div>
    </nav>
  );
}

function FeatureBand({ id, title, icon: Icon, children }) {
  return (
    <section id={id} className="relative mx-auto max-w-7xl px-6 pb-16">
      <div className="glass-panel rounded-3xl p-6 md:p-8">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-amk-accent/15 text-amk-accent">
            <Icon className="h-5 w-5" />
          </div>
          <h2 className="font-display text-3xl font-semibold text-white">{title}</h2>
        </div>
        {children}
      </div>
    </section>
  );
}
