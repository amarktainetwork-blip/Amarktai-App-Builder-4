import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  CircuitBoard,
  Code2,
  Film,
  GitPullRequest,
  Image,
  Layers3,
  MonitorCheck,
  Play,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Workflow,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const navItems = [
  ["Builds", "/features"],
  ["Agents", "/pipeline"],
  ["Media", "/features#media"],
  ["Repo Workbench", "/features#repo"],
  ["Access", "/access"],
];

const capabilities = [
  ["Websites & Landing Pages", "Cinematic pages, responsive sections, conversion copy, media treatment.", MonitorCheck],
  ["Web Apps & PWAs", "Interactive product flows, installable experiences, dashboards and portals.", CircuitBoard],
  ["Dashboards & Admin Tools", "Charts, tables, metrics, internal tools, CRM and operations screens.", Layers3],
  ["APIs & Full-stack Apps", "Backend scaffolds, routes, contracts, docs and integration-ready services.", Code2],
  ["Repo Workbench", "Import a repo, ask for a change, review diffs, commit, and open PRs.", GitPullRequest],
  ["Media Pipeline", "Images, video, voice/avatar and stock fallback - only marked live when proven.", Image],
];

const agents = [
  ["Planner", "Turns intent into a build route."],
  ["Scout", "Finds context and constraints."],
  ["Architect", "Defines stack and contracts."],
  ["Designer", "Shapes product-grade UI."],
  ["Coder", "Writes the working files."],
  ["Media Director", "Routes visual and media proof."],
  ["Motion", "Adds cinematic interaction."],
  ["Runtime QA", "Runs browser evidence."],
  ["Reviewer", "Checks and repairs output."],
  ["Final Gate", "Blocks fake green lights."],
];

const truthBadges = [
  ["End-to-end available", "#10B981"],
  ["Provider discovered", "#22D3EE"],
  ["Runtime failed", "#F97316"],
  ["Rate limited", "#F59E0B"],
  ["Setup needed", "#64748B"],
  ["Optional", "#8B5CF6"],
];

