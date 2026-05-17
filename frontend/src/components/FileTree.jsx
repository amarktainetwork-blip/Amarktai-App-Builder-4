import { File, FileCode, FileJson, FileText } from "lucide-react";
import { fileLanguage } from "@/lib/agents";

const ICONS = {
  html: FileCode, css: FileCode, javascript: FileCode, typescript: FileCode,
  json: FileJson, markdown: FileText,
};

export default function FileTree({ files, activePath, onSelect }) {
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));
  const groups = [
    ["App source", sorted.filter((f) => !isReportFile(f.path) && !isMediaFile(f.path))],
    ["Reports / manifests", sorted.filter((f) => isReportFile(f.path))],
    ["Media / assets", sorted.filter((f) => isMediaFile(f.path))],
  ].filter(([, items]) => items.length > 0);
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
      <div className="py-1">
        {groups.map(([label, items]) => (
          <div key={label}>
            <div className="px-3 py-1 font-mono text-[9px] uppercase tracking-wider text-amk-fg3">{label}</div>
            {items.map((f) => {
          const lang = f.language || fileLanguage(f.path);
          const Icon = ICONS[lang] || File;
          const active = f.path === activePath;
          return (
            <div key={f.path}>
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
            </div>
          );
        })}
          </div>
        ))}
      </div>
    </div>
  );
}

function isReportFile(path = "") {
  return /(?:report|manifest|runtime-qa|quality|accessibility|lighthouse|coverage)/i.test(path);
}

function isMediaFile(path = "") {
  return /(?:^|\/)(media|assets)\//i.test(path) || /\.(png|jpe?g|webp|gif|mp4|webm|mp3|wav|ogg)$/i.test(path);
}
