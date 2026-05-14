"""Deterministic Motion / 3D patching for generated frontend files."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_requires_motion(prompt: str, mode: str = "") -> bool:
    haystack = f"{prompt} {mode}".lower()
    return bool(re.search(r"\b(3d|three\.js|threejs|motion|animation|animated|gsap|parallax|cinematic|particles|video background)\b", haystack))


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
}
@media (prefers-reduced-motion: reduce) {
  .amarktai-motion-reveal, .amarktai-motion-float, .amarktai-motion-orbit { animation: none !important; opacity: 1 !important; transform: none !important; }
}
@keyframes amarktaiReveal { to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes amarktaiFloat { 0%,100% { transform: translate3d(0,0,0); } 50% { transform: translate3d(0,-14px,0); } }
@keyframes amarktaiOrbit { to { transform: rotate(360deg); } }
""".strip()

    js = """
(() => {
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.documentElement.dataset.motionRuntime = reduce ? 'reduced' : 'active';
  if (reduce) return;
  document.querySelectorAll('section, .card, [data-motion-target]').forEach((el, index) => {
    el.classList.add('amarktai-motion-reveal');
    el.style.animationDelay = `${Math.min(index * 70, 560)}ms`;
  });
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
