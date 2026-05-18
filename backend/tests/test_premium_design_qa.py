from pathlib import Path


def _write_workspace(ws: Path, *, generic: bool = False) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    if generic:
        (ws / "index.html").write_text(
            "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
            "<body><section class='hero text-center'><h1>Your Product</h1><p>Innovative solutions for everyone.</p></section>"
            "<section class='features grid grid-cols-3 text-center'><div class='card'>Feature One</div><div class='card'>Feature Two</div><div class='card'>Feature Three</div></section>"
            "<section class='features grid grid-cols-3 text-center'><div class='card'>Feature One</div><div class='card'>Feature Two</div><div class='card'>Feature Three</div></section>"
            "</body></html>",
            encoding="utf-8",
        )
        (ws / "styles.css").write_text("body{font-family:Arial} .card{padding:1rem}", encoding="utf-8")
        return

    (ws / "index.html").write_text(
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<link rel='stylesheet' href='https://fonts.bunny.net/css?family=space-grotesk:700|dm-sans:400'></head>"
        "<body>"
        "<section id='hero' class='cinematic scene split media_scene'><canvas></canvas><p class='eyebrow'>Launch chapter</p><h1>Immersive Product Launch</h1><p>A tactile, cinematic product story for an expert audience.</p></section>"
        "<section id='story' class='story editorial chapter'><h2>The transformation journey</h2><p>Human warmth, product proof, and emotional pacing.</p></section>"
        "<section id='proof' class='metrics proof rail'><h2>Runtime evidence</h2><p>Playwright, Lighthouse, media manifests, and final gates.</p></section>"
        "<section id='media' class='immersive media_scene'><video src='media/loop.mp4'></video><h2>Motion-led media</h2></section>"
        "<section id='workflow' class='timeline rail'><h2>Agent workflow</h2><p>Plan, design, build, test, repair, and launch.</p></section>"
        "<section id='contact' class='cta finale'><h2>Start the launch</h2><a href='#hero'>Request access</a></section>"
        "</body></html>",
        encoding="utf-8",
    )
    (ws / "styles.css").write_text(
        ":root{--color-bg:#030712;--color-accent:#22d3ee;--font-heading:'Space Grotesk';--font-body:'DM Sans'}"
        "body{font-family:var(--font-body);background:radial-gradient(circle,#164e63,transparent),#030712;color:white}"
        "h1,h2{font-family:var(--font-heading);font-size:clamp(2.5rem,7vw,7rem)}"
        "section{padding:clamp(3rem,8vw,9rem);display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:clamp(1.5rem,4vw,5rem);backdrop-filter:blur(20px);box-shadow:0 30px 100px rgba(0,0,0,.4)}"
        ".rail{display:flex;flex-wrap:wrap}.media_scene{perspective:1000px}.cta{text-align:center}"
        "@keyframes drift{to{transform:translate3d(0,-14px,0)}}.scene{animation:drift 8s ease-in-out infinite alternate}"
        "@media(max-width:720px){section{display:block}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}",
        encoding="utf-8",
    )
    (ws / "media").mkdir(exist_ok=True)
    (ws / "media" / "loop.mp4").write_bytes(b"mp4")


def test_premium_design_qa_fails_generic_repetitive_layout(tmp_path):
    from app.services.premium_design_qa_service import run_premium_design_qa

    _write_workspace(tmp_path, generic=True)
    report = run_premium_design_qa(tmp_path, prompt="premium cinematic product launch")

    assert report["ok"] is False
    assert report["score"] < 78
    assert any("Generic" in blocker or "originality" in blocker for blocker in report["blockers"])


def test_premium_design_qa_passes_cinematic_diverse_layout(tmp_path):
    from app.services.premium_design_qa_service import run_premium_design_qa

    _write_workspace(tmp_path)
    report = run_premium_design_qa(tmp_path, prompt="premium cinematic product launch")

    assert report["ok"] is True
    assert report["sub_scores"]["originality"] >= 65
    assert report["layout_fingerprint"]["hash"]
    assert "reduced_motion" in report["motion_systems"]


def test_quality_gate_includes_premium_design_qa(tmp_path):
    from app.services.quality_gate_service import run_quality_gate

    _write_workspace(tmp_path, generic=True)
    (tmp_path / "README.md").write_text("# Generic\n", encoding="utf-8")
    (tmp_path / "preview-manifest.json").write_text('{"entry":"index.html"}', encoding="utf-8")
    report = run_quality_gate(tmp_path, prompt="premium cinematic product launch")

    assert report["pass"] is False
    assert report["premium_quality_report"]["premium_design_qa"]["ok"] is False
