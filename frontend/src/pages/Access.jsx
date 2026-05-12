import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";

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
    <main className="min-h-screen bg-amk-base text-amk-fg">
      <section className="relative overflow-hidden border-b border-amk-line bg-[radial-gradient(circle_at_top_right,rgba(0,230,118,0.18),transparent_32%),linear-gradient(180deg,#07110d,#050706)]">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link to="/" className="font-display text-lg tracking-tight text-white">Amarktai Builder</Link>
          <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.18em] text-amk-fg3">
            <Link to="/features" className="hover:text-white">Features</Link>
            <Link to="/pipeline" className="hover:text-white">Pipeline</Link>
            <Link to="/login" className="border border-amk-line px-3 py-2 text-amk-fg hover:border-amk-accent hover:text-white">Approved Login</Link>
          </div>
        </nav>

        <div className="mx-auto grid max-w-7xl gap-10 px-6 py-20 md:grid-cols-[1.1fr_0.9fr] md:py-28">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.28em] text-amk-accent">Restricted private access</p>
            <h1 className="mt-5 max-w-3xl font-display text-4xl font-semibold leading-tight text-white md:text-6xl">
              Access the private AI software factory.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-amk-fg2 md:text-lg">
              Amarktai Builder is currently invitation-based while runtime infrastructure, repo orchestration and advanced media systems continue scaling.
            </p>

            <div className="mt-10 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-amk-line bg-amk-panel/70 p-5">
                <LockKeyhole className="h-6 w-6 text-amk-accent" strokeWidth={1.5} />
                <h2 className="mt-4 font-display text-xl text-white">Private onboarding</h2>
                <p className="mt-2 text-sm leading-6 text-amk-fg2">Approved users receive access to the dashboard, repo workbench, runtime previews and agent workspace.</p>
              </div>
              <div className="rounded-2xl border border-amk-line bg-amk-panel/70 p-5">
                <ShieldCheck className="h-6 w-6 text-amk-accent" strokeWidth={1.5} />
                <h2 className="mt-4 font-display text-xl text-white">Truthful capability states</h2>
                <p className="mt-2 text-sm leading-6 text-amk-fg2">Features are exposed according to real configured providers and runtime capability checks.</p>
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-amk-line bg-amk-panel/90 p-6 shadow-2xl shadow-black/30">
            {submitted ? (
              <div className="space-y-4">
                <div className="font-mono text-xs uppercase tracking-[0.24em] text-amk-accent">Request received</div>
                <h2 className="font-display text-3xl text-white">Thanks. We’ll review your request.</h2>
                <p className="text-sm leading-6 text-amk-fg2">
                  If approved, you’ll receive onboarding instructions and access details.
                </p>
              </div>
            ) : (
              <form className="space-y-5" onSubmit={handleSubmit}>
                <div>
                  <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3">Name</label>
                  <input required name="name" className="w-full border border-amk-line bg-amk-base px-4 py-3 text-sm text-white outline-none transition focus:border-amk-accent" />
                </div>

                <div>
                  <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3">Email</label>
                  <input required type="email" name="email" className="w-full border border-amk-line bg-amk-base px-4 py-3 text-sm text-white outline-none transition focus:border-amk-accent" />
                </div>

                <div>
                  <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.2em] text-amk-fg3">What do you want to build?</label>
                  <textarea required name="project" rows={4} className="w-full border border-amk-line bg-amk-base px-4 py-3 text-sm text-white outline-none transition focus:border-amk-accent" />
                </div>

                <button type="submit" className="inline-flex items-center gap-2 border border-amk-accent px-5 py-3 font-mono text-xs uppercase tracking-[0.2em] text-amk-accent transition hover:bg-amk-accent hover:text-black">
                  Request Access <ArrowRight className="h-4 w-4" />
                </button>
              </form>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
