import { Link } from "react-router-dom";
import { ArrowRight, Boxes, Code2, Eye, GitBranch, Image, ShieldCheck } from "lucide-react";
import CapabilityStatus from "@/components/CapabilityStatus";

const features = [
  { icon: Boxes, title: "Agent workspace", copy: "Manager and specialist agents coordinate planning, code, QA, repair, media, runtime, memory, versioning, and deployment tasks." },
  { icon: Code2, title: "Prompt-first build flow", copy: "Create websites, web apps, dashboards, APIs, full-stack scaffolds, and repo-fix workspaces through the routed dashboard." },
  { icon: GitBranch, title: "Repo workbench", copy: "Public repo import, stack analysis, preview fallback, coverage, and PR workflows. Private repo and PR actions require GITHUB_PAT." },
  { icon: Image, title: "Media library", copy: "Uploads are always real assets. GenX, Qwen, Brave, and Pixabay features are shown according to configured provider keys." },
  { icon: Eye, title: "Live preview", copy: "Preview generation is available for previewable builds through a scoped preview token and honest fallback panels." },
  { icon: ShieldCheck, title: "QA, versioning, rollback", copy: "Validation, repair loops, project memory, versions, and rollback support keep iteration auditable." },
];

export default function FeaturesPage() {
  return (
    <main className="min-h-screen bg-amk-base text-amk-fg">
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <Link to="/" className="font-display text-lg tracking-tight text-white">Amarktai App Builder</Link>
        <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
          <Link to="/pipeline" className="hover:text-white">Pipeline</Link>
          <Link to="/access" className="border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Request Access</Link>
        </div>
      </nav>

      <section className="border-y border-amk-line">
        <div className="mx-auto max-w-7xl px-6 py-16 md:py-24">
          <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Truthful capabilities</p>
          <h1 className="mt-5 max-w-4xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">
            What the private software factory can actually do.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-amk-fg2 md:text-lg">
            Core workspace, runtime, preview, repo import, agents, settings, memory, and versioning are real product surfaces. Provider-backed claims stay setup-aware.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-14">
        <div className="grid gap-px border border-amk-line bg-amk-line md:grid-cols-2 xl:grid-cols-3">
          {features.map(({ icon: Icon, title, copy }) => (
            <article key={title} className="bg-amk-panel p-6">
              <Icon className="h-6 w-6 text-amk-accent" strokeWidth={1.5} />
              <h2 className="mt-5 font-display text-xl text-white">{title}</h2>
              <p className="mt-3 text-sm leading-6 text-amk-fg2">{copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-20">
        <CapabilityStatus />
        <Link to="/access" className="mt-8 inline-flex h-11 items-center gap-2 bg-amk-accent px-5 font-mono text-xs uppercase tracking-wider text-black hover:bg-emerald-300">
          Request Access <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
    </main>
  );
}
