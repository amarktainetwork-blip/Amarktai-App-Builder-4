import { File, FileCode, FileJson, FileText } from "lucide-react";
import { fileLanguage } from "@/lib/agents";

const ICONS = {
  html: FileCode, css: FileCode, javascript: FileCode, typescript: FileCode,
  json: FileJson, markdown: FileText,
};

export default function FileTree({ files, activePath, onSelect }) {
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));
  return (
    <div data-testid="file-tree" className="border-r border-amk-line bg-amk-base/50 overflow-y-auto scroll-thin">
      <div className="px-3 pt-3 pb-2 sticky top-0 bg-amk-base/95 backdrop-blur-sm border-b border-amk-line">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-amk-fg3">
          Files <span className="text-amk-fg2">({sorted.length})</span>
        </span>
      </div>
      {sorted.length === 0 && (
        <div className="px-3 py-6 text-center font-mono text-[11px] text-amk-fg3">
          [ no files yet ]
        </div>
      )}
      <ul className="py-1">
        {sorted.map((f) => {
          const lang = f.language || fileLanguage(f.path);
          const Icon = ICONS[lang] || File;
          const active = f.path === activePath;
          return (
            <li key={f.path}>
              <button
                data-testid={`file-row-${f.path}`}
                onClick={() => onSelect(f.path)}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-left font-mono text-[11px] hover:bg-amk-surface ${
                  active ? "bg-amk-surface text-white border-l-2 border-white" : "text-amk-fg2"
                }`}
                style={{ borderLeftColor: active ? "#FAFAFA" : "transparent" }}
              >
                <Icon className="w-3.5 h-3.5 shrink-0 text-amk-fg3" strokeWidth={1.5} />
                <span className="truncate">{f.path}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
