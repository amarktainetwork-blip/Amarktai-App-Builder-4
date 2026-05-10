import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

export default function TermsPage() {
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
        <h1 className="font-display font-semibold text-4xl tracking-tight mb-2">Terms of Use</h1>
        <p className="font-mono text-xs text-amk-fg3 mb-10">Part of Amarktai Network · <a href="https://amarktai.com" className="hover:text-white" target="_blank" rel="noreferrer">amarktai.com</a></p>

        <div className="space-y-8 text-sm text-amk-fg2 leading-relaxed">
          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">AI-generated output disclaimer</h2>
            <p>
              Amarktai App Builder uses AI models to generate code, content, and other artefacts. All AI-generated
              output must be reviewed by you before use in production. Amarktai Network makes no warranty that
              generated code is correct, secure, or fit for any particular purpose. You are responsible for
              reviewing, testing, and deploying any generated output.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">Your responsibility for generated code</h2>
            <p>
              You are solely responsible for any code generated and deployed using this platform. This includes
              responsibility for security vulnerabilities, licensing compliance, intellectual property, and any
              consequences of deploying AI-generated software.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">API key responsibility</h2>
            <p>
              You are responsible for all usage and costs incurred under your configured API keys (GENX_API_KEY,
              GitHub PAT, or any other keys). Keep your keys secure and do not share them. Amarktai App Builder
              uses your keys only to fulfil actions you explicitly trigger.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">GitHub usage</h2>
            <p>
              When you provide a GitHub Personal Access Token and trigger GitHub actions (repository import, commit,
              or pull request), you are authorising Amarktai App Builder to act on your behalf using that token.
              You are responsible for ensuring your use of GitHub complies with GitHub's Terms of Service.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">Acceptable use</h2>
            <p>
              You must not use Amarktai App Builder to generate content that is illegal, harmful, abusive,
              defamatory, or that infringes the intellectual property rights of others. Misuse of the platform
              may result in account suspension.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">Self-hosted / private beta</h2>
            <p>
              Amarktai App Builder is provided as a self-hosted platform currently in private beta. The service
              is provided "as is" without warranties of any kind. Amarktai Network reserves the right to change
              or discontinue the software at any time.
            </p>
          </section>

          <section>
            <h2 className="font-display font-semibold text-lg text-amk-fg mb-3">Contact</h2>
            <p>
              For questions about these terms, please use the <Link to="/contact" className="text-amk-accent hover:underline">Contact</Link> page
              or visit <a href="https://amarktai.com" className="text-amk-accent hover:underline" target="_blank" rel="noreferrer">amarktai.com</a>.
            </p>
          </section>
        </div>
      </main>

      <footer className="border-t border-amk-line py-8 mt-16">
        <div className="max-w-3xl mx-auto px-5 text-center font-mono text-[11px] text-amk-fg3">
          <span>Amarktai App Builder · Part of Amarktai Network · </span>
          <Link to="/privacy" className="hover:text-white">Privacy</Link>
          <span> · </span>
          <a href="https://amarktai.com" target="_blank" rel="noreferrer" className="hover:text-white">amarktai.com</a>
        </div>
      </footer>
    </div>
  );
}
