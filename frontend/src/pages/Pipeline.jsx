import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Search, Cpu, Code2, ShieldCheck, GitBranch, CheckCircle2 } from "lucide-react";
import Header from "@/components/Header";

const STAGES = [
  {
    id: "01",
    icon: <Search className="w-5 h-5 text-[#00E676]" strokeWidth={1.5} />,
    agent: "Scout Agent",
    color: "#00E676",
    title: "Research & Discovery",
    bullets: [
      "Analyses your prompt and infers intent, target audience, and required features.",
      "Identifies the optimal technology stack using a capability-weighted decision engine.",
      "Runs optional Brave Search research to ground recommendations in current patterns.",
      "Produces a structured brief: requirements, tech stack, pages, and feature spec.",
    ],
  },
  {
    id: "02",
    icon: <Cpu className="w-5 h-5 text-[#FFC107]" strokeWidth={1.5} />,
    agent: "Architect Agent",
    color: "#FFC107",
    title: "Architecture & Planning",
    bullets: [
      "Converts the Scout brief into a concrete build plan with phases and deliverables.",
      "Defines component hierarchy, routing structure, data flow, and API contracts.",
      "Selects media strategy (AI-generated, Pixabay stock, or CSS/SVG).",
      "Emits a build plan event visible in real time on the workspace timeline.",
    ],
  },
  {
    id: "03",
    icon: <Code2 className="w-5 h-5 text-[#29B6F6]" strokeWidth={1.5} />,
    agent: "Coder Agent",
    color: "#29B6F6",
    title: "Code Generation",
    bullets: [
      "Writes all application files following the Architect's plan and Scout's requirements.",
      "Streams each file write to the workspace as it happens.",
      "Applies the design signature: colour palette, typography, spacing, and motion.",
      "Handles images, icons, CSS, JavaScript, HTML, and configuration files.",
    ],
  },
  {
    id: "04",
    icon: <ShieldCheck className="w-5 h-5 text-[#AB47BC]" strokeWidth={1.5} />,
    agent: "Reviewer/Repair Agent",
    color: "#AB47BC",
    title: "Review, Validate & Repair",
    bullets: [
      "Runs quality, design, security, accessibility, SEO, and performance checks.",
      "Scores every dimension from 0–100 and surfaces results in the workspace.",
      "Automatically patches files that fail validation (up to 3 repair passes).",
      "Locks GitHub finalize if scores fall below acceptable thresholds.",
    ],
  },
  {
    id: "05",
    icon: <GitBranch className="w-5 h-5 text-[#FF7043]" strokeWidth={1.5} />,
    agent: "Finalization",
    color: "#FF7043",
    title: "GitHub Push & PR",
    bullets: [
      "Creates or updates a GitHub repository using a stored Personal Access Token.",
      "Pushes all generated files to the default branch or a feature branch.",
      "Optionally opens a pull request with a build summary and change description.",
      "Handles name collisions gracefully — rename or branch-PR workflow.",
    ],
  },
];

export default function PipelinePage() {
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
              [ pipeline ]
            </div>
            <h1 className="font-display font-semibold text-4xl lg:text-5xl tracking-tight leading-[1.1] mb-5">
              How agents build<br />
              <span className="text-amk-accent">your application.</span>
            </h1>
            <p className="text-base text-amk-fg2 leading-relaxed max-w-xl mx-auto">
              The Amarktai build pipeline runs four specialised AI agents in sequence.
              Each agent has a defined contract, produces structured outputs, and hands
              off to the next with full context.
            </p>
          </motion.div>
        </section>

        {/* Pipeline stages */}
        <section className="py-16 px-6 border-b border-amk-line">
          <div className="max-w-3xl mx-auto">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-10 text-center">
              [ stages ]
            </div>

            <div className="space-y-6">
              {STAGES.map(({ id, icon, agent, color, title, bullets }, i) => (
                <motion.div
                  key={id}
                  initial={{ opacity: 0, x: -12 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.28, delay: i * 0.04 }}
                  className="border border-amk-line bg-amk-panel p-6"
                >
                  <div className="flex items-start gap-4">
                    <div
                      className="w-10 h-10 border bg-amk-base grid place-items-center shrink-0 mt-0.5"
                      style={{ borderColor: color + "40" }}
                    >
                      {icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-1">
                        <span className="font-mono text-[10px] text-amk-fg3">
                          {id}
                        </span>
                        <span
                          className="font-mono text-[10px] uppercase tracking-wider"
                          style={{ color }}
                        >
                          {agent}
                        </span>
                      </div>
                      <h3 className="font-mono text-sm font-medium mb-3">
                        {title}
                      </h3>
                      <ul className="space-y-1.5">
                        {bullets.map((b, j) => (
                          <li key={j} className="flex items-start gap-2 text-[13px] text-amk-fg2">
                            <CheckCircle2
                              className="w-3.5 h-3.5 shrink-0 mt-0.5"
                              strokeWidth={1.5}
                              style={{ color }}
                            />
                            {b}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="py-16 px-6 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">
            [ get started ]
          </div>
          <h2 className="font-display font-semibold text-2xl tracking-tight mb-4">
            Ready to build your next app?
          </h2>
          <p className="text-sm text-amk-fg2 mb-8 max-w-md mx-auto">
            Request access to Amarktai App Builder and start shipping with AI agents today.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/access"
              className="inline-flex items-center gap-2 px-5 h-10 bg-amk-accent text-black font-mono text-xs hover:bg-emerald-300 transition-colors"
            >
              Request Access <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} />
            </Link>
            <Link
              to="/features"
              className="inline-flex items-center gap-2 px-5 h-10 border border-amk-line bg-amk-panel hover:bg-amk-surface font-mono text-xs text-amk-fg hover:text-white transition-colors"
            >
              See all features
            </Link>
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