export default function LandingPage() {
  const { user } = useAuth();
  return (
    <main className="cinematic-bg min-h-screen text-amk-fg">
      <div className="premium-orb orb-cyan left-[-12rem] top-20" />
      <div className="premium-orb orb-violet right-[-10rem] top-10" />
      <div className="premium-orb orb-magenta bottom-80 left-1/2" />
      <PublicNav user={user} />

      <section className="relative mx-auto grid max-w-7xl gap-12 px-5 pb-20 pt-14 md:pt-20 lg:grid-cols-[0.92fr_1.08fr] lg:items-center">
        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}>
          <div className="status-pill inline-flex items-center gap-2 text-amk-accent">
            <span className="h-2 w-2 rounded-full bg-amk-accent shadow-[0_0_24px_rgba(34,211,238,.8)]" />
            Aiva command intelligence
          </div>
          <h1 className="mt-7 max-w-4xl font-display text-5xl font-semibold leading-[0.95] tracking-tight text-white md:text-7xl">
            Build production software with an AI team that can <span className="gradient-text">design, code, test, repair, and launch.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-amk-fg2">
            Aiva turns a prompt into a working product workspace - with specialist agents for UI, code, media, QA, repo work, runtime checks, and launch gates.
          </p>
          <p className="mt-4 max-w-xl text-sm leading-6 text-amk-fg3">
            Describe what you want. Aiva plans it, designs it, builds it, tests it, repairs it, and prepares it for launch.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/access" className="cta-primary inline-flex h-12 items-center gap-2 rounded-2xl px-6 font-mono text-xs uppercase tracking-wider">
              Request Access <ArrowRight className="h-4 w-4" />
            </Link>
            <Link to="/pipeline" className="cta-secondary inline-flex h-12 items-center gap-2 rounded-2xl px-6 font-mono text-xs uppercase tracking-wider">
              See the System <Play className="h-4 w-4" />
            </Link>
          </div>
        </motion.div>
        <CommandCenterMockup />
      </section>

      <SectionShell eyebrow="Production layers" title="One command center. Every production layer.">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {capabilities.map(([title, copy, Icon], index) => (
            <motion.article
              key={title}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ delay: index * 0.04 }}
              className="premium-card rounded-3xl p-6"
            >
              <Icon className="h-6 w-6 text-amk-accent" strokeWidth={1.6} />
              <h3 className="mt-5 font-display text-2xl font-semibold text-white">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-amk-fg2">{copy}</p>
            </motion.article>
          ))}
        </div>
      </SectionShell>

      <SectionShell eyebrow="Agent orchestra" title="Aiva routes the work to the right specialist agents.">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {agents.map(([name, copy], index) => (
            <motion.div
              key={name}
              initial={{ opacity: 0, scale: 0.96 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.03 }}
              className="glass-panel rounded-2xl p-4"
            >
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-amk-accent/25 to-amk-violet/25 text-amk-accent">
                  <Bot className="h-4 w-4" />
                </span>
                <h3 className="font-mono text-xs uppercase tracking-wider text-white">{name}</h3>
              </div>
              <p className="mt-3 text-xs leading-5 text-amk-fg2">{copy}</p>
            </motion.div>
          ))}
        </div>
      </SectionShell>

      <SectionShell id="media" eyebrow="Truth-gated media" title="Media-aware builds, not empty templates.">
        <div className="grid gap-4 lg:grid-cols-4">
          {[
            ["AI image direction", "Provider-backed visuals when runtime calls pass.", Image],
            ["Hero video / motion layer", "Cinematic backgrounds when video evidence exists.", Film],
            ["Voice & avatar-ready experiences", "Interactive surfaces without client-side secret leaks.", Sparkles],
            ["Stock/upload fallback", "Fallbacks are labeled truthfully, never disguised.", ShieldCheck],
          ].map(([title, copy, Icon]) => (
            <article key={title} className="premium-card min-h-64 rounded-3xl p-5">
              <div className="grid h-24 place-items-center rounded-2xl bg-gradient-to-br from-amk-accent/20 via-amk-blue/20 to-amk-violet/20">
                <Icon className="h-8 w-8 text-white" />
              </div>
              <h3 className="mt-5 font-display text-xl font-semibold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-amk-fg2">{copy}</p>
            </article>
          ))}
        </div>
        <div className="mt-6 rounded-3xl border border-amk-amber/30 bg-amk-amber/10 p-5 text-sm leading-6 text-amber-100">
          When a provider fails, the system must say so. Fallback media never pretends to be generated.
        </div>
      </SectionShell>

      <SectionShell id="repo" eyebrow="Developer cockpit" title="From GitHub repo to reviewed pull request.">
        <div className="glass-panel rounded-3xl p-5">
          <div className="grid gap-3 md:grid-cols-7">
            {["Import", "Analyze", "Plan", "Edit", "Diff", "Commit", "PR"].map((step, index) => (
              <div key={step} className="rounded-2xl border border-amk-line bg-amk-base/70 p-4">
                <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">0{index + 1}</div>
                <div className="mt-2 font-display text-lg text-white">{step}</div>
              </div>
            ))}
          </div>
          <div className="mt-5 rounded-2xl bg-black/30 p-4 font-mono text-xs leading-6 text-amk-fg2">
            <div className="text-amk-accent">$ aiva repo plan --truth-gated</div>
            <div>imported repo -> stack analyzed -> files changed -> diff reviewed -> PR ready when configured</div>
          </div>
        </div>
      </SectionShell>

      <SectionShell eyebrow="Runtime truth" title="No fake green lights.">
        <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
          <p className="text-lg leading-8 text-amk-fg2">
            Amarktai separates discovery from execution. A capability is only green after it runs, persists, appears in preview, and passes the final gate.
          </p>
          <div className="flex flex-wrap gap-3">
            {truthBadges.map(([label, color]) => (
              <span key={label} className="status-pill" style={{ color, borderColor: `${color}55`, background: `${color}14` }}>{label}</span>
            ))}
          </div>
        </div>
      </SectionShell>

      <section className="relative mx-auto max-w-7xl px-5 py-24">
        <div className="premium-card rounded-3xl p-8 text-center md:p-12">
          <h2 className="mx-auto max-w-3xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">
            Ready to build with a real AI software team?
          </h2>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/access" className="cta-primary inline-flex h-12 items-center gap-2 rounded-2xl px-6 font-mono text-xs uppercase tracking-wider">
              Request Access <ArrowRight className="h-4 w-4" />
            </Link>
            <Link to="/login" className="cta-secondary inline-flex h-12 items-center gap-2 rounded-2xl px-6 font-mono text-xs uppercase tracking-wider">
              Login
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}

