import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-amk-base text-amk-fg">
      <nav className="sticky top-0 z-40 border-b border-amk-line bg-amk-base/85 backdrop-blur-md">
        <div className="max-w-3xl mx-auto h-14 px-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 grid place-items-center border border-amk-line bg-amk-panel">
              <span className="font-mono text-[13px] font-bold">A</span>
            </div>
            <span className="font-display font-semibold tracking-tight">
              Amarktai <span className="text-amk-accent">App Builder</span>
            </span>
          </Link>
          <Link to="/" className="inline-flex items-center gap-1.5 font-mono text-xs text-amk-fg2 hover:text-white transition-colors">
            <ArrowLeft className="w-3.5 h-3.5" strokeWidth={2} /> Back
          </Link>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-5 py-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-4">[ legal ]</div>
        <h1 className="font-display font-semibold text-4xl tracking-tight mb-2">Privacy Policy</h1>
        <p className="font-mono text-xs text-amk-fg3 mb-10">Part of Amarktai Network · <a href="https://amarktai.com" className="hover:text-white" target="_blank" rel="noreferrer">amarktai.com</a></p>

        <div className="space-y-8 text-sm text-amk-fg2 leading-relaxed">
          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">What we collect</h2>
            <p>
              Amarktai App Builder stores the account information you provide (email address and hashed password),
              the projects and files you generate, your settings preferences, and usage events associated with your
              account. We do not collect any personally identifiable information beyond what is necessary to operate
              the service.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">We do not sell your data</h2>
            <p>
              We do not sell, rent, or share your personal data or project data with third parties for marketing
              or advertising purposes. Your project content belongs to you.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">API key storage</h2>
            <p>
              API keys you configure in Settings (such as your GENX_API_KEY, GitHub Personal Access Token, or
              Brave Search API key) are encrypted at rest using AES-128 Fernet symmetric encryption before being
              stored in the database. Keys are decrypted in memory only when needed to make API requests on your
              behalf. We do not log or expose your API keys.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">GitHub token usage</h2>
            <p>
              If you provide a GitHub Personal Access Token, it is used exclusively to: import repositories you
              specify, push commits and open pull requests on your behalf, and perform repository operations you
              explicitly trigger. We do not access any GitHub repositories beyond those you direct us to.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">AI model requests</h2>
            <p>
              Prompts and project context are sent to the AI provider (via your configured API key) to generate
              code and content. These requests are governed by the AI provider's own privacy policy. We recommend
              reviewing the policies of any AI provider whose key you configure.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">Self-hosted deployment</h2>
            <p>
              Amarktai App Builder is a self-hosted platform. All data is stored in your own MongoDB instance
              running on infrastructure you control. Amarktai Network does not have access to your self-hosted
              instance's data unless you explicitly share it with us for support purposes.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">Contact</h2>
            <p>
              For privacy inquiries, please use the <Link to="/contact" className="text-amk-accent hover:underline">Contact</Link> page
              or reach out via <a href="https://amarktai.com" className="text-amk-accent hover:underline" target="_blank" rel="noreferrer">amarktai.com</a>.
            </p>
          </section>
        </div>
      </main>

      <footer className="border-t border-amk-line py-8 mt-16">
        <div className="max-w-3xl mx-auto px-5 text-center font-mono text-[11px] text-amk-fg3">
          <span>Amarktai App Builder · Part of Amarktai Network · </span>
          <Link to="/terms" className="hover:text-white">Terms</Link>
          <span> · </span>
          <a href="https://amarktai.com" target="_blank" rel="noreferrer" className="hover:text-white">amarktai.com</a>
        </div>
      </footer>
    </div>
  );
}
