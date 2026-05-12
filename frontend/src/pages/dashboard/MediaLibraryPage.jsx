import { useState } from "react";
import { motion } from "framer-motion";
import { Image } from "lucide-react";
import MediaLibraryDialog from "@/components/MediaLibraryDialog";

export default function MediaLibraryPage() {
  const [open, setOpen] = useState(true);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="p-6 lg:p-10 max-w-4xl"
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-amk-fg3 mb-3">
        [ media library ]
      </div>
      <h1 className="font-display font-semibold text-3xl tracking-tight mb-2">
        Media Library
      </h1>
      <p className="text-sm text-amk-fg2 mb-8 leading-relaxed">
        Manage uploaded assets, Pixabay images, and AI-generated visuals.
      </p>

      <button
        data-testid="open-media-library-btn"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 px-5 h-10 border border-amk-line bg-amk-panel hover:bg-amk-surface font-mono text-xs text-amk-fg hover:text-white transition-colors"
      >
        <Image className="w-3.5 h-3.5" strokeWidth={1.5} />
        Open Media Library
      </button>

      <MediaLibraryDialog open={open} onOpenChange={setOpen} />
    </motion.div>
  );
}
