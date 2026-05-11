import { useCallback, useEffect, useRef, useState } from "react";
import { Media as MediaApi } from "@/lib/amk-api";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Upload, Search, Trash2, Image as ImageIcon, Film, Music,
  FileText, Code2, RefreshCw, Check, ExternalLink, X
} from "lucide-react";
import { toast } from "sonner";

const SOURCE_LABELS = {
  upload: { label: "Upload", color: "bg-blue-600" },
  pixabay: { label: "Pixabay", color: "bg-yellow-600" },
  genx: { label: "GenX", color: "bg-purple-600" },
  qwen: { label: "Qwen", color: "bg-indigo-600" },
  logo_agent: { label: "Logo", color: "bg-pink-600" },
  css_svg: { label: "SVG", color: "bg-green-600" },
};

const TYPE_ICONS = {
  image: <ImageIcon className="w-4 h-4" />,
  logo: <ImageIcon className="w-4 h-4" />,
  svg: <Code2 className="w-4 h-4" />,
  video: <Film className="w-4 h-4" />,
  audio: <Music className="w-4 h-4" />,
  document: <FileText className="w-4 h-4" />,
};

const TYPE_FILTERS = ["all", "image", "logo", "svg", "video", "audio", "document"];

function AssetCard({ asset, selected, onSelect, onDelete }) {
  const thumbnailUrl = MediaApi.thumbnailUrl(asset.id);
  const source = SOURCE_LABELS[asset.source] || { label: asset.source, color: "bg-gray-600" };
  const isImage = ["image", "logo", "svg"].includes(asset.media_type);

  return (
    <div
      className={`group relative rounded-lg border overflow-hidden cursor-pointer transition-all ${
        selected ? "ring-2 ring-blue-500 border-blue-500" : "border-white/10 hover:border-white/30"
      } bg-white/5`}
      onClick={() => onSelect(asset)}
    >
      {/* Thumbnail */}
      <div className="aspect-video bg-black/30 flex items-center justify-center relative">
        {isImage ? (
          <img
            src={thumbnailUrl}
            alt={asset.original_name}
            className="w-full h-full object-cover"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        ) : (
          <div className="text-white/40">
            {TYPE_ICONS[asset.media_type] || <FileText className="w-8 h-8" />}
          </div>
        )}
        {selected && (
          <div className="absolute top-1 right-1 bg-blue-500 rounded-full p-0.5">
            <Check className="w-3 h-3 text-white" />
          </div>
        )}
        <span className={`absolute bottom-1 left-1 text-xs text-white px-1.5 py-0.5 rounded ${source.color}`}>
          {source.label}
        </span>
      </div>

      {/* Info */}
      <div className="p-2">
        <p className="text-xs text-white/80 truncate" title={asset.original_name}>
          {asset.original_name}
        </p>
        {asset.width > 0 && (
          <p className="text-xs text-white/40">{asset.width}×{asset.height}</p>
        )}
        {asset.attribution?.pageURL && (
          <a
            href={asset.attribution.pageURL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-400 hover:underline flex items-center gap-0.5"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="w-3 h-3" /> Attribution
          </a>
        )}
      </div>

      {/* Delete */}
      <button
        className="absolute top-1 left-1 bg-black/60 hover:bg-red-600 rounded p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={(e) => { e.stopPropagation(); onDelete(asset); }}
        title="Delete asset"
      >
        <Trash2 className="w-3 h-3 text-white" />
      </button>
    </div>
  );
}

export default function MediaLibraryDialog({
  open,
  onOpenChange,
  onSelect,
  projectId,
  selectionMode = false,
}) {
  const [assets, setAssets] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const filters = {};
      if (projectId) filters.project_id = projectId;
      if (typeFilter !== "all") filters.media_type = typeFilter;
      if (search.trim()) filters.q = search.trim();
      const res = await MediaApi.library(filters);
      setAssets(res.assets || []);
      setTotal(res.total || 0);
    } catch (err) {
      toast.error("Failed to load media library");
    } finally {
      setLoading(false);
    }
  }, [projectId, typeFilter, search]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setUploading(true);
    let successCount = 0;
    for (const file of files) {
      try {
        await MediaApi.upload(file, { project_id: projectId });
        successCount++;
      } catch (err) {
        const msg = err.response?.data?.detail || err.message || "Upload failed";
        toast.error(`Failed to upload ${file.name}: ${msg}`);
      }
    }
    if (successCount > 0) {
      toast.success(`${successCount} file(s) uploaded`);
      await load();
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDelete = async (asset) => {
    if (!window.confirm(`Delete "${asset.original_name}"?`)) return;
    try {
      await MediaApi.delete(asset.id);
      toast.success("Asset deleted");
      setAssets((prev) => prev.filter((a) => a.id !== asset.id));
      if (selected?.id === asset.id) setSelected(null);
    } catch (err) {
      toast.error("Failed to delete asset");
    }
  };

  const handleSelect = (asset) => {
    setSelected((prev) => (prev?.id === asset.id ? null : asset));
  };

  const handleConfirmSelect = () => {
    if (selected && onSelect) {
      onSelect(selected);
    }
    onOpenChange(false);
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === "Enter") load();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col bg-[#0a0e1a] border-white/10 text-white">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <ImageIcon className="w-5 h-5 text-blue-400" />
            Media Library
            {total > 0 && (
              <span className="text-xs text-white/40 font-normal ml-1">({total} assets)</span>
            )}
          </DialogTitle>
          <DialogDescription className="text-white/50">
            Upload, browse and manage your media assets. Use uploaded logos in builds.
          </DialogDescription>
        </DialogHeader>

        {/* Toolbar */}
        <div className="flex flex-wrap gap-2 items-center">
          {/* Upload button */}
          <Button
            size="sm"
            className="bg-blue-600 hover:bg-blue-700 text-white"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <RefreshCw className="w-4 h-4 animate-spin mr-1" />
            ) : (
              <Upload className="w-4 h-4 mr-1" />
            )}
            {uploading ? "Uploading..." : "Upload"}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,video/*,audio/*,.svg,.pdf"
            className="hidden"
            onChange={handleUpload}
          />

          {/* Search */}
          <div className="flex items-center gap-1 flex-1 min-w-[160px]">
            <Search className="w-4 h-4 text-white/40" />
            <Input
              className="bg-white/5 border-white/10 text-white placeholder-white/30 text-sm h-8"
              placeholder="Search assets..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={handleSearchKeyDown}
            />
            {search && (
              <button onClick={() => { setSearch(""); }} className="text-white/40 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Refresh */}
          <Button
            variant="ghost"
            size="sm"
            onClick={load}
            className="text-white/40 hover:text-white"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>

        {/* Type filters */}
        <div className="flex gap-1 flex-wrap">
          {TYPE_FILTERS.map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`text-xs px-2 py-1 rounded capitalize transition-colors ${
                typeFilter === t
                  ? "bg-blue-600 text-white"
                  : "bg-white/5 text-white/50 hover:bg-white/10 hover:text-white"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Asset grid */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-white/40">
              <RefreshCw className="w-6 h-6 animate-spin mr-2" /> Loading...
            </div>
          ) : assets.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 gap-3 text-white/40">
              <ImageIcon className="w-10 h-10" />
              <p className="text-sm">No assets yet. Upload your logo or media files.</p>
              <Button
                size="sm"
                variant="outline"
                className="border-white/20 text-white/60 hover:text-white"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="w-4 h-4 mr-1" /> Upload files
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 p-1">
              {assets.map((asset) => (
                <AssetCard
                  key={asset.id}
                  asset={asset}
                  selected={selected?.id === asset.id}
                  onSelect={handleSelect}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {selectionMode && (
          <div className="flex items-center justify-between border-t border-white/10 pt-3 mt-1">
            <div className="text-sm text-white/50">
              {selected ? (
                <span className="text-white">
                  Selected: <strong>{selected.original_name}</strong>{" "}
                  <Badge variant="outline" className="text-xs border-white/20 text-white/60">
                    {selected.media_type}
                  </Badge>
                </span>
              ) : (
                "Click an asset to select it"
              )}
            </div>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="text-white/40"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                className="bg-blue-600 hover:bg-blue-700"
                disabled={!selected}
                onClick={handleConfirmSelect}
              >
                Use Selected
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
