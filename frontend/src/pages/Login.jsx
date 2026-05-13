import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ArrowRight, Lock, Mail, AlertCircle } from "lucide-react";
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
    <div className="min-h-screen grid lg:grid-cols-2 bg-amk-base">
      {/* Left visual */}
      <div className="hidden lg:flex relative hero-glow hero-grain border-r border-amk-line p-12 flex-col justify-between overflow-hidden">
        <Link to="/" className="flex items-center gap-2.5 relative z-10 w-fit">
          <div className="w-7 h-7 grid place-items-center border border-amk-line bg-amk-panel">
            <span className="font-mono text-[13px] font-bold">A</span>
          </div>
          <span className="font-display font-semibold tracking-tight">
            Amarktai <span className="text-amk-accent">App Builder</span>
          </span>
        </Link>
        <div className="relative z-10 max-w-md">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">[ approved users only ]</div>
          <h1 className="font-display font-semibold text-4xl tracking-tight leading-[1.05] mb-6">
            Single-tenant.<br />
            Single-key.<br />
            <span className="text-amk-accent">Single-admin.</span>
          </h1>
          <p className="text-sm text-amk-fg2 leading-relaxed">
            Private beta users can start builds, import repos, preview work, and configure provider keys from the dashboard.
          </p>
        </div>
        <div className="relative z-10 font-mono text-[10px] text-amk-fg3 uppercase tracking-wider">
          <span className="blink">// jwt · bcrypt · tls</span>
        </div>
      </div>

      {/* Right form */}
      <div className="grid place-items-center p-6 sm:p-12">
        <div className="w-full max-w-sm" data-testid="login-card">
          <Link to="/" className="lg:hidden flex items-center gap-2 mb-10">
            <div className="w-7 h-7 grid place-items-center border border-amk-line bg-amk-panel">
              <span className="font-mono text-[13px] font-bold">A</span>
            </div>
            <span className="font-display font-semibold tracking-tight">
              Amarktai <span className="text-amk-accent">App Builder</span>
            </span>
          </Link>
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">[ approved users only ]</div>
          <h2 className="font-display font-semibold text-3xl tracking-tight mb-2">Login to the private beta</h2>
          <p className="text-sm text-amk-fg2 mb-8">Use the credentials issued after approval. Not approved yet? Request access below.</p>

          <form onSubmit={submit} className="space-y-4" data-testid="login-form">
            <div>
              <label className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 block mb-1.5">Email</label>
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-amk-fg3" strokeWidth={1.5} />
                <input
                  data-testid="login-email-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                  autoComplete="email"
                  placeholder="admin@amarktai.io"
                  className="w-full bg-amk-panel border border-amk-line h-11 pl-10 pr-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                />
              </div>
            </div>
            <div>
              <label className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 block mb-1.5">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-amk-fg3" strokeWidth={1.5} />
                <input
                  data-testid="login-password-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••••••"
                  className="w-full bg-amk-panel border border-amk-line h-11 pl-10 pr-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                />
              </div>
            </div>
            {err && (
              <div data-testid="login-error" className="flex items-start gap-2 px-3 py-2 border border-red-900/60 bg-red-950/40 text-red-300 font-mono text-[11px]">
                <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" strokeWidth={1.5} />
                <span>{err}</span>
              </div>
            )}
            <button
              data-testid="login-submit-btn"
              type="submit"
              disabled={busy}
              className="w-full h-11 bg-white text-black hover:bg-zinc-200 disabled:opacity-50 font-mono text-xs uppercase tracking-wider inline-flex items-center justify-center gap-2"
            >
              {busy ? "Signing in..." : (<>Sign in <ArrowRight className="w-3.5 h-3.5" strokeWidth={2} /></>)}
            </button>
          </form>
          <p className="font-mono text-[10px] text-amk-fg3 mt-8 leading-relaxed">
            Need access? <Link to="/access" className="text-amk-accent hover:text-white">Request Access</Link>.
          </p>
        </div>
      </div>
    </div>
  );
}
