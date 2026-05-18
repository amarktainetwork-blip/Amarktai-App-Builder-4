import json
from pathlib import Path


def _premium_workspace(ws: Path, *, fallback: bool = False, broken_media: bool = False) -> Path:
    (ws / "media").mkdir(exist_ok=True)
    for name in ("hero.mp4", "menu.jpg", "story.jpg", "gallery.jpg", "contact.jpg"):
        (ws / "media" / name).write_bytes(b"asset")
    missing_src = "media/missing.jpg" if broken_media else "media/gallery.jpg"
    (ws / "index.html").write_text(
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><link rel='stylesheet' href='https://fonts.bunny.net/css?family=playfair-display:700|inter:400,600'></head>"
        "<body><main>"
        "<section id='hero' class='cinematic scene media_scene split'><div class='amarktai-hero-media-layer'><video data-amarktai-media-asset data-amarktai-hero-background src='media/hero.mp4'></video></div><p class='eyebrow'>Warm craft chapter</p><h1>Fixture Bakery</h1><p>A cinematic story of fire, grain, and morning ritual.</p></section>"
        "<section id='menu' class='editorial split product-rail'><h2>Wood-fired pastries and sourdough menu</h2><p>Seasonal loaves, laminated pastries, espresso, and tasting boxes.</p><img data-amarktai-media-asset src='media/menu.jpg' alt='Menu'></section>"
        "<section id='story' class='story chapter editorial'><h2>Our bakery story</h2><p>Small-batch doughs, cultured butter, and neighborhood hospitality shape every morning.</p><img data-amarktai-media-asset src='media/story.jpg' alt='Story'></section>"
        f"<section id='gallery' class='gallery immersive media_scene'><h2>Gallery</h2><p>See the crust, pastry layers, and warm counter moments.</p><img data-amarktai-media-asset src='{missing_src}' alt='Gallery'></section>"
        "<section id='proof' class='metrics proof'><h2>Daily proof</h2><p>48-hour ferments, 6am bake cycles, and neighborhood pickup rituals.</p></section>"
        "<section id='contact' class='cta conversion finale'><h2>Visit Fixture Bakery</h2><p>Reserve a tasting, plan a catering box, or ask about weekly specials.</p><img data-amarktai-media-asset src='media/contact.jpg' alt='Contact'><a href='#hero'>Book a tasting</a></section>"
        "</main></body></html>",
        encoding="utf-8",
    )
    (ws / "styles.css").write_text(
        ":root{--color-bg:#170f0a;--color-accent:#d6a15f;--font-heading:'Playfair Display';--font-body:'Inter'}"
        "body{font-family:var(--font-body);background:radial-gradient(circle,#5b341a,transparent),#170f0a;color:#fff}"
        "h1,h2{font-family:var(--font-heading);font-size:clamp(2.5rem,7vw,7rem)}"
        "section{padding:clamp(3rem,7vw,8rem);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:clamp(1.5rem,4vw,4rem);box-shadow:0 30px 90px rgba(0,0,0,.35)}"
        ".gallery{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}.proof{display:flex}.cta{text-align:center}"
        "@keyframes emberDrift{to{transform:translate3d(0,-12px,0)}}.scene{animation:emberDrift 6s ease-in-out infinite alternate}"
        "@media (max-width:700px){section{display:block}}@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}",
        encoding="utf-8",
    )
    (ws / "README.md").write_text("# Fixture Bakery\n", encoding="utf-8")
    (ws / "preview-manifest.json").write_text('{"entry":"index.html"}', encoding="utf-8")
    assets = [
        {"path": "media/hero.mp4", "media_type": "video", "section": "hero", "source": "pixabay" if fallback else "genx"},
        {"path": "media/menu.jpg", "media_type": "image", "section": "menu", "source": "local_runtime_fallback" if fallback else "genx"},
        {"path": "media/story.jpg", "media_type": "image", "section": "story", "source": "local_runtime_fallback" if fallback else "genx"},
        {"path": "media/gallery.jpg", "media_type": "image", "section": "gallery", "source": "local_runtime_fallback" if fallback else "genx"},
        {"path": "media/contact.jpg", "media_type": "image", "section": "contact", "source": "local_runtime_fallback" if fallback else "genx"},
    ]
    (ws / "media_manifest.json").write_text(json.dumps({
        "status": "fallback" if fallback else "ai_generated",
        "assets": assets,
        "attempts": [{"provider": "genx", "ok": not fallback, "error": "params is required"}] if fallback else [{"provider": "genx", "ok": True}],
        "asset_count": 4,
        "runtime_call_failed": fallback,
        "fallback_used": fallback,
        "injected": True,
        "premium_media_complete": not fallback,
        "section_alignment": {
            "expected_sections": ["hero", "menu", "story", "gallery", "contact"],
            "aligned_sections": ["hero", "menu", "story", "gallery", "contact"],
            "missing_sections": [],
            "hero_only": False,
        },
    }), encoding="utf-8")
    (ws / "runtime-qa").mkdir(exist_ok=True)
    (ws / "runtime-qa" / "runtime-qa-report.json").write_text(json.dumps({
        "pass": not broken_media,
        "blockers": ["Broken runtime media assets detected: 1."] if broken_media else [],
        "warnings": [],
        "media_assets": {"broken": [{"src": "media/missing.jpg"}] if broken_media else []},
        "accessibility": {"available": True, "score": 100},
        "performance": {"available": True, "score": 95},
    }), encoding="utf-8")
    return ws


