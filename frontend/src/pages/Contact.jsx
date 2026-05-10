import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Send, Mail, Github } from "lucide-react";
import { Contact } from "@/lib/amk-api";
import { toast } from "sonner";

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", message: "" });
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await Contact.send(form);
      setSent(true);
      toast.success("Message sent. Talk soon.");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to send message");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-amk-base text-amk-fg flex flex-col">
      <nav className="border-b border-amk-line">
        <div className="max-w-6xl mx-auto h-14 px-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-amk-fg2 hover:text-white font-mono text-xs">
            <ArrowLeft className="w-3.5 h-3.5" strokeWidth={1.5} /> back
          </Link>
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 grid place-items-center border border-amk-line bg-amk-panel">
              <span className="font-mono text-[13px] font-bold">A</span>
            </div>
            <span className="font-display font-semibold tracking-tight">
              Amarktai <span className="text-amk-accent">App Builder</span>
            </span>
          </Link>
          <div />
        </div>
      </nav>

      <main className="flex-1 grid lg:grid-cols-2 max-w-6xl w-full mx-auto">
        <section className="p-8 lg:p-16 border-r border-amk-line">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">[ get in touch ]</div>
          <h1 className="font-display font-semibold text-4xl md:text-5xl tracking-tight leading-[1.05] mb-6">
            Have a question,<br />
            an integration idea,<br />
            <span className="text-amk-accent">or a wild request?</span>
          </h1>
          <p className="text-sm text-amk-fg2 leading-relaxed mb-10 max-w-md">
            Drop us a line. We read everything. Whether it's a bug, a feature wish, an enterprise
            inquiry, or just a hello — we want to hear from you.
          </p>
          <div className="space-y-3 font-mono text-xs">
            <div className="flex items-center gap-3 text-amk-fg2">
              <Mail className="w-3.5 h-3.5 text-amk-accent" strokeWidth={1.5} />
              <a href="mailto:hello@amarktai.io" className="hover:text-white">hello@amarktai.io</a>
            </div>
            <div className="flex items-center gap-3 text-amk-fg2">
              <Github className="w-3.5 h-3.5 text-amk-accent" strokeWidth={1.5} />
              <a href="https://github.com" target="_blank" rel="noreferrer" className="hover:text-white">@amarktai-network</a>
            </div>
          </div>
        </section>

        <section className="p-8 lg:p-16">
          {sent ? (
            <div data-testid="contact-success" className="grid-bg border border-amk-line p-10 text-center min-h-[280px] grid place-items-center">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-accent mb-3">[ delivered ]</div>
                <h3 className="font-display font-semibold text-2xl mb-2">Message sent.</h3>
                <p className="text-sm text-amk-fg2 max-w-xs mx-auto">
                  We'll get back to you at <span className="text-amk-fg">{form.email}</span> shortly.
                </p>
                <button
                  onClick={() => { setSent(false); setForm({ name: "", email: "", message: "" }); }}
                  className="mt-6 inline-flex items-center gap-2 h-10 px-4 border border-amk-line hover:bg-amk-panel font-mono text-xs uppercase tracking-wider"
                >
                  Send another
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4" data-testid="contact-form">
              <Field label="Name" testid="contact-name-input">
                <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-amk-panel border border-amk-line h-11 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                  placeholder="Ada Lovelace" />
              </Field>
              <Field label="Email" testid="contact-email-input">
                <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full bg-amk-panel border border-amk-line h-11 px-3 font-mono text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3"
                  placeholder="ada@example.com" />
              </Field>
              <Field label="Message" testid="contact-message-input">
                <textarea required rows={6} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })}
                  className="w-full bg-amk-panel border border-amk-line p-3 font-sans text-sm focus:outline-none focus:border-white text-amk-fg placeholder:text-amk-fg3 resize-none"
                  placeholder="Tell us what you're trying to build..." />
              </Field>
              <button
                data-testid="contact-submit-btn"
                type="submit"
                disabled={busy}
                className="w-full h-11 bg-white text-black hover:bg-zinc-200 disabled:opacity-50 font-mono text-xs uppercase tracking-wider inline-flex items-center justify-center gap-2"
              >
                {busy ? "Sending..." : (<>Send message <Send className="w-3.5 h-3.5" strokeWidth={2} /></>)}
              </button>
            </form>
          )}
        </section>
      </main>
    </div>
  );
}

function Field({ label, testid, children }) {
  return (
    <div data-testid={testid + "-wrap"}>
      <label className="font-mono text-[10px] uppercase tracking-wider text-amk-fg3 block mb-1.5">{label}</label>
      {children}
    </div>
  );
}