function PublicNav({ user }) {
  return (
    <nav data-testid="landing-nav" className="sticky top-0 z-40 border-b border-amk-line bg-[#030712]/80 backdrop-blur-xl">
      <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-5">
        <Link to="/" className="min-w-0">
          <div className="font-display text-base font-semibold tracking-tight text-white">Amarktai App Builder</div>
          <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-amk-accent">Private AI Software Factory</div>
        </Link>
        <div className="hidden items-center gap-5 font-mono text-[11px] uppercase tracking-wider text-amk-fg2 lg:flex">
          {navItems.map(([label, to]) => <Link key={label} to={to} className="hover:text-white">{label}</Link>)}
        </div>
        <div className="flex items-center gap-2">
          <Link to="/access" className="hidden rounded-xl border border-amk-line px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-amk-fg2 hover:border-amk-accent hover:text-white sm:inline-flex">
            Request Access
          </Link>
          <Link to={user ? "/dashboard" : "/login"} className="rounded-xl bg-white px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-amk-base hover:bg-amk-accent">
            Open Dashboard
          </Link>
        </div>
      </div>
    </nav>
  );
}

function CommandCenterMockup() {
  return (
    <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.65, delay: 0.1 }} className="glass-panel rounded-3xl p-4">
      <div className="rounded-2xl border border-amk-line bg-amk-base/80">
        <div className="flex items-center justify-between border-b border-amk-line px-4 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3">Aiva Command Center</div>
          <div className="flex gap-1.5"><span className="h-2 w-2 rounded-full bg-amk-red" /><span className="h-2 w-2 rounded-full bg-amk-amber" /><span className="h-2 w-2 rounded-full bg-amk-green" /></div>
        </div>
        <div className="grid gap-px bg-amk-line md:grid-cols-[0.88fr_1.12fr]">
          <div className="space-y-3 bg-amk-panel/70 p-4">
            <MockBlock icon={TerminalSquare} title="Prompt input" copy="Build a cinematic product workspace..." color="#22D3EE" />
            <MockBlock icon={Workflow} title="Agent routing" copy="Planner -> Designer -> Coder -> QA" color="#8B5CF6" />
            <MockBlock icon={Film} title="Media pipeline" copy="AI media when providers are live" color="#D946EF" />
            <MockBlock icon={ShieldCheck} title="Final gate" copy="Runtime evidence required" color="#10B981" />
          </div>
          <div className="bg-[#050816] p-4">
            <div className="rounded-2xl border border-amk-line bg-gradient-to-br from-amk-accent/12 via-amk-blue/10 to-amk-violet/16 p-4">
              <div className="grid aspect-[1.45] gap-3">
                <div className="rounded-2xl bg-black/35 p-4">
                  <div className="h-3 w-28 rounded-full bg-amk-accent/80" />
                  <div className="mt-4 h-16 rounded-2xl bg-gradient-to-r from-amk-accent/35 to-amk-violet/35" />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-2xl bg-white/8 p-3"><div className="h-10 rounded-xl bg-amk-blue/35" /></div>
                  <div className="rounded-2xl bg-white/8 p-3"><div className="h-10 rounded-xl bg-amk-magenta/35" /></div>
                  <div className="rounded-2xl bg-white/8 p-3"><div className="h-10 rounded-xl bg-amk-amber/35" /></div>
                </div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {["Provider discovered", "Runtime checked", "Preview visible", "Gate enforced"].map((item, i) => (
                <span key={item} className="status-pill" style={{ color: i === 3 ? "#10B981" : "#22D3EE" }}>{item}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function MockBlock({ icon: Icon, title, copy, color }) {
  return (
    <div className="rounded-2xl border border-amk-line bg-amk-base/70 p-3">
      <div className="flex items-center gap-3">
        <Icon className="h-4 w-4" style={{ color }} />
        <div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-white">{title}</div>
          <div className="mt-1 text-xs text-amk-fg3">{copy}</div>
        </div>
      </div>
    </div>
  );
}

function SectionShell({ id, eyebrow, title, children }) {
  return (
    <section id={id} className="relative mx-auto max-w-7xl px-5 py-16 md:py-20">
      <div className="mb-8 max-w-3xl">
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-amk-accent">{eyebrow}</div>
        <h2 className="mt-3 font-display text-4xl font-semibold leading-tight text-white md:text-5xl">{title}</h2>
      </div>
      {children}
    </section>
  );
}
