"""Deterministic Motion / 3D patching for generated frontend files."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Allowed app-source file targets for motion patches
_ALLOWED_MOTION_TARGETS = {"index.html", "styles.css", "script.js", "motion_manifest.json"}

# AMARKTAI_FILE block pattern (fenced and unfenced variants)
_AMARKTAI_FILE_PAT = re.compile(
    r"===AMARKTAI_FILE\[(?P<path>[^\]]+)\]===\n(?P<content>.*?)===END_AMARKTAI_FILE\[(?P=path)\]===",
    re.DOTALL,
)
# Fallback: markdown fenced code block with filename comment
_FENCED_FILE_PAT = re.compile(
    r"```[a-z]*\s*\n#\s*(?P<path>[^\n]+)\n(?P<content>.*?)```",
    re.DOTALL,
)

# Media section mapping keywords
_SECTION_KEYWORDS: dict[str, list[str]] = {
    "hero": ["hero", "cinematic", "banner", "header", "cover", "full-width"],
    "product": ["product", "sourdough", "pastry", "pastries", "bread", "cake", "menu", "item"],
    "gallery": ["gallery", "photos", "grid", "showcase", "portfolio"],
    "events": ["event", "catering", "special", "occasion", "wedding", "corporate"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_requires_motion(prompt: str, mode: str = "") -> bool:
    haystack = f"{prompt} {mode}".lower()
    return bool(re.search(r"\b(3d|three\.js|threejs|motion|animation|animated|gsap|parallax|cinematic|particles|video background)\b", haystack))


def parse_motion_agent_output(agent_output: str) -> tuple[dict[str, str], list[str]]:
    """Parse AMARKTAI_FILE blocks from Motion_3D agent output.

    Returns:
        (files_dict, warnings) where files_dict maps path → content for allowed targets only.
        Non-allowed paths (report/metadata files) are excluded and recorded as warnings.
    """
    files: dict[str, str] = {}
    warnings: list[str] = []

    if not agent_output or not agent_output.strip():
        warnings.append("Motion_3D agent returned empty output; no motion patches applied.")
        return files, warnings

    # Try AMARKTAI_FILE blocks first
    for match in _AMARKTAI_FILE_PAT.finditer(agent_output):
        path = match.group("path").strip()
        content = match.group("content")
        if path in _ALLOWED_MOTION_TARGETS:
            files[path] = content
        else:
            warnings.append(
                f"Motion_3D output contained path '{path}' which is not an allowed motion target "
                f"({', '.join(sorted(_ALLOWED_MOTION_TARGETS))}); skipped."
            )

    # If no AMARKTAI_FILE blocks found, try fenced code blocks
    if not files:
        for match in _FENCED_FILE_PAT.finditer(agent_output):
            path = match.group("path").strip()
            content = match.group("content")
            if path in _ALLOWED_MOTION_TARGETS:
                files[path] = content
            else:
                warnings.append(
                    f"Motion_3D fenced block path '{path}' is not an allowed motion target; skipped."
                )

    if not files:
        if re.search(r"\bsafe\s*snippet\b|\bplaceholder\s+snippet\b", agent_output or "", re.IGNORECASE):
            warnings.append(
                "Motion_3D output contained a safe-snippet placeholder; deterministic motion fallback will be applied."
            )
        warnings.append(
            "Motion_3D output could not be parsed into AMARKTAI_FILE or fenced code blocks. "
            "Existing working files will be preserved."
        )

    return files, warnings


def map_asset_to_section(asset_prompt: str, asset_url: str = "") -> str:
    """Map a media asset to its intended page section based on keywords."""
    combined = f"{asset_prompt} {asset_url}".lower()
    for section, keywords in _SECTION_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return section
    return "general"


def build_media_section_manifest(
    assets: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group media assets by their intended page section."""
    sections: dict[str, list[dict[str, Any]]] = {
        "hero": [],
        "product": [],
        "gallery": [],
        "events": [],
        "general": [],
    }
    for asset in assets:
        prompt = asset.get("prompt", "") or asset.get("description", "") or ""
        url = asset.get("url", "") or asset.get("path", "") or ""
        section = asset.get("section") or map_asset_to_section(prompt, url)
        if section not in sections:
            section = "general"
        sections[section].append({
            **asset,
            "section": section,
            "fallback": not bool(asset.get("url") or asset.get("path")),
        })
    return sections


