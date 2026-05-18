import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, Lock, Mail } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { toast } from "sonner";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (loading) return null;
  if (user) return <Navigate to="/dashboard" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await login(email.trim().toLowerCase(), password);
      toast.success("Welcome back.");
      nav("/dashboard");
    } catch (e) {
      if (e.response?.status === 401) {
        setErr("Approved users only. The email or password was not accepted.");
      } else if (e.response?.status === 403) {
        setErr(e.response?.data?.detail || "This account is not currently approved for access.");
      } else {
        setErr(e.response?.data?.detail || "Login failed. Check the backend connection and try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cinematic-bg grid min-h-screen text-amk-fg lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-amk-line p-12 lg:flex">
        <div className="premium-orb orb-cyan left-[-12rem] top-16" />
        <div className="premium-orb orb-violet right-[-10rem] bottom-24" />
        <Link to="/" className="relative z-10 flex w-fit items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-2xl border border-amk-line bg-amk-panel/80">
            <span className="font-mono text-[13px] font-bold">A</span>
          </div>
          <span className="font-display font-semibold tracking-tight">
            Amarktai <span className="text-amk-accent">App Builder</span>
          </span>
        </Link>
        <div className="relative z-10 max-w-md">
          <div className="mb-4 font-mono text-[10px] uppercase tracking-[0.22em] text-amk-accent">Private command center</div>
          <h1 className="mb-6 font-display text-4xl font-semibold leading-[1.05] tracking-tight">
            Approved access for<br />
            the Amarktai<br />
            <span className="gradient-text">Software Factory.</span>
          </h1>
          <p className="text-sm leading-relaxed text-amk-fg2">
            Private beta users can start builds, import repos, preview work, and configure provider keys from the dashboard.
          </p>
        </div>
        <div className="relative z-10 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">
          <span>// jwt / bcrypt / tls</span>
        </div>
      </div>

      <div className="grid place-items-center p-6 sm:p-12">
        <div className="glass-panel w-full max-w-md rounded-3xl p-6 sm:p-8" data-testid="login-card">
          <Link to="/" className="mb-10 flex items-center gap-2 lg:hidden">
            <div className="grid h-8 w-8 place-items-center rounded-2xl border border-amk-line bg-amk-panel">
              <span className="font-mono text-[13px] font-bold">A</span>
            </div>
            <span className="font-display font-semibold tracking-tight">
              Amarktai <span className="text-amk-accent">App Builder</span>
            </span>
          </Link>
          <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-amk-accent">Approved users only</div>
          <h2 className="mb-2 font-display text-3xl font-semibold tracking-tight">Login to the private beta</h2>
          <p className="mb-8 text-sm text-amk-fg2">Use the credentials issued after approval. Not approved yet? Request access below.</p>

          <form onSubmit={submit} className="space-y-4" data-testid="login-form">
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-amk-fg3" strokeWidth={1.5} />
                <input
                  data-testid="login-email-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                  autoComplete="email"
                  placeholder="admin@amarktai.io"
                  className="h-11 w-full rounded-2xl border border-amk-line bg-amk-panel pl-10 pr-3 font-mono text-sm text-amk-fg placeholder:text-amk-fg3 focus:border-amk-accent focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-amk-fg3">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-amk-fg3" strokeWidth={1.5} />
                <input
                  data-testid="login-password-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="password"
                  className="h-11 w-full rounded-2xl border border-amk-line bg-amk-panel pl-10 pr-3 font-mono text-sm text-amk-fg placeholder:text-amk-fg3 focus:border-amk-accent focus:outline-none"
                />
              </div>
            </div>
            {err && (
              <div data-testid="login-error" className="flex items-start gap-2 rounded-2xl border border-red-900/60 bg-red-950/40 px-3 py-2 font-mono text-[11px] text-red-300">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                <span>{err}</span>
              </div>
            )}
            <button
              data-testid="login-submit-btn"
              type="submit"
              disabled={busy}
              className="cta-primary inline-flex h-11 w-full items-center justify-center gap-2 rounded-2xl font-mono text-xs uppercase tracking-wider disabled:opacity-50"
            >
              {busy ? "Signing in..." : (<>Sign in <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} /></>)}
            </button>
          </form>
          <p className="mt-8 font-mono text-[10px] leading-relaxed text-amk-fg3">
            Need access? <Link to="/access" className="text-amk-accent hover:text-white">Request Access</Link>.
          </p>
        </div>
      </div>
    </div>
  );
}
