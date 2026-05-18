from pathlib import Path


def _write_page(ws: Path) -> None:
    (ws / "index.html").write_text(
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body><main>"
        "<section id='hero'><h1>Fixture Bakery</h1></section>"
        "<section id='menu'><h2>Menu</h2></section>"
        "<section id='story'><h2>Story</h2></section>"
        "<section id='gallery'><h2>Gallery</h2></section>"
        "<section id='contact'><h2>Contact</h2></section>"
        "</main></body></html>",
        encoding="utf-8",
    )
    (ws / "styles.css").write_text("", encoding="utf-8")
    (ws / "media").mkdir(exist_ok=True)
    for name in ("hero.mp4", "menu.jpg", "story.jpg", "gallery.jpg"):
        (ws / "media" / name).write_bytes(b"asset")


def test_prompt_sections_detect_gallery_story_menu():
    from app.services.media_runtime_service import expected_media_sections

    sections = expected_media_sections("cinematic bakery with menu, story, gallery, and contact visual CTA", ["hero"])

    assert {"hero", "menu", "story", "gallery", "contact"} <= set(sections)


def test_all_media_in_hero_fails_alignment_for_premium_gallery_prompt(tmp_path):
    from app.services.media_runtime_service import summarize_media_section_alignment

    _write_page(tmp_path)
    summary = summarize_media_section_alignment(
        tmp_path,
        [
            {"path": "media/hero.mp4", "media_type": "video", "section": "hero"},
            {"path": "media/menu.jpg", "media_type": "image", "section": "hero"},
            {"path": "media/story.jpg", "media_type": "image", "section": "hero"},
        ],
        sections=["hero", "menu", "story", "gallery"],
    )

    assert summary["hero_only"] is True
    assert {"menu", "story", "gallery"} <= set(summary["missing_sections"])


def test_gallery_story_menu_media_required_and_aligned(tmp_path):
    from app.services.media_runtime_service import summarize_media_section_alignment

    _write_page(tmp_path)
    summary = summarize_media_section_alignment(
        tmp_path,
        [
            {"path": "media/hero.mp4", "media_type": "video", "section": "hero"},
            {"path": "media/menu.jpg", "media_type": "image", "section": "menu"},
            {"path": "media/story.jpg", "media_type": "image", "section": "story"},
            {"path": "media/gallery.jpg", "media_type": "image", "section": "gallery"},
        ],
        sections=["hero", "menu", "story", "gallery"],
    )

    assert summary["missing_sections"] == []
    assert {"menu", "story", "gallery"} <= set(summary["aligned_sections"])


def test_video_is_used_as_hero_background_when_cinematic_video_exists(tmp_path):
    from app.services.media_runtime_service import inject_media_assets

    _write_page(tmp_path)
    changed = inject_media_assets(
        tmp_path,
        [
            {"path": "media/hero.mp4", "media_type": "video", "section": "hero"},
            {"path": "media/gallery.jpg", "media_type": "image", "section": "gallery"},
        ],
        sections=["hero", "gallery"],
    )
    html = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert "index.html" in changed
    assert "data-amarktai-hero-background" in html
    assert "<video" in html
    assert "media/gallery.jpg" in html
