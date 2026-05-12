import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { LogIn, Lock, Send, CheckCircle2, AlertTriangle } from "lucide-react";
import Header from "@/components/Header";
import { api } from "@/lib/amk-api";

export default function AccessPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState("idle"); // "idle" | "submitting" | "success" | "error"
  const [errorMsg, setErrorMsg] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !reason.trim()) return;
    setStatus("submitting");
    setErrorMsg("");
    try {
      await api.post("/access/request", {
        name: name.trim(),
        email: email.trim(),
        reason: reason.trim(),
      });
      setStatus("success");
    } catch (err) {
      const detail = err.response?.data?.detail;
      setErrorMsg(
        typeof detail === "string"
          ? detail
          : "Request could not be submitted. Please try again or contact us directly."
      );
      setStatus("error");
    }
  };

  return (
    <div className="min-h-screen bg-amk-base text-amk-fg flex flex-col">
      <Header />

      <main className="flex-1 flex flex-col">
        {/* Hero */}
        <section className="border-b border-amk-line py-16 px-6">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
            className="max-w-2xl mx-auto text-center"
          >
            <div className="inline-flex items-center gap-2 border border-amk-line bg-amk-panel px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-5">
              <Lock className="w-3 h-3" strokeWidth={1.5} />
              Restricted Access
            </div>
            <h1 className="font-display font-semibold text-4xl lg:text-5xl tracking-tight leading-[1.1] mb-5">
              Request access to<br />
              <span className="text-amk-accent">Amarktai App Builder.</span>
            </h1>
            <p className="text-base text-amk-fg2 leading-relaxed">
              Amarktai App Builder is currently invite-only. Fill in the form below and we will
              review your request. Approved users receive login credentials by email.
            </p>
          </motion.div>
        </section>

        {/* Two-column layout */}
        <section className="flex-1 py-14 px-6">
          <div className="max-w-4xl mx-auto grid lg:grid-cols-2 gap-10">
            {/* Left: already approved */}
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-5">
                [ already approved ]
              </div>
              <p className="text-sm text-amk-fg2 mb-6 leading-relaxed">
                If you have already been approved and received your credentials, sign in to your account.
              </p>
              <Link
                to="/login"
                className="inline-flex items-center gap-2 px-5 h-10 bg-amk-accent text-black font-mono text-xs hover:bg-emerald-300 transition-colors"
              >
                <LogIn className="w-3.5 h-3.5" strokeWidth={2} />
                Sign in to your account
              </Link>

              <div className="mt-10 space-y-3">
                <div className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3">
                  [ what you get ]
                </div>
                {[
                  "Full AI build pipeline: Scout, Architect, Coder, Reviewer",
                  "10+ build modes: landing pages, PWAs, full-stack apps, APIs",
                  "Live streaming workspace with real-time file writes",
                  "GitHub integration: auto-push, branch and PR creation",
                  "Media library with Pixabay and AI-generated visuals",
                  "Quality and security scoring on every build",
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2 text-[13px] text-amk-fg2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-amk-accent shrink-0 mt-0.5" strokeWidth={1.5} />
                    {item}
                  </div>
                ))}
              </div>
            </div>

            {/* Right: request form */}
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-5">
                [ request access ]
              </div>

              {status === "success" ? (
                <motion.div
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="border border-amk-accent/40 bg-amk-panel p-6 text-center"
                >
                  <CheckCircle2 className="w-8 h-8 text-amk-accent mx-auto mb-3" strokeWidth={1.5} />
                  <p className="font-mono text-sm text-amk-fg mb-1">Request submitted.</p>
                  <p className="text-[13px] text-amk-fg2 leading-relaxed">
                    We will review your request and contact you at <strong>{email}</strong>.
                  </p>
                </motion.div>
              ) : (
                <form onSubmit={submit} className="space-y-4">
                  <div>
                    <label className="block font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-1.5">
                      Full name
                    </label>
                    <input
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Jane Smith"
                      className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                    />
                  </div>
                  <div>
                    <label className="block font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-1.5">
                      Email address
                    </label>
                    <input
                      required
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="jane@example.com"
                      className="w-full bg-amk-panel border border-amk-line h-10 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                    />
                  </div>
                  <div>
                    <label className="block font-mono text-[10px] uppercase tracking-wider text-amk-fg3 mb-1.5">
                      What are you building?
                    </label>
                    <textarea
                      required
                      rows={4}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Briefly describe your use case and what you would like to build with Amarktai App Builder."
                      className="w-full bg-amk-panel border border-amk-line p-3 font-sans text-sm resize-none focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                    />
                  </div>

                  {status === "error" && (
                    <div className="flex items-start gap-2 border border-red-900 bg-red-950/30 px-3 py-2 text-[12px] text-red-400 font-mono">
                      <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" strokeWidth={1.5} />
                      {errorMsg}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={status === "submitting" || !name.trim() || !email.trim() || !reason.trim()}
                    className="inline-flex items-center gap-2 px-5 h-10 bg-amk-accent text-black font-mono text-xs hover:bg-emerald-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Send className="w-3.5 h-3.5" strokeWidth={2} />
                    {status === "submitting" ? "Submitting…" : "Submit Request"}
                  </button>
                </form>
              )}
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
