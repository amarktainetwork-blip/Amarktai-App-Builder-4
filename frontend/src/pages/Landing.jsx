import { Link } from "react-router-dom";
import { ArrowRight, Sparkles, GitPullRequest, Network, Boxes, Cpu, Zap, Github, Mail } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export default function LandingPage() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-amk-base text-amk-fg">
      <Nav user={user} />
      <Hero />
      <Marquee />
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
            AmarktAI <span className="text-amk-accent">Network</span>
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
              Open Workspace <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
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
            <span className="pulse-dot bg-amk-accent" /> powered by genx router · 40+ models
          </div>
          <h1 className="font-display font-semibold text-5xl md:text-7xl leading-[0.95] tracking-tight mb-6">
            Describe an app.<br />
            <span className="text-amk-fg2">Watch agents</span><br />
            <span className="text-amk-accent">build it live<span className="blink" /></span>
          </h1>
          <p className="text-base md:text-lg text-amk-fg2 max-w-xl leading-relaxed mb-8">
            AmarktAI Network is your autonomous coding studio. Four specialised agents — Scout,
            Architect, Coder, Reviewer — collaborate over a single GenX key to ship working web
            apps, websites, and pull requests against your GitHub repos. In real-time.
          </p>
          <div className="flex flex-wrap items-center gap-3" data-testid="hero-ctas">
            <Link to="/login" data-testid="hero-cta-primary" className="inline-flex items-center gap-2 h-12 px-6 bg-white text-black hover:bg-zinc-200 font-mono text-xs uppercase tracking-wider">
              Enter the workspace <ArrowRight className="w-4 h-4" strokeWidth={2} />
            </Link>
            <a href="#features" data-testid="hero-cta-secondary" className="inline-flex items-center gap-2 h-12 px-6 border border-amk-line hover:bg-amk-panel font-mono text-xs uppercase tracking-wider text-amk-fg">
              See how it works
            </a>
          </div>
          <div className="mt-10 grid grid-cols-3 gap-6 max-w-md">
            {[
              { v: "40+", k: "models · 1 key" },
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
        <div className="h-9 border-b border-amk-line flex items-center px-3 gap-2 bg-amk-base">
          <span className="w-2 h-2 rounded-full bg-amk-fg3" />
          <span className="w-2 h-2 rounded-full bg-amk-fg3" />
          <span className="w-2 h-2 rounded-full bg-amk-fg3" />
          <span className="ml-3 font-mono text-[10px] text-amk-fg3 uppercase tracking-wider">workspace · live</span>
        </div>
        <div className="p-4 space-y-3 font-mono text-xs">
          {[
            { agent: "Scout",     color: "#FF5722", text: "Researching market patterns…", st: "complete" },
            { agent: "Architect", color: "#2962FF", text: "Designing tech_stack.json", st: "complete" },
            { agent: "Coder",     color: "#00E676", text: "Writing index.html, styles.css, app.js", st: "active" },
            { agent: "Reviewer",  color: "#FFC107", text: "Standing by", st: "idle" },
          ].map((r, i) => (
            <div key={r.agent} className="flex items-center gap-3 px-3 py-2 border-l-2 animate-fade-up" style={{ borderLeftColor: r.color, animationDelay: `${i * 90}ms` }}>
              <span className="pulse-dot" style={{ background: r.color }} />
              <div className="flex-1">
                <div className="text-[11px] uppercase tracking-wider" style={{ color: r.color }}>{r.agent}</div>
                <div className="text-amk-fg2 text-[11px]">{r.text}</div>
              </div>
              <span className="text-amk-fg3 text-[10px] uppercase">{r.st}</span>
            </div>
          ))}
        </div>
        <div className="border-t border-amk-line bg-amk-base/70 p-3 flex items-center gap-3 text-[10px] font-mono text-amk-fg3">
          <Cpu className="w-3 h-3" strokeWidth={1.5} /> claude-sonnet-4-6
          <Zap className="w-3 h-3" strokeWidth={1.5} /> 8.2k tokens
          <span className="ml-auto text-amk-accent">$0.04</span>
        </div>
      </div>
    </div>
  );
}

function Marquee() {
  const items = ["scout", "architect", "coder", "reviewer", "github pr", "genx router", "claude", "gpt-5", "gemini", "grok"];
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

const FEATURES = [
  { icon: Network,        title: "One key. 40+ models.", body: "GenX Router fans your single API key out to Claude, GPT-5, Gemini, and Grok. We pick cheap models for research and edits, premium models for architecture and code." },
  { icon: Boxes,          title: "Modular agentic build", body: "Scout briefs → Architect plans → Coder writes → Reviewer audits. Every step is logged, colour-coded, and replayable." },
  { icon: GitPullRequest, title: "Pull from GitHub. Push a PR.", body: "Paste a public repo URL. Agents iterate. Click Open PR — we fork, commit, and open a pull request against the original." },
  { icon: Sparkles,       title: "Live preview, every keystroke", body: "An inlined-iframe renderer hot-reloads your generated app instantly. Drop in a WebContainer key for full Node sandboxes." },
  { icon: Cpu,            title: "Cost-aware routing", body: "Cheap edits don't burn premium tokens. The token & cost meter is always visible — no surprises at billing time." },
  { icon: Zap,            title: "Real-time WebSockets", body: "Every agent message, file write, and status change streams over a project-scoped socket. The UI never feels stale." },
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
    { n: "01", t: "Describe or import", b: "Type a prompt or paste a public GitHub repo URL." },
    { n: "02", t: "Agents collaborate", b: "Scout, Architect, Coder, Reviewer execute in sequence." },
    { n: "03", t: "Iterate live",       b: "Chat additional changes — preview updates in real-time." },
    { n: "04", t: "Ship a PR",          b: "One click opens a pull request against the original repo." },
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
          Your next app is one prompt away.
        </h2>
        <p className="text-base md:text-lg text-amk-fg2 leading-relaxed mb-10 max-w-xl mx-auto">
          Sign in, paste an idea, and let AmarktAI Network build it for you — running entirely on
          your GenX key, deployed on your VPS.
        </p>
        <Link to="/login" data-testid="cta-primary" className="inline-flex items-center gap-2 h-12 px-7 bg-amk-accent text-black hover:bg-emerald-300 font-mono text-xs uppercase tracking-wider">
          Open the studio <ArrowRight className="w-4 h-4" strokeWidth={2} />
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
          <span className="font-display font-semibold text-amk-fg">AmarktAI Network</span>
          <span>· built on GenX Router</span>
        </div>
        <div className="flex items-center gap-5">
          <Link to="/contact" className="hover:text-white inline-flex items-center gap-1.5">
            <Mail className="w-3 h-3" strokeWidth={1.5} /> Contact
          </Link>
          <a href="https://genx.sh" target="_blank" rel="noreferrer" className="hover:text-white">genx.sh</a>
          <a href="https://github.com" target="_blank" rel="noreferrer" className="hover:text-white inline-flex items-center gap-1.5">
            <Github className="w-3 h-3" strokeWidth={1.5} /> GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}
