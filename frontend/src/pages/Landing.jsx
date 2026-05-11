import { Link } from "react-router-dom";
import { ArrowRight, Sparkles, GitPullRequest, Network, Boxes, Zap, Mail, Cpu } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export default function LandingPage() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-amk-base text-amk-fg">
      <Nav user={user} />
      <Hero />
      <Marquee />
      <WhatYouCanBuild />
      <Features />
      <Pipeline />
      <CTA />
      <Footer />
    </div>
  );
}

function Nav({ user }) {
  return (
    <nav data-testid="landing-nav" className="sticky top-0 z-40 border-b border-amk-line bg-amk-base/85 backdrop-blur-md">
      <div className="max-w-6xl mx-auto h-14 px-5 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 grid place-items-center border border-amk-line bg-amk-panel">
            <span className="font-mono text-[13px] font-bold">A</span>
          </div>
          <span className="font-display font-semibold tracking-tight">
            Amarktai <span className="text-amk-accent">App Builder</span>
          </span>
        </Link>
        <div className="hidden md:flex items-center gap-8 font-mono text-xs text-amk-fg2">
          <a href="#features" className="hover:text-white transition-colors">Features</a>
          <a href="#pipeline" className="hover:text-white transition-colors">Pipeline</a>
          <Link to="/contact" className="hover:text-white transition-colors">Contact</Link>
        </div>
        <div className="flex items-center gap-2">
          {user ? (
            <Link to="/app" data-testid="nav-app-btn" className="inline-flex items-center gap-2 h-9 px-4 bg-white text-black hover:bg-zinc-200 font-mono text-xs">
              Open Dashboard <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
            </Link>
          ) : (
            <Link to="/login" data-testid="nav-login-btn" className="inline-flex items-center gap-2 h-9 px-4 bg-white text-black hover:bg-zinc-200 font-mono text-xs">
              Sign In <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <section className="relative hero-glow hero-grain overflow-hidden">
      <div className="max-w-6xl mx-auto px-5 pt-20 pb-24 md:pt-28 md:pb-36 grid lg:grid-cols-12 gap-10 items-center relative z-10">
        <div className="lg:col-span-7 animate-fade-up">
          <div className="inline-flex items-center gap-2 mb-6 px-3 h-7 border border-amk-line bg-amk-panel/60 font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg2">
            <span className="pulse-dot bg-amk-accent" /> Amarktai App Builder · by Amarktai Network
          </div>
          <h1 className="font-display font-semibold text-5xl md:text-7xl leading-[0.95] tracking-tight mb-6">
            Build websites, apps,<br />
            <span className="text-amk-fg2">and GitHub-ready</span><br />
            <span className="text-amk-accent">projects from one prompt.<span className="blink" /></span>
          </h1>
          <p className="text-base md:text-lg text-amk-fg2 max-w-xl leading-relaxed mb-6">
            Amarktai App Builder plans, designs, codes, validates, previews, and prepares your project
            for GitHub using AmarktAI model routing behind the scenes.
            60+ AI models available through configured providers.
          </p>
          {/* Capability chips */}
          <div className="flex flex-wrap gap-1.5 mb-8">
            {[
              "Landing pages", "Multi-page sites", "PWAs", "SaaS starters",
              "Dashboards", "API services", "Repo upgrades", "Media + logos", "GitHub PRs",
            ].map((chip) => (
              <span
                key={chip}
                className="font-mono text-[10px] uppercase tracking-wider px-2.5 py-1 border border-amk-line bg-amk-panel/60 text-amk-fg2"
              >
                {chip}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3" data-testid="hero-ctas">
            <Link to="/login" data-testid="hero-cta-primary" className="inline-flex items-center gap-2 h-12 px-6 bg-white text-black hover:bg-zinc-200 font-mono text-xs uppercase tracking-wider">
              Enter the workspace <ArrowRight className="w-4 h-4" strokeWidth={2} />
            </Link>
            <a href="#features" data-testid="hero-cta-secondary" className="inline-flex items-center gap-2 h-12 px-6 border border-amk-line hover:bg-amk-panel font-mono text-xs uppercase tracking-wider text-amk-fg">
              See how it works
            </a>
          </div>
          <ul className="mt-5 space-y-1 font-mono text-[11px] text-amk-fg3">
            <li>· Preview before deploy. Request changes before finalizing.</li>
            <li>· Quality, design, security, and coverage checks keep incomplete builds from shipping.</li>
          </ul>
          <div className="mt-10 grid grid-cols-3 gap-6 max-w-md">
            {[
              { v: "60+", k: "models · configured providers" },
              { v: "4", k: "agents · 1 prompt" },
              { v: "PR", k: "→ github · live" },
            ].map((s) => (
              <div key={s.k}>
                <div className="font-display text-2xl font-semibold">{s.v}</div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{s.k}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="lg:col-span-5 animate-fade-up" style={{ animationDelay: "120ms" }}>
          <HeroPreviewCard />
        </div>
      </div>
    </section>
  );
}

function HeroPreviewCard() {
  return (
    <div className="relative">
      <div className="absolute -inset-4 bg-gradient-to-tr from-agent-coder/20 via-agent-architect/10 to-transparent blur-2xl" aria-hidden />
      <div className="relative border border-amk-line bg-amk-panel rounded-md overflow-hidden shadow-2xl shadow-black/40">
        {/* Title bar */}
        <div className="h-9 border-b border-amk-line flex items-center px-3 gap-2 bg-amk-base">
          <span className="w-2 h-2 rounded-full bg-amk-fg3" />
          <span className="w-2 h-2 rounded-full bg-amk-fg3" />
          <span className="w-2 h-2 rounded-full bg-amk-fg3" />
          <span className="ml-3 font-mono text-[10px] text-amk-fg3 uppercase tracking-wider">amarktai workspace · live</span>
        </div>
        {/* Prompt bubble */}
        <div className="px-4 pt-3 pb-2">
          <div className="bg-amk-base border border-amk-line rounded px-3 py-2 font-mono text-[11px] text-amk-fg2">
            <span className="text-amk-fg3">prompt › </span>
            <span className="text-white">Complete BMW dealership website, 6 pages, dark theme</span>
            <span className="blink ml-0.5 text-amk-accent">|</span>
          </div>
        </div>
        {/* Agent rows */}
        <div className="px-4 pt-1 pb-2 space-y-1.5 font-mono text-xs">
          {[
            { agent: "Scout",     color: "#FF5722", text: "Requirements & audience analysed", st: "complete", delay: 0 },
            { agent: "Architect", color: "#2962FF", text: "6-page plan · styles.css · manifest", st: "complete", delay: 100 },
            { agent: "Coder",     color: "#00E676", text: "Writing inventory.html, contact.html…", st: "active",   delay: 200 },
            { agent: "Reviewer",  color: "#FFC107", text: "Awaiting Coder output",              st: "idle",     delay: 300 },
          ].map((r) => (
            <div
              key={r.agent}
              className="flex items-center gap-3 px-3 py-1.5 border-l-2 animate-fade-up"
              style={{ borderLeftColor: r.color, animationDelay: `${r.delay}ms` }}
            >
              <span
                className={r.st === "active" ? "pulse-dot" : "w-2 h-2 rounded-full shrink-0"}
                style={{ background: r.st === "idle" ? "#333" : r.color }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-[11px] uppercase tracking-wider" style={{ color: r.color }}>{r.agent}</div>
                <div className="text-amk-fg2 text-[11px] truncate">{r.text}</div>
              </div>
              <span className="text-amk-fg3 text-[10px] uppercase shrink-0">{r.st}</span>
            </div>
          ))}
        </div>
        {/* File chips */}
        <div className="px-4 pb-2 flex flex-wrap gap-1.5">
          {["index.html", "inventory.html", "styles.css", "about.html", "contact.html", "README.md"].map((f, i) => (
            <span
              key={f}
              className="font-mono text-[10px] px-2 py-0.5 border border-amk-line text-amk-fg3 animate-fade-up"
              style={{ animationDelay: `${300 + i * 60}ms` }}
            >
              {f}
            </span>
          ))}
        </div>
        {/* Validation scores */}
        <div className="border-t border-amk-line bg-amk-base/70 px-4 py-2 flex items-center gap-4 text-[10px] font-mono">
          <span className="text-amk-fg3">Validate</span>
          {[
            { label: "Quality", v: 92, color: "#00E676" },
            { label: "Design",  v: 88, color: "#2962FF" },
            { label: "Security", v: 95, color: "#FFC107" },
          ].map((s) => (
            <span key={s.label} className="flex items-center gap-1">
              <span style={{ color: s.color }}>{s.label}</span>
              <span className="text-white">{s.v}</span>
            </span>
          ))}
          <span className="ml-auto text-amk-accent">→ PR ready</span>
        </div>
      </div>
    </div>
  );
}

function Marquee() {
  const items = ["scout", "architect", "coder", "reviewer", "github pr", "Amarktai Network", "Amarktai Assistant", "Amarktai Coding Agents"];
  return (
    <div data-testid="logo-marquee" className="border-y border-amk-line py-5 overflow-hidden">
      <div className="flex gap-12 whitespace-nowrap animate-[marquee_25s_linear_infinite]" style={{ animation: "scroll 30s linear infinite" }}>
        {[...items, ...items, ...items].map((t, i) => (
          <span key={i} className="font-mono text-xs text-amk-fg3 uppercase tracking-[0.25em]">// {t}</span>
        ))}
      </div>
      <style>{`
        @keyframes scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
      `}</style>
    </div>
  );
}

function WhatYouCanBuild() {
  const items = [
    "Landing Pages", "Multi-page Websites", "PWAs", "Dashboards",
    "SaaS Starters", "APIs / Backends", "Admin Panels", "Repo Upgrades",
  ];
  return (
    <div data-testid="what-you-can-build" className="border-b border-amk-line py-8">
      <div className="max-w-6xl mx-auto px-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">
          [ what you can build ]
        </div>
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <span
              key={item}
              className="font-mono text-[11px] uppercase tracking-wider px-3 py-1.5 border border-amk-line bg-amk-panel/60 text-amk-fg2 hover:text-white hover:bg-amk-surface transition-colors duration-150"
            >
              {item}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

const FEATURES = [
  { icon: Network,        title: "One key. Amarktai routed.", body: "GENX_API_KEY is the only required key. 60+ AI models are available through configured providers, routing research, design, code, and review automatically." },
  { icon: Boxes,          title: "Four-agent build pipeline", body: "Scout researches → Architect plans → Coder writes → Reviewer audits. Every step is logged, colour-coded, and replayable." },
  { icon: GitPullRequest, title: "GitHub import & PR workflow", body: "Paste a GitHub repo URL to import, analyze, fix, and open a pull request. Agents preserve your existing stack and architecture." },
  { icon: Sparkles,       title: "Validate before you finalize", body: "Quality, design, security, and coverage are scored before you can finalize. Incomplete or broken sites are blocked from shipping." },
  { icon: Cpu,            title: "Honest live preview", body: "A secure iframe renderer refreshes generated files instantly. Preview exists only when validated build files are present — never faked." },
  { icon: Zap,            title: "Iterate with natural language", body: "Chat change requests after a build. Agents apply all requested changes, report satisfied vs unsatisfied, and refresh the preview." },
];

function Features() {
  return (
    <section id="features" className="py-24 md:py-32 border-b border-amk-line">
      <div className="max-w-6xl mx-auto px-5">
        <div className="max-w-2xl mb-16">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">[ capabilities ]</div>
          <h2 className="font-display font-semibold text-3xl md:text-5xl tracking-tight leading-tight mb-4">
            Built like a serious developer tool.<br />
            <span className="text-amk-fg2">Feels like an instant idea machine.</span>
          </h2>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-px bg-amk-line border border-amk-line">
          {FEATURES.map((f) => (
            <div key={f.title} className="bg-amk-base p-7 hover:bg-amk-panel transition-colors duration-150">
              <f.icon className="w-5 h-5 mb-5 text-amk-accent" strokeWidth={1.5} />
              <h3 className="font-display font-medium text-lg mb-2 tracking-tight">{f.title}</h3>
              <p className="text-sm text-amk-fg2 leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Pipeline() {
  const steps = [
    { n: "01", t: "Describe what you want", b: "Type a prompt for a website, PWA, dashboard, API, or SaaS app — or paste a GitHub repo URL to import and fix." },
    { n: "02", t: "Agents collaborate",     b: "Scout, Architect, Coder, Reviewer execute in sequence. Every file and event streams live." },
    { n: "03", t: "Preview & iterate",      b: "Validate quality, design, and coverage. Chat changes — agents apply all requests and report what was satisfied." },
    { n: "04", t: "Finalize to GitHub",     b: "One click opens a pull request against your repo. Only validated builds can be finalized." },
  ];
  return (
    <section id="pipeline" className="py-24 md:py-32 border-b border-amk-line">
      <div className="max-w-6xl mx-auto px-5 grid lg:grid-cols-12 gap-12">
        <div className="lg:col-span-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">[ workflow ]</div>
          <h2 className="font-display font-semibold text-3xl md:text-5xl tracking-tight leading-tight mb-4">
            From prompt to PR in four moves.
          </h2>
          <p className="text-sm text-amk-fg2 leading-relaxed">
            Every step is auditable, every artefact is yours. Self-hosted, single-key, fully under
            your control.
          </p>
        </div>
        <ol className="lg:col-span-8 grid sm:grid-cols-2 gap-px bg-amk-line border border-amk-line">
          {steps.map((s) => (
            <li key={s.n} className="bg-amk-base p-7 hover:bg-amk-panel transition-colors">
              <div className="flex items-baseline gap-3 mb-3">
                <span className="font-mono text-3xl font-bold text-amk-accent">{s.n}</span>
                <h3 className="font-display font-medium text-lg tracking-tight">{s.t}</h3>
              </div>
              <p className="text-sm text-amk-fg2 leading-relaxed">{s.b}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="py-24 md:py-32 grid-bg">
      <div className="max-w-3xl mx-auto px-5 text-center">
        <h2 className="font-display font-semibold text-4xl md:text-6xl tracking-tight leading-none mb-6">
          Your next app is one clear prompt away.
        </h2>
        <p className="text-base md:text-lg text-amk-fg2 leading-relaxed mb-10 max-w-xl mx-auto">
          Sign in, describe what you want to build, and let four Amarktai agents plan, design, code,
          review, and prepare it for GitHub — running on your AI key.
        </p>
        <Link to="/login" data-testid="cta-primary" className="inline-flex items-center gap-2 h-12 px-7 bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs uppercase tracking-wider">
          Open the dashboard <ArrowRight className="w-4 h-4" strokeWidth={2} />
        </Link>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer data-testid="landing-footer" className="border-t border-amk-line py-10">
      <div className="max-w-6xl mx-auto px-5 flex flex-col md:flex-row items-center justify-between gap-4 text-amk-fg3 font-mono text-[11px]">
        <div className="flex items-center gap-2">
          <span className="font-display font-semibold text-amk-fg">Amarktai App Builder</span>
          <span>· Part of Amarktai Network</span>
        </div>
        <div className="flex items-center gap-5">
          <a href="https://amarktai.com" target="_blank" rel="noreferrer" className="hover:text-white">amarktai.com</a>
          <Link to="/privacy" className="hover:text-white">Privacy</Link>
          <Link to="/terms" className="hover:text-white">Terms</Link>
          <Link to="/contact" className="hover:text-white inline-flex items-center gap-1.5">
            <Mail className="w-3 h-3" strokeWidth={1.5} /> Contact
          </Link>
        </div>
      </div>
    </footer>
  );
}
