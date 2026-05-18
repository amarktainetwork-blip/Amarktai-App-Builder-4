"""Generate the Amarktai Builder cinematic showcase website.

The showcase is a static proof site scaffold that can be generated from a
CapabilityTruthService payload. It only marks systems as live when the supplied
truth data says they are end-to-end available or available. Setup-needed systems
are displayed honestly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SHOWCASE_FEATURES = [
    ("website_generation", "Website generation"),
    ("app_generation", "App generation"),
    ("dashboard_generation", "Dashboard generation"),
    ("pwa_generation", "PWA generation"),
    ("repo_analysis", "Repo analysis"),
    ("github_integration", "Repo repair and PR workflow"),
    ("runtime_qa", "Runtime QA"),
    ("playwright", "Playwright"),
    ("lighthouse", "Lighthouse"),
    ("image_generation", "Image generation"),
    ("video_generation", "Video generation"),
    ("avatar_generation", "Avatar systems"),
    ("voice_generation", "Voice systems"),
    ("deployment_finalize", "Deployment final gate"),
    ("capability_truth", "Capability truth"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capability_state(capabilities: dict[str, Any], key: str) -> dict[str, Any]:
    item = capabilities.get(key) or {}
    if not isinstance(item, dict):
        return {"status": "setup_needed", "label": "Setup needed", "available": False}
    status = item.get("capability_status") or item.get("status") or item.get("live_status") or "setup_needed"
    available = bool(item.get("end_to_end_available") or item.get("available"))
    label = item.get("dashboard_label") or (
        "End-to-end available" if available else str(status).replace("_", " ").title()
    )
    return {
        "status": "end_to_end_available" if available else status,
        "label": label,
        "available": available,
        "reason": item.get("reason") or item.get("message") or "",
    }


def build_showcase_files(capability_truth: dict[str, Any] | None = None) -> dict[str, str]:
    truth = capability_truth or {}
    capabilities = truth.get("capabilities") or truth.get("summary") or {}
    feature_cards = []
    live_count = 0
    for key, title in SHOWCASE_FEATURES:
        state = _capability_state(capabilities, key)
        if state["available"]:
            live_count += 1
        feature_cards.append(
            f"<article class='proof-card {state['status']}'><span>{state['label']}</span>"
            f"<h3>{title}</h3><p>{state['reason'] or 'Evidence is read from capability truth at generation time.'}</p></article>"
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Amarktai Builder Showcase</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main>
    <section id="hero" class="scene hero">
      <div class="orb"></div>
      <p class="eyebrow">Cinematic software factory proof</p>
      <h1>Amarktai Builder turns prompts into launch-ready digital experiences.</h1>
      <p class="lede">This showcase is generated from capability truth: live systems are marked live, setup-needed systems stay honest, and final gates remain evidence based.</p>
      <a href="#proof" class="button">See live proof</a>
    </section>
    <section id="story" class="chapter split editorial">
      <p class="eyebrow">From prompt to product</p>
      <h2>Plan, design, build, test, repair, verify, and prepare for launch.</h2>
      <p>The experience demonstrates websites, apps, dashboards, PWAs, repo workflows, media, runtime QA, and final gate verification without fake capability claims.</p>
    </section>
    <section id="motion" class="scene media_scene">
      <div class="kinetic-grid" aria-hidden="true"></div>
      <h2>Motion supports the story. It does not decorate randomly.</h2>
      <p>Layered depth, responsive pacing, reduced-motion support, and cinematic reveal systems are part of the build standard.</p>
    </section>
    <section id="proof" class="proof metrics">
      <p class="eyebrow">{live_count} systems currently marked live by truth data</p>
      <h2>Every capability is truth-gated.</h2>
      <div class="proof-grid">{''.join(feature_cards)}</div>
    </section>
    <section id="finale" class="cta finale">
      <h2>Runtime-valid is not enough. The final gate demands evidence and design quality.</h2>
      <p>Generic output, broken media, weak motion, missing provider proof, or setup-needed blockers cannot masquerade as launch-ready.</p>
    </section>
  </main>
  <script src="showcase.js"></script>
</body>
</html>"""

    css = """@import url('https://fonts.bunny.net/css?family=space-grotesk:700,800|dm-sans:400,500,700');
:root{--bg:#030712;--panel:rgba(15,23,42,.72);--line:rgba(148,163,184,.18);--text:#f8fafc;--muted:#94a3b8;--cyan:#22d3ee;--violet:#8b5cf6;--magenta:#d946ef;--green:#10b981;--amber:#f59e0b;--red:#ef4444;--font-heading:'Space Grotesk',system-ui;--font-body:'DM Sans',system-ui}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 20% 10%,rgba(34,211,238,.22),transparent 30%),radial-gradient(circle at 90% 20%,rgba(139,92,246,.22),transparent 34%),var(--bg);color:var(--text);font-family:var(--font-body);overflow-x:hidden}
section{position:relative;min-height:70vh;padding:clamp(4rem,8vw,9rem) clamp(1.25rem,6vw,6rem);border-bottom:1px solid var(--line)}
.hero{display:grid;align-content:center;overflow:hidden}.orb{position:absolute;inset:auto -12rem 8rem auto;width:34rem;aspect-ratio:1;border-radius:999px;background:conic-gradient(from 90deg,var(--cyan),var(--violet),var(--magenta),var(--cyan));filter:blur(70px);opacity:.35;animation:orbit 18s linear infinite}
.eyebrow{font-size:.72rem;letter-spacing:.28em;text-transform:uppercase;color:var(--cyan);font-weight:800}h1,h2{font-family:var(--font-heading);max-width:1100px;margin:.3em 0;font-size:clamp(3rem,8vw,8.5rem);line-height:.9;letter-spacing:0}h2{font-size:clamp(2.25rem,5.5vw,6rem)}.lede,p{max-width:760px;color:var(--muted);font-size:clamp(1rem,1.6vw,1.25rem);line-height:1.65}.button{display:inline-flex;width:max-content;margin-top:2rem;border:1px solid rgba(34,211,238,.5);border-radius:999px;background:linear-gradient(90deg,var(--cyan),#3b82f6,var(--violet));color:#020617;padding:1rem 1.25rem;font-weight:900;text-decoration:none}.split{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:clamp(2rem,5vw,6rem);align-items:center}.media_scene{overflow:hidden}.kinetic-grid{min-height:24rem;border:1px solid var(--line);border-radius:2rem;background:linear-gradient(90deg,rgba(255,255,255,.08) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.08) 1px,transparent 1px),radial-gradient(circle at 50% 50%,rgba(34,211,238,.22),transparent 45%);background-size:46px 46px,46px 46px,100% 100%;box-shadow:0 40px 120px rgba(0,0,0,.45);animation:drift 10s ease-in-out infinite alternate}.proof-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;margin-top:2rem}.proof-card{min-height:190px;border:1px solid var(--line);border-radius:1.4rem;background:var(--panel);padding:1.1rem;backdrop-filter:blur(18px);transition:transform .35s ease,border-color .35s ease}.proof-card:hover{transform:translateY(-6px);border-color:rgba(34,211,238,.55)}.proof-card span{font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;color:var(--amber)}.proof-card.end_to_end_available span,.proof-card.live_ok span{color:var(--green)}.proof-card.runtime_failed span{color:var(--red)}.proof-card h3{font-family:var(--font-heading);font-size:1.3rem}.cta{text-align:center;display:grid;place-items:center} .cta p{margin-inline:auto}@keyframes orbit{to{transform:rotate(360deg)}}@keyframes drift{to{transform:translate3d(0,-18px,0) scale(1.02)}}@media(max-width:760px){.split{grid-template-columns:1fr}section{min-height:auto}.proof-grid{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}"""

    js = """const reduceMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;if(!reduceMotion){const cards=[...document.querySelectorAll('.proof-card')];window.addEventListener('pointermove',(event)=>{const x=event.clientX/window.innerWidth-.5;const y=event.clientY/window.innerHeight-.5;cards.forEach((card,index)=>{const depth=(index%5+1)*2;card.style.transform=`translate3d(${x*depth}px,${y*depth}px,0)`;});},{passive:true});}"""
    manifest = json.dumps({
        "generated_at": _now(),
        "source": "CapabilityTruthService payload",
        "live_feature_count": live_count,
        "feature_count": len(SHOWCASE_FEATURES),
        "truthful_capability_labels": True,
        "fake_provider_claims": False,
    }, indent=2)
    return {
        "index.html": html,
        "styles.css": css,
        "showcase.js": js,
        "showcase-manifest.json": manifest,
    }


def write_showcase_workspace(workspace_path: str | Path, capability_truth: dict[str, Any] | None = None) -> dict[str, Any]:
    ws = Path(workspace_path)
    ws.mkdir(parents=True, exist_ok=True)
    files = build_showcase_files(capability_truth)
    for rel, content in files.items():
        (ws / rel).write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "workspace_path": str(ws),
        "files": sorted(files.keys()),
        "manifest": json.loads(files["showcase-manifest.json"]),
    }
