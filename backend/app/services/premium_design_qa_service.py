"""Premium design QA and originality checks for generated workspaces.

This service is intentionally heuristic and local-only. It does not claim a
provider capability and it does not replace runtime QA. Its job is to catch the
class of output that is technically valid but visually generic, repetitive, or
too template-like for premium launch work.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", ".svelte-kit"}

_GENERIC_PHRASES = re.compile(
    r"\b("
    r"lorem ipsum|your product|feature one|feature two|feature three|"
    r"welcome to our website|we provide solutions|innovative solutions|"
    r"best in class|cutting edge technology|click here|learn more\s*</"
    r")\b",
    re.IGNORECASE,
)

_MOTION_PATTERNS = {
    "framer_motion": re.compile(r"framer-motion|motion\.", re.IGNORECASE),
    "gsap": re.compile(r"\bgsap\b|ScrollTrigger", re.IGNORECASE),
    "three": re.compile(r"three|@react-three/fiber|<Canvas\b", re.IGNORECASE),
    "canvas": re.compile(r"<canvas\b|getContext\(|requestAnimationFrame", re.IGNORECASE),
    "keyframes": re.compile(r"@keyframes|animation\s*:", re.IGNORECASE),
    "parallax": re.compile(r"parallax|translate3d|perspective|transform-style", re.IGNORECASE),
    "reduced_motion": re.compile(r"prefers-reduced-motion", re.IGNORECASE),
}

_LAYOUT_ARCHETYPES = {
    "split": re.compile(r"\b(split|two-column|grid-cols-2|lg:grid-cols|md:grid-cols-2)\b", re.IGNORECASE),
    "editorial": re.compile(r"\b(editorial|magazine|prose|eyebrow|kicker|lead)\b", re.IGNORECASE),
    "rail": re.compile(r"\b(rail|timeline|steps|workflow|marquee)\b", re.IGNORECASE),
    "media_scene": re.compile(r"\b(video|canvas|hero-media|media-layer|immersive|scene)\b", re.IGNORECASE),
    "metrics": re.compile(r"\b(metric|kpi|stat|score|proof|evidence)\b", re.IGNORECASE),
    "story": re.compile(r"\b(story|narrative|chapter|journey|transformation)\b", re.IGNORECASE),
    "cta": re.compile(r"\b(cta|request|start|book|launch|contact)\b", re.IGNORECASE),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_source_files(ws: Path) -> list[Path]:
    files: list[Path] = []
    for path in ws.rglob("*"):
        if not path.is_file():
            continue
        if set(path.relative_to(ws).parts) & _SKIP_DIRS:
            continue
        if path.suffix.lower() in {".html", ".css", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}:
            files.append(path)
    return files


def _source_text(ws: Path) -> str:
    chunks: list[str] = []
    for path in _iter_source_files(ws)[:80]:
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace")[:120_000])
        except Exception:
            continue
    return "\n".join(chunks)


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))


def _layout_fingerprint(source: str) -> dict[str, Any]:
    section_matches = re.findall(r"<section\b([^>]*)>", source, re.IGNORECASE)
    classes = re.findall(r'class(?:Name)?=["\']([^"\']+)["\']', source, re.IGNORECASE)
    archetypes = sorted(name for name, pattern in _LAYOUT_ARCHETYPES.items() if pattern.search(source))
    section_tokens: list[str] = []
    for attrs in section_matches:
        ident = re.search(r'\b(?:id|class)=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        section_tokens.append(ident.group(1)[:80] if ident else "section")
    raw = "|".join(section_tokens + archetypes + classes[:40])
    return {
        "hash": hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16],
        "section_count": len(section_matches),
        "section_tokens": section_tokens[:24],
        "archetypes": archetypes,
        "unique_class_ratio": round(len(set(classes)) / max(1, len(classes)), 2),
    }


def _score_originality(source: str, fingerprint: dict[str, Any]) -> tuple[int, list[str]]:
    issues: list[str] = []
    archetype_count = len(fingerprint["archetypes"])
    section_count = fingerprint["section_count"]
    card_count = len(re.findall(r"\b(card|feature-card|rounded-2xl|rounded-3xl)\b", source, re.IGNORECASE))
    centered_count = len(re.findall(r"text-center|mx-auto", source, re.IGNORECASE))
    repeated_grid_count = len(re.findall(r"grid-cols-3|repeat\(3|md:grid-cols-3|lg:grid-cols-3", source, re.IGNORECASE))

    score = 100
    if section_count < 5:
        score -= 22
        issues.append("Premium output needs at least five meaningful sections or scenes.")
    if archetype_count < 4:
        score -= 24
        issues.append("Layout uses too few distinct section archetypes.")
    if card_count >= 10 and archetype_count < 5:
        score -= 20
        issues.append("Card repetition dominates the composition.")
    if centered_count >= 8 and repeated_grid_count >= 2:
        score -= 18
        issues.append("Repeated centered sections and repeated grids create a template feel.")
    if _GENERIC_PHRASES.search(source):
        score -= 22
        issues.append("Generic placeholder or low-specificity marketing copy detected.")
    return _clamp(score), issues


def _score_motion(source: str) -> tuple[int, list[str], list[str]]:
    found = [name for name, pattern in _MOTION_PATTERNS.items() if pattern.search(source)]
    issues: list[str] = []
    score = 35 + min(55, len([x for x in found if x != "reduced_motion"]) * 14)
    if "reduced_motion" in found:
        score += 10
    else:
        issues.append("Motion system needs a prefers-reduced-motion fallback.")
    if not any(x in found for x in ("framer_motion", "gsap", "three", "canvas", "keyframes", "parallax")):
        issues.append("No meaningful motion, depth, or interaction system detected.")
    return _clamp(score), issues, found


def _score_typography(source: str) -> tuple[int, list[str]]:
    issues: list[str] = []
    has_font_import = bool(re.search(r"fonts\.(?:bunny|googleapis)|@font-face|font-family\s*:", source, re.IGNORECASE))
    has_fluid_type = bool(re.search(r"clamp\([^)]*(?:rem|vw|px)|text-5xl|text-6xl|text-7xl|font-display", source, re.IGNORECASE))
    has_hierarchy = len(re.findall(r"<h[1-3]\b|font-size|text-[3-9]xl", source, re.IGNORECASE)) >= 4
    score = 40
    if has_font_import:
        score += 20
    else:
        issues.append("No distinctive font system detected.")
    if has_fluid_type:
        score += 20
    else:
        issues.append("No premium-scale or fluid typography detected.")
    if has_hierarchy:
        score += 20
    else:
        issues.append("Typography hierarchy is too shallow.")
    return _clamp(score), issues


def _score_responsiveness(source: str) -> tuple[int, list[str]]:
    issues: list[str] = []
    has_viewport = "name='viewport'" in source or 'name="viewport"' in source
    has_breakpoints = bool(re.search(r"@media\s*\(|sm:|md:|lg:|xl:|max-width", source, re.IGNORECASE))
    has_fluid_layout = bool(re.search(r"clamp\(|minmax\(|grid-template|flex-wrap|auto-fit|auto-fill", source, re.IGNORECASE))
    score = (35 if has_viewport else 0) + (35 if has_breakpoints else 0) + (30 if has_fluid_layout else 0)
    if not has_viewport:
        issues.append("Viewport meta tag missing.")
    if not has_breakpoints:
        issues.append("No responsive breakpoints detected.")
    if not has_fluid_layout:
        issues.append("No fluid layout primitives detected.")
    return _clamp(score), issues


def _score_atmosphere(source: str) -> tuple[int, list[str]]:
    issues: list[str] = []
    signals = {
        "texture": re.search(r"noise|grain|texture|paper|tactile|mask-image|mix-blend", source, re.IGNORECASE),
        "depth": re.search(r"backdrop-filter|box-shadow|radial-gradient|conic-gradient|perspective|blur\(", source, re.IGNORECASE),
        "identity": re.search(r"--color-|:root|data-theme|brand|palette|accent", source, re.IGNORECASE),
        "media": re.search(r"<img\b|<video\b|canvas|svg|picture", source, re.IGNORECASE),
        "interaction": re.search(r":hover|onMouse|onPointer|cursor|transition|whileHover", source, re.IGNORECASE),
    }
    score = sum(20 for value in signals.values() if value)
    for key, value in signals.items():
        if not value:
            issues.append(f"Missing atmospheric signal: {key}.")
    return _clamp(score), issues


def run_premium_design_qa(
    workspace_path: str | Path,
    *,
    prompt: str = "",
    mode: str = "",
    minimum_score: int = 78,
) -> dict[str, Any]:
    """Score premium design quality and return blockers for generic output."""
    ws = Path(workspace_path).resolve()
    source = _source_text(ws)
    fingerprint = _layout_fingerprint(source)
    originality_score, originality_issues = _score_originality(source, fingerprint)
    motion_score, motion_issues, motion_systems = _score_motion(source)
    typography_score, typography_issues = _score_typography(source)
    responsive_score, responsive_issues = _score_responsiveness(source)
    atmosphere_score, atmosphere_issues = _score_atmosphere(source)

    sub_scores = {
        "originality": originality_score,
        "spacing_quality": 85 if re.search(r"gap-|padding|p-|margin|clamp\(", source, re.IGNORECASE) else 35,
        "cinematic_quality": _clamp((atmosphere_score + motion_score + originality_score) / 3),
        "motion_sophistication": motion_score,
        "visual_hierarchy": typography_score,
        "typography_quality": typography_score,
        "image_coherence": 80 if re.search(r"<img\b|<video\b|data-amarktai-media-asset|svg", source, re.IGNORECASE) else 45,
        "responsiveness": responsive_score,
        "immersion": atmosphere_score,
        "interaction_quality": _clamp(motion_score + 8 if re.search(r":hover|whileHover|onPointer|cursor", source, re.IGNORECASE) else motion_score - 10),
        "atmosphere": atmosphere_score,
        "emotional_quality": 85 if re.search(r"story|journey|feeling|tone|crafted|human|warm|cinematic|immersive", source, re.IGNORECASE) else 45,
        "premium_feel": _clamp((originality_score + typography_score + atmosphere_score) / 3),
        "storytelling_quality": 85 if re.search(r"chapter|story|journey|proof|transformation|outcome|finale|launch", source, re.IGNORECASE) else 45,
        "composition_balance": _clamp((originality_score + responsive_score + atmosphere_score) / 3),
    }
    overall = int(sum(sub_scores.values()) / len(sub_scores))
    issues = originality_issues + motion_issues + typography_issues + responsive_issues + atmosphere_issues
    blockers: list[str] = []
    if overall < minimum_score:
        blockers.append(f"premium_design_score {overall} is below threshold {minimum_score}.")
    critical_floor = {
        "originality": 65,
        "motion_sophistication": 55,
        "typography_quality": 65,
        "responsiveness": 70,
        "atmosphere": 60,
        "premium_feel": 65,
    }
    for key, floor in critical_floor.items():
        if sub_scores[key] < floor:
            blockers.append(f"{key} score {sub_scores[key]} is below premium floor {floor}.")
    if _GENERIC_PHRASES.search(source):
        blockers.append("Generic/template copy detected.")

    report = {
        "ok": not blockers,
        "score": overall,
        "sub_scores": sub_scores,
        "blockers": blockers,
        "issues": issues[:24],
        "layout_fingerprint": fingerprint,
        "motion_systems": motion_systems,
        "prompt": prompt,
        "mode": mode,
        "checked_at": _now(),
    }
    try:
        (ws / "premium-design-qa-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        pass
    return report
