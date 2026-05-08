import { useEffect, useState } from "react";
import { Projects } from "@/lib/emergent-api";
import { Copy, Check } from "lucide-react";

export default function CodeViewer({ projectId, path }) {
  const [content, setContent] = useState("");
  const [lang, setLang] = useState("text");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!path) return;
    setLoading(true);
    Projects.fileContent(projectId, path)
      .then((d) => { setContent(d.content || ""); setLang(d.language || "text"); })
      .finally(() => setLoading(false));
  }, [projectId, path]);

  const copy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  if (!path) {
    return (
      <div data-testid="code-viewer-empty" className="grid-bg h-full grid place-items-center font-mono text-[11px] text-emergent-fg3">
        [ select a file to view ]
      </div>
    );
  }

  return (
    <div data-testid="code-viewer" className="h-full flex flex-col">
      <div className="h-9 border-b border-emergent-line bg-emergent-base flex items-center justify-between px-3 shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-emergent-fg">{path}</span>
          <span className="font-mono text-[10px] text-emergent-fg3 uppercase">{lang}</span>
        </div>
        <button
          data-testid="copy-code-btn"
          onClick={copy}
          className="font-mono text-[10px] uppercase tracking-wider text-emergent-fg3 hover:text-white inline-flex items-center gap-1.5 px-2 h-6 border border-emergent-line"
        >
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <div className="flex-1 overflow-auto scroll-thin bg-emergent-panel">
        {loading ? (
          <div className="p-4 font-mono text-[11px] text-emergent-fg3">[ loading... ]</div>
        ) : (
          <pre className="p-4 font-mono text-[12px] leading-relaxed text-emergent-fg whitespace-pre">
            {content}
          </pre>
        )}
      </div>
    </div>
  );
}
