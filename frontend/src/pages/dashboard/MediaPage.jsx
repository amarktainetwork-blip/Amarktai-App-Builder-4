import { useCallback, useEffect, useRef, useState } from "react";
import { Code2, FileText, Film, Image as ImageIcon, Music, RefreshCw, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Media } from "@/lib/amk-api";

const FILTERS = ["all", "image", "logo", "svg", "video", "audio", "document"];

export default function MediaPage() {
  const [assets, setAssets] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");
  const [search, setSearch] = useState("");
  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const filters = {};
      if (typeFilter !== "all") filters.media_type = typeFilter;
      if (search.trim()) filters.q = search.trim();
      const result = await Media.library(filters);
      setAssets(result.assets || []);
      setTotal(result.total || 0);
    } catch {
      toast.error("Failed to load media library");
    } finally {
      setLoading(false);
    }
  }, [search, typeFilter]);

  useEffect(() => { load(); }, [load]);

  const upload = async (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    setUploading(true);
    let uploaded = 0;
    for (const file of files) {
      try {
        await Media.upload(file);
        uploaded += 1;
      } catch (err) {
        toast.error(err.response?.data?.detail || `Failed to upload ${file.name}`);
      }
    }
    if (uploaded) toast.success(`${uploaded} file(s) uploaded`);
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
    load();
  };

  const remove = async (asset) => {
    if (!window.confirm(`Delete "${asset.original_name}"?`)) return;
    try {
      await Media.delete(asset.id);
      setAssets((prev) => prev.filter((item) => item.id !== asset.id));
      toast.success("Asset deleted");
    } catch {
      toast.error("Failed to delete asset");
    }
  };

  return (
    <section className="border border-amk-line bg-amk-panel">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-amk-line p-5">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-amk-fg3">Media</div>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-white">Media library</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-amk-fg2">Uploaded assets are available to builds. Generated, Qwen, GenX, and Pixabay assets appear only when their providers are configured and produce real files.</p>
        </div>
        <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="inline-flex h-10 items-center gap-2 bg-amk-accent px-4 font-mono text-xs uppercase tracking-wider text-black hover:bg-emerald-300 disabled:opacity-50">
          {uploading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {uploading ? "Uploading" : "Upload"}
        </button>
        <input ref={fileInputRef} type="file" multiple accept="image/*,video/*,audio/*,.svg,.pdf" className="hidden" onChange={upload} />
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-amk-line p-4">
        <input value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") load(); }} placeholder="Search assets..." className="h-9 min-w-[220px] flex-1 border border-amk-line bg-amk-base px-3 font-mono text-xs text-white outline-none focus:border-white" />
        <button onClick={load} className="inline-flex h-9 items-center gap-2 border border-amk-line px-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg3 hover:bg-amk-base hover:text-white">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-amk-line p-3">
        {FILTERS.map((filter) => (
          <button key={filter} onClick={() => setTypeFilter(filter)} className={`h-8 shrink-0 border px-3 font-mono text-[10px] uppercase tracking-wider ${typeFilter === filter ? "border-amk-accent bg-amk-accent/10 text-amk-accent" : "border-amk-line text-amk-fg3 hover:bg-amk-base hover:text-white"}`}>
            {filter}
          </button>
        ))}
      </div>

      <div className="p-4">
        <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{total} assets</div>
        {loading ? (
          <div className="grid h-40 place-items-center font-mono text-xs text-amk-fg3">Loading media...</div>
        ) : assets.length === 0 ? (
          <div className="grid h-44 place-items-center border border-amk-line bg-amk-base text-center">
            <div>
              <ImageIcon className="mx-auto h-8 w-8 text-amk-fg3" />
              <p className="mt-3 text-sm text-amk-fg2">No assets yet. Upload a logo, image, video, audio file, SVG, or document.</p>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {assets.map((asset) => <AssetCard key={asset.id} asset={asset} onDelete={() => remove(asset)} />)}
          </div>
        )}
      </div>
    </section>
  );
}

function AssetCard({ asset, onDelete }) {
  const Icon = iconFor(asset.media_type);
  const isImage = ["image", "logo", "svg"].includes(asset.media_type);
  return (
    <article className="group overflow-hidden border border-amk-line bg-amk-base">
      <div className="grid aspect-video place-items-center bg-black/30">
        {isImage ? (
          <img src={Media.thumbnailUrl(asset.id)} alt={asset.original_name} className="h-full w-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
        ) : (
          <Icon className="h-8 w-8 text-amk-fg3" />
        )}
      </div>
      <div className="flex items-start justify-between gap-3 p-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-xs text-white" title={asset.original_name}>{asset.original_name}</div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-amk-fg3">{asset.source || "upload"} / {asset.media_type}</div>
        </div>
        <button onClick={onDelete} className="shrink-0 text-amk-fg3 hover:text-red-300" aria-label="delete asset"><Trash2 className="h-3.5 w-3.5" /></button>
      </div>
    </article>
  );
}

function iconFor(type) {
  if (type === "video") return Film;
  if (type === "audio") return Music;
  if (type === "svg") return Code2;
  if (type === "document") return FileText;
  return ImageIcon;
}