def test_generic_fallback_premium_page_fails(tmp_path):
    from app.services.quality_gate_service import run_quality_gate

    ws = _premium_workspace(tmp_path, fallback=True)
    html = (ws / "index.html").read_text(encoding="utf-8").replace("Fixture Bakery", "Amarktai Builder runtime media")
    (ws / "index.html").write_text(html, encoding="utf-8")
    report = run_quality_gate(ws, require_media=True, prompt="premium cinematic bakery gallery menu story")

    assert report["pass"] is False
    assert report["premium_quality_score"] < 100
    assert any(item["check"] == "premium_quality" for item in report["blockers"])


def test_runtime_broken_media_blocks_premium_finalization(tmp_path, monkeypatch):
    from app.services.quality_gate_service import run_quality_gate

    ws = _premium_workspace(tmp_path, broken_media=True)
    monkeypatch.setattr("app.services.quality_gate_service.run_runtime_qa", lambda _ws: {
        "pass": False,
        "blockers": ["Broken runtime media assets detected: 1."],
        "warnings": [],
        "media_assets": {"broken": [{"src": "media/missing.jpg"}]},
        "accessibility": {"available": True, "score": 100},
        "performance": {"available": True, "score": 95},
        "report_path": str(ws / "runtime-qa" / "runtime-qa-report.json"),
    })
    report = run_quality_gate(ws, require_media=True, require_runtime=True, prompt="premium cinematic bakery gallery menu story")

    assert report["pass"] is False
    assert any("Broken runtime media" in msg for msg in report["checks"]["premium_quality"]["report"]["blockers"])


def test_quality_score_cannot_be_100_with_provider_failures(tmp_path):
    from app.services.quality_gate_service import run_quality_gate

    ws = _premium_workspace(tmp_path, fallback=True)
    report = run_quality_gate(ws, require_media=True, prompt="premium cinematic bakery gallery menu story")

    assert report["score"] < 100
    assert report["premium_quality_report"]["provider_failures"]


def test_valid_premium_page_with_media_and_responsive_css_passes(tmp_path):
    from app.services.quality_gate_service import run_quality_gate

    ws = _premium_workspace(tmp_path)
    report = run_quality_gate(ws, require_media=True, prompt="premium cinematic bakery gallery menu story")

    assert report["pass"] is True
    assert report["premium_quality_score"] >= 75
