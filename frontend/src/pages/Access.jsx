import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, LockKeyhole, ShieldCheck, Sparkles } from "lucide-react";

export default function AccessPage() {
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const payload = Object.fromEntries(formData.entries());
    try {
      const response = await fetch("/api/access/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("request_failed");
      setSubmitted(true);
    } catch {
      window.location.href = "mailto:amarktainetwork@gmail.com?subject=Builder%20Access%20Request";
    }
  }

  return (
    <main className="cinematic-bg min-h-screen text-amk-fg">
      <nav className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <Link to="/" className="font-display text-lg font-semibold tracking-tight text-white">Amarktai App Builder</Link>
        <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
          <Link to="/features" className="hover:text-white">Features</Link>
          <Link to="/pipeline" className="hover:text-white">Pipeline</Link>
          <Link to="/login" className="rounded-xl border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Login</Link>
        </div>
      </nav>

      <section className="relative mx-auto grid max-w-7xl gap-10 px-6 py-16 md:py-24 lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Private beta access</p>
          <h1 className="mt-5 max-w-4xl font-display text-5xl font-semibold leading-tight text-white md:text-7xl">
            Build with a serious AI software command center.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-amk-fg2">
            For founders, operators, studios, and engineering teams who need working product spaces, repo workflows, media-aware pages, and launch evidence.
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-2">
            <Info title="Access includes" icon={Sparkles} items={["Amarktai Command Center", "New builds and workspaces", "Repo Workbench", "Media Studio", "Runtime QA and final gates"]} />
            <Info title="Approval checks" icon={ShieldCheck} items={["Use case clarity", "Responsible build intent", "Provider setup needs", "Team fit", "Beta capacity"]} />
          </div>
          <div className="mt-6 rounded-3xl border border-amk-amber/30 bg-amk-amber/10 p-5 text-sm leading-6 text-amber-100">
            Truthful beta note: some provider-backed capabilities require live keys and runtime proof before they appear as available.
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          {submitted ? (
            <div className="space-y-4">
              <CheckCircle2 className="h-10 w-10 text-amk-green" />
              <div className="font-mono text-xs uppercase tracking-[0.24em] text-amk-accent">Request received</div>
              <h2 className="font-display text-3xl text-white">We will review your request.</h2>
              <p className="text-sm leading-6 text-amk-fg2">If approved, you will receive onboarding instructions and dashboard access details.</p>
            </div>
          ) : (
            <form className="space-y-5" onSubmit={handleSubmit}>
              <div className="flex items-center gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-amk-accent/15 text-amk-accent">
                  <LockKeyhole className="h-5 w-5" />
                </div>
                <div>
                  <div className="font-display text-2xl text-white">Request access</div>
                  <div className="text-sm text-amk-fg3">Tell us what you want to build.</div>
                </div>
              </div>
              <Field label="Name"><input required name="name" className="field-input rounded-2xl" /></Field>
              <Field label="Email"><input required type="email" name="email" className="field-input rounded-2xl" /></Field>
              <Field label="Who is it for?"><input name="audience" className="field-input rounded-2xl" placeholder="Founder, agency, product team, operations..." /></Field>
              <Field label="What do you want to build?">
                <textarea required name="project" rows={5} className="field-input resize-none rounded-2xl leading-6" placeholder="A cinematic website, a SaaS dashboard, an API service, a repo repair workflow..." />
              </Field>
              <button type="submit" className="cta-primary inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl px-6 font-mono text-xs uppercase tracking-wider">
                Request Access <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}

function Info({ title, icon: Icon, items }) {
  return (
    <div className="premium-card rounded-3xl p-5">
      <Icon className="h-6 w-6 text-amk-accent" />
      <h2 className="mt-4 font-display text-xl font-semibold text-white">{title}</h2>
      <ul className="mt-4 space-y-2">
        {items.map((item) => (
          <li key={item} className="flex items-center gap-2 text-sm text-amk-fg2">
            <CheckCircle2 className="h-4 w-4 text-amk-green" /> {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Field({ label, children }) {
  return <label className="block"><span className="mb-2 block font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3">{label}</span>{children}</label>;
}