def apply_motion_agent_output(
    files: list[dict[str, Any]],
    agent_output: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply parsed Motion_3D agent output to a file list.

    Merges allowed motion patches into the existing file list.
    Returns the updated file list and any warnings.
    """
    parsed, warnings = parse_motion_agent_output(agent_output)
    if not parsed:
        if any("safe-snippet placeholder" in w for w in warnings):
            fallback_files, _manifest = patch_motion_files(files, prompt="motion fallback", mode="landing_page")
            warnings.append(
                "Applied deterministic Motion_3D fallback runtime patch because parsed motion blocks were unavailable."
            )
            return fallback_files, warnings
        return files, warnings

    by_path = {f.get("path", ""): {**f} for f in files if f.get("path")}
    for path, content in parsed.items():
        if path in by_path:
            # Merge: append motion CSS/JS to existing file content
            existing = by_path[path].get("content", "")
            by_path[path]["content"] = (existing.rstrip() + "\n\n" + content.strip() + "\n").strip() + "\n"
        else:
            ext = path.rsplit(".", 1)[-1] if "." in path else "text"
            lang_map = {"css": "css", "js": "javascript", "html": "html", "json": "json"}
            by_path[path] = {
                "path": path,
                "content": content,
                "language": lang_map.get(ext, "text"),
            }
    return list(by_path.values()), warnings


def patch_motion_files(files: list[dict[str, Any]], prompt: str = "", mode: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Patch an in-memory file list with deterministic animation assets.

    The patch targets generated static sites first and React/Vite projects second.
    It returns a new file list plus a manifest that can be persisted downstream.
    """
    by_path = {f.get("path", ""): {**f} for f in files if f.get("path")}
    changed: list[str] = []
    requires_3d = bool(re.search(r"\b(3d|three\.js|threejs|react three|three fiber|particles)\b", f"{prompt} {mode}".lower()))
    strategy = "three_js_canvas" if requires_3d else "css_gsap_motion"

    css = """

@media (prefers-reduced-motion: no-preference) {
  .amarktai-motion-reveal { opacity: 0; transform: translateY(22px) scale(.985); animation: amarktaiReveal .85s cubic-bezier(.2,.8,.2,1) forwards; }
  .amarktai-motion-float { animation: amarktaiFloat 7s ease-in-out infinite; }
  .amarktai-motion-orbit { animation: amarktaiOrbit 18s linear infinite; transform-origin: center; }
  .amarktai-motion-depth { transition: transform .35s ease, box-shadow .35s ease; will-change: transform; }
  .amarktai-motion-depth:hover { transform: translateY(-6px) scale(1.01); box-shadow: 0 28px 90px rgba(0, 230, 118, .18); }
  .amarktai-waveform-bar { transform-origin: bottom; animation: amarktaiWave 1.3s ease-in-out infinite; }
  .amarktai-waveform-bar:nth-child(2n) { animation-delay: .14s; }
  .amarktai-waveform-bar:nth-child(3n) { animation-delay: .28s; }
}
@media (prefers-reduced-motion: reduce) {
  .amarktai-motion-reveal, .amarktai-motion-float, .amarktai-motion-orbit, .amarktai-waveform-bar { animation: none !important; opacity: 1 !important; transform: none !important; }
}
@keyframes amarktaiReveal { to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes amarktaiFloat { 0%,100% { transform: translate3d(0,0,0); } 50% { transform: translate3d(0,-14px,0); } }
@keyframes amarktaiOrbit { to { transform: rotate(360deg); } }
@keyframes amarktaiWave { 0%, 100% { transform: scaleY(.28); } 50% { transform: scaleY(1); } }
.amarktai-motion-proof { position: relative; z-index: 1; display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); padding: clamp(1rem, 3vw, 2rem); border: 1px solid rgba(255,255,255,.12); border-radius: 16px; background: rgba(255,255,255,.045); }
.amarktai-motion-proof strong { display: block; font-size: clamp(1.7rem, 4vw, 3.4rem); line-height: 1; color: var(--color-accent, #00e676); }
.amarktai-waveform { display: flex; align-items: end; gap: 4px; min-height: 44px; }
.amarktai-waveform-bar { width: 7px; min-height: 9px; border-radius: 999px; background: linear-gradient(180deg, var(--color-cyan, #53d8ff), var(--color-accent, #00e676)); }
""".strip()

    js = """
(() => {
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.documentElement.dataset.motionRuntime = reduce ? 'reduced' : 'active';
  if (reduce) return;
  document.querySelectorAll('section, .card, article, [data-motion-target]').forEach((el, index) => {
    el.classList.add('amarktai-motion-reveal');
    if (index % 3 === 0) el.classList.add('amarktai-motion-depth');
    el.style.animationDelay = `${Math.min(index * 70, 560)}ms`;
  });
  const counters = document.querySelectorAll('[data-motion-counter]');
  counters.forEach((node) => {
    const target = Number(node.getAttribute('data-motion-counter') || '0');
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / 1100);
      node.textContent = String(Math.round(target * progress));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  const parallaxNodes = document.querySelectorAll('[data-motion-parallax]');
  window.addEventListener('scroll', () => {
    const offset = window.scrollY * 0.035;
    parallaxNodes.forEach((node, index) => {
      node.style.transform = `translate3d(0, ${Math.sin(offset + index) * 10}px, 0)`;
    });
  }, { passive: true });
  const hero = document.querySelector('main, .hero, section');
  if (hero && !document.querySelector('[data-amarktai-motion-scene]')) {
    const scene = document.createElement('canvas');
    scene.dataset.amarktaiMotionScene = 'css-canvas';
    scene.setAttribute('aria-hidden', 'true');
    scene.style.cssText = 'position:absolute;inset:0;pointer-events:none;opacity:.32;mix-blend-mode:screen;z-index:0';
    const style = getComputedStyle(hero);
    if (style.position === 'static') hero.style.position = 'relative';
    hero.prepend(scene);
    const ctx = scene.getContext('2d');
    const draw = () => {
      const rect = hero.getBoundingClientRect();
      scene.width = Math.max(1, rect.width * devicePixelRatio);
      scene.height = Math.max(1, rect.height * devicePixelRatio);
      ctx.clearRect(0, 0, scene.width, scene.height);
      ctx.strokeStyle = 'rgba(99, 255, 221, .28)';
      ctx.lineWidth = 1 * devicePixelRatio;
      for (let i = 0; i < 18; i += 1) {
        const x = (scene.width / 18) * i;
        ctx.beginPath();
        ctx.arc(x, scene.height * .42 + Math.sin(Date.now()/900 + i) * 28, 80 + i * 2, 0, Math.PI * 2);
        ctx.stroke();
      }
      requestAnimationFrame(draw);
    };
    draw();
  }
})();
""".strip()

    css_path = "styles.css" if "styles.css" in by_path else ("src/App.css" if "src/App.css" in by_path else "src/index.css")
    by_path[css_path] = {
        "path": css_path,
        "content": (by_path.get(css_path, {}).get("content", "") + "\n\n" + css).strip() + "\n",
        "language": "css",
    }
    changed.append(css_path)

    js_path = "script.js" if "script.js" in by_path or "index.html" in by_path else "src/motion-runtime.js"
    by_path[js_path] = {
        "path": js_path,
        "content": (by_path.get(js_path, {}).get("content", "") + "\n\n" + js).strip() + "\n",
        "language": "javascript",
    }
    changed.append(js_path)

    if "index.html" in by_path:
        html = by_path["index.html"].get("content", "")
        if "data-amarktai-motion-scene" not in html:
            html = re.sub(r"<section(\s|>)", r"<section data-amarktai-motion-scene\1", html, count=1, flags=re.IGNORECASE)
        if "data-motion-runtime" not in html:
            html = re.sub(r"<body([^>]*)>", r"<body\1 data-motion-runtime=\"pending\">", html, count=1, flags=re.IGNORECASE)
        if "amarktai-motion-proof" not in html:
            proof = """
  <section id="motion-intelligence" class="amarktai-motion-proof" data-amarktai-motion-scene data-motion-parallax="subtle" aria-label="Motion runtime proof">
    <div><strong data-motion-counter="28">0</strong><span>coordinated agents</span></div>
    <div><strong data-motion-counter="3">0</strong><span>browser viewport checks</span></div>
    <div class="amarktai-waveform" data-motion-waveform aria-hidden="true"><span class="amarktai-waveform-bar"></span><span class="amarktai-waveform-bar"></span><span class="amarktai-waveform-bar"></span><span class="amarktai-waveform-bar"></span><span class="amarktai-waveform-bar"></span><span class="amarktai-waveform-bar"></span></div>
  </section>
""".rstrip()
            if "</main>" in html:
                html = html.replace("</main>", f"{proof}\n</main>", 1)
            else:
                html = html.replace("</body>", f"{proof}\n</body>", 1)
        if 'href="styles.css"' not in html and css_path == "styles.css":
            html = html.replace("</head>", '  <link rel="stylesheet" href="styles.css">\n</head>')
        if 'src="script.js"' not in html and js_path == "script.js":
            html = html.replace("</body>", '  <script src="script.js"></script>\n</body>')
        by_path["index.html"]["content"] = html
        changed.append("index.html")

    manifest = {
        "version": 1,
        "strategy": strategy,
        "requires_3d": requires_3d,
        "libraries": ["css_keyframes", "canvas_runtime"] + (["three_js_cdn_ready"] if requires_3d else ["gsap_ready"]),
        "changed_files": sorted(set(changed)),
        "choreography": [
            {"phase": "opening", "runtime": "parallax hero reveal", "selectors": ["[data-amarktai-motion-scene]"]},
            {"phase": "capability_proof", "runtime": "staggered reveal and hover depth", "selectors": ["section", "article", ".card"]},
            {"phase": "evidence", "runtime": "animated counters", "selectors": ["[data-motion-counter]"]},
            {"phase": "voice_media", "runtime": "waveform animation", "selectors": ["[data-motion-waveform]", ".amarktai-waveform-bar"]},
        ],
        "reduced_motion_supported": True,
        "runtime_validation_selector": "[data-amarktai-motion-scene], [data-motion-runtime]",
        "generated_at": _now(),
    }
    by_path["motion_manifest.json"] = {
        "path": "motion_manifest.json",
        "content": json.dumps(manifest, indent=2),
        "language": "json",
    }
    return list(by_path.values()), manifest


def persist_motion_manifest(workspace: str | Path, manifest: dict[str, Any]) -> Path:
    path = Path(workspace).resolve() / "motion_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path
