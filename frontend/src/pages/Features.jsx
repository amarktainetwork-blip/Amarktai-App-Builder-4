import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Cpu, Sparkles, GitBranch, ShieldCheck, Image, BarChart3, ArrowRight } from "lucide-react";
import Header from "@/components/Header";

const FEATURES = [
  {
    icon: <Sparkles className="w-5 h-5 text-amk-accent" strokeWidth={1.5} />,
    title: "AI Build Pipeline",
    desc: "Four specialised agents — Scout, Architect, Coder, and Reviewer — collaborate to plan, design, write, and validate your application in a single automated pipeline.",
  },
  {
    icon: <Cpu className="w-5 h-5 text-amk-accent" strokeWidth={1.5} />,
    title: "10+ Build Modes",
    desc: "Choose from landing pages, multi-section websites, PWAs, SaaS dashboards, full-stack apps, API services, automation bots, and more. Each mode is pre-configured for its use case.",
  },
  {
    icon: <GitBranch className="w-5 h-5 text-amk-accent" strokeWidth={1.5} />,
    title: "Repo Import & Fix",
    desc: "Import any existing GitHub repository. Agents analyse the codebase, identify missing or broken files, and produce a branch or pull request with targeted fixes.",
  },
  {
    icon: <ShieldCheck className="w-5 h-5 text-amk-accent" strokeWidth={1.5} />,
    title: "Quality Validation",
    desc: "Every build passes through automated quality, design, and security checks. Scores for accessibility, SEO, responsiveness, and performance are surfaced live in the workspace.",
  },
  {
    icon: <Image className="w-5 h-5 text-amk-accent" strokeWidth={1.5} />,
    title: "Media Library",
    desc: "Search and use Pixabay stock images, AI-generated visuals via GenX/Qwen, or upload your own assets. All media is stored in a project-scoped library.",
  },
  {
    icon: <BarChart3 className="w-5 h-5 text-amk-accent" strokeWidth={1.5} />,
    title: "Live Streaming Workspace",
    desc: "Watch files being written in real time. Chat with the AI during or after a build, iterate with natural language, and preview your app in an inline sandboxed iframe.",
  },
];

const MODES = [
  { label: "Landing Page", badge: "Static" },
  { label: "Website", badge: "Multi-page" },
  { label: "PWA", badge: "Installable" },
  { label: "Web App", badge: "Interactive" },
  { label: "Full-Stack", badge: "Docker" },
  { label: "Dashboard", badge: "Admin" },
  { label: "API Service", badge: "Backend" },
  { label: "Automation Bot", badge: "Worker" },
  { label: "Research", badge: "Report" },
  { label: "Repo Fix", badge: "GitHub" },
];

export default function FeaturesPage() {
  return (
    <div className="min-h-screen bg-amk-base text-amk-fg flex flex-col">
      <Header />

      <main className="flex-1">
        {/* Hero */}
        <section className="border-b border-amk-line py-20 px-6">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            className="max-w-3xl mx-auto text-center"
          >
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">
              [ features ]
            </div>
            <h1 className="font-display font-semibold text-4xl lg:text-5xl tracking-tight leading-[1.1] mb-5">
              Everything you need to<br />
              <span className="text-amk-accent">ship with AI agents.</span>
            </h1>
            <p className="text-base text-amk-fg2 leading-relaxed max-w-xl mx-auto">
              Amarktai App Builder combines specialised AI agents, a real-time streaming workspace,
              and automated quality checks — so you can go from idea to GitHub-ready code in minutes.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link
                to="/access"
                className="inline-flex items-center gap-2 px-5 h-10 bg-amk-accent text-black font-mono text-xs hover:bg-emerald-300 transition-colors"
              >
                Request Access <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
              </Link>
              <Link
                to="/pipeline"
                className="inline-flex items-center gap-2 px-5 h-10 border border-amk-line bg-amk-panel hover:bg-amk-surface font-mono text-xs text-amk-fg hover:text-white transition-colors"
              >
                How the pipeline works
              </Link>
            </div>
          </motion.div>
        </section>

        {/* Feature grid */}
        <section className="py-16 px-6 border-b border-amk-line">
          <div className="max-w-5xl mx-auto">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-8 text-center">
              [ core capabilities ]
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {FEATURES.map(({ icon, title, desc }) => (
                <motion.div
                  key={title}
                  initial={{ opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.25 }}
                  className="border border-amk-line bg-amk-panel p-5"
                >
                  <div className="w-9 h-9 border border-amk-line bg-amk-base grid place-items-center mb-4">
                    {icon}
                  </div>
                  <h3 className="font-mono text-sm font-medium mb-2">{title}</h3>
                  <p className="text-[13px] text-amk-fg2 leading-relaxed">{desc}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Build modes */}
        <section className="py-16 px-6">
          <div className="max-w-4xl mx-auto">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-6 text-center">
              [ build modes ]
            </div>
            <p className="text-center text-sm text-amk-fg2 mb-8">
              Describe what you want to build and pick a mode — agents configure themselves automatically.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {MODES.map(({ label, badge }) => (
                <div
                  key={label}
                  className="inline-flex items-center gap-2 border border-amk-line bg-amk-panel px-3 py-2"
                >
                  <span className="font-mono text-xs text-amk-fg">{label}</span>
                  <span className="font-mono text-[9px] uppercase tracking-wider text-amk-fg3 border border-amk-line px-1.5 py-0.5">
                    {badge}
                  </span>
                </div>
              ))}
            </div>

            <div className="mt-12 text-center">
              <Link
                to="/access"
                className="inline-flex items-center gap-2 px-6 h-11 bg-amk-accent text-black font-mono text-xs hover:bg-emerald-300 transition-colors"
              >
                Get access <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-amk-line py-8 px-6">
        <div className="max-w-5xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="font-mono text-[10px] text-amk-fg3">
            © {new Date().getFullYear()} Amarktai Network
          </div>
          <div className="flex items-center gap-4 font-mono text-[10px]">
            <Link to="/privacy" className="text-amk-fg3 hover:text-white">Privacy</Link>
            <Link to="/terms" className="text-amk-fg3 hover:text-white">Terms</Link>
            <Link to="/contact" className="text-amk-fg3 hover:text-white">Contact</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
