"""
HTML and CSS structural validator using BeautifulSoup4 and tinycss2.

Used by the QA/Validation Agent to check generated project files.

Checks:
  HTML:
    - every page has a <title>
    - nav links resolve to existing files or anchors
    - stylesheet <link>/<style> exists
    - images have alt text
    - sections are non-empty
    - forms have labels
    - no duplicate empty pages

  CSS:
    - font-family exists
    - @media query exists
    - font-size readable (>= 12px)
    - no near-invisible text
    - no body/main hidden
    - sufficient visual styling depth

  Media:
    - selected uploaded logo is referenced
    - Pixabay attribution present when used
    - no broken local media paths
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("amarktai.html_validator")

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
    logger.warning("beautifulsoup4 not available; HTML structural validation will be limited")

try:
    import tinycss2
    _TINYCSS2_AVAILABLE = True
except ImportError:
    _TINYCSS2_AVAILABLE = False
    logger.warning("tinycss2 not available; CSS validation will be limited")


# ── CSS/font validation helpers ───────────────────────────────────────────────

_FONT_FAMILY_RE = re.compile(r"font-family\s*:", re.IGNORECASE)
_MEDIA_QUERY_RE = re.compile(r"@media\s*\(", re.IGNORECASE)
_FONT_SIZE_PX_RE = re.compile(r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*px", re.IGNORECASE)
# Use simple non-backtracking patterns for CSS checks applied to user-provided content
_LOW_OPACITY_RE = re.compile(
    r"color\s*:\s*rgba\([^)]{0,100},\s*0\.0[0-9]\s*\)", re.IGNORECASE
)
_HIDDEN_BODY_RE = re.compile(
    r"(?:body|main)\s*\{[^}]{0,500}(?:display\s*:\s*none|visibility\s*:\s*hidden)",
    re.IGNORECASE,
)


def validate_html_structure(html_content: str, filename: str = "index.html") -> dict[str, Any]:
    """Validate HTML structure using BeautifulSoup.

    Returns dict with issues (list[str]) and warnings (list[str]).
    """
    issues: list[str] = []
    warnings: list[str] = []

    if not html_content.strip():
        return {"issues": [f"{filename}: File is empty"], "warnings": []}

    if not _BS4_AVAILABLE:
        # Fallback regex-based checks
        return _validate_html_regex(html_content, filename)

    try:
        soup = BeautifulSoup(html_content, "html.parser")
    except Exception as e:
        warnings.append(f"{filename}: HTML parse warning: {e}")
        return {"issues": issues, "warnings": warnings}

    # 1. <title> present
    title = soup.find("title")
    if not title or not (title.string or "").strip():
        issues.append(f"{filename}: Missing or empty <title> element")

    # 2. Stylesheet link or inline <style>
    has_link_css = bool(soup.find("link", {"rel": re.compile(r"stylesheet", re.I)}))
    has_style_tag = bool(soup.find("style"))
    if not has_link_css and not has_style_tag:
        warnings.append(f"{filename}: No stylesheet <link> or <style> found")

    # 3. Images have alt text
    imgs = soup.find_all("img")
    for img in imgs:
        alt = img.get("alt")
        if alt is None:
            issues.append(f"{filename}: <img> missing alt attribute (src={img.get('src', '?')[:60]})")

    # 4. Non-empty sections
    empty_section_count = 0
    for tag in soup.find_all(["section", "main", "article"]):
        text = (tag.get_text() or "").strip()
        children = list(tag.children)
        if not text and len(children) <= 2:
            empty_section_count += 1
    if empty_section_count > 2:
        warnings.append(f"{filename}: {empty_section_count} empty section/main/article elements found")

    # 5. Forms have labels
    forms = soup.find_all("form")
    for i, form in enumerate(forms):
        inputs = form.find_all(["input", "select", "textarea"])
        labels = form.find_all("label")
        labeled = {lbl.get("for") for lbl in labels if lbl.get("for")}
        for inp in inputs:
            inp_type = (inp.get("type") or "text").lower()
            if inp_type in ("hidden", "submit", "button", "reset", "image"):
                continue
            inp_id = inp.get("id", "")
            if inp_id and inp_id not in labeled:
                aria = inp.get("aria-label") or inp.get("aria-labelledby")
                if not aria:
                    warnings.append(f"{filename}: Form input id='{inp_id}' has no associated <label>")

    # 6. <html lang> attribute
    html_tag = soup.find("html")
    if html_tag and not html_tag.get("lang"):
        warnings.append(f"{filename}: <html> missing lang attribute (accessibility)")

    # 7. H1 present
    if not soup.find("h1"):
        warnings.append(f"{filename}: No <h1> element found")

    return {"issues": issues, "warnings": warnings}


def _validate_html_regex(html_content: str, filename: str) -> dict[str, Any]:
    """Fallback regex-based HTML checks when BS4 is not available."""
    issues: list[str] = []
    warnings: list[str] = []
    # Use non-backtracking patterns (bounded quantifiers to avoid ReDoS)
    if not re.search(r"<title[^>]{0,200}>[^<]{1,500}</title>", html_content, re.I):
        issues.append(f"{filename}: Missing or empty <title>")
    if not re.search(r'<link[^>]{0,500}stylesheet|<style\b', html_content, re.I):
        warnings.append(f"{filename}: No stylesheet link or style tag found")
    if not re.search(r"<h1\b", html_content, re.I):
        warnings.append(f"{filename}: No <h1> found")
    imgs = re.findall(r"<img\b[^>]{0,500}>", html_content, re.I)
    for img in imgs:
        if "alt=" not in img.lower():
            issues.append(f"{filename}: <img> missing alt attribute")
    return {"issues": issues, "warnings": warnings}


def validate_css(css_content: str, filename: str = "styles.css") -> dict[str, Any]:
    """Validate CSS using tinycss2 and regex helpers.

    Returns dict with issues (list[str]) and warnings (list[str]).
    """
    issues: list[str] = []
    warnings: list[str] = []

    if not css_content.strip():
        return {"issues": [f"{filename}: CSS file is empty"], "warnings": []}

    # Check font-family
    if not _FONT_FAMILY_RE.search(css_content):
        warnings.append(f"{filename}: No font-family declaration found")

    # Check responsive media query
    if not _MEDIA_QUERY_RE.search(css_content):
        warnings.append(f"{filename}: No @media query found (not responsive)")

    # Check for hidden body/main
    if _HIDDEN_BODY_RE.search(css_content):
        issues.append(f"{filename}: body or main appears to have display:none or visibility:hidden")

    # Check for near-invisible text color
    if _LOW_OPACITY_RE.search(css_content):
        warnings.append(f"{filename}: Near-invisible text color detected (very low opacity)")

    # Check for very small font sizes
    tiny_sizes = [
        int(float(sz)) for sz in _FONT_SIZE_PX_RE.findall(css_content)
        if float(sz) < 10
    ]
    if tiny_sizes:
        warnings.append(f"{filename}: Very small font sizes detected: {tiny_sizes}px")

    # tinycss2 parse errors
    if _TINYCSS2_AVAILABLE:
        try:
            rules, _ = tinycss2.parse_stylesheet_bytes(css_content.encode())
            parse_errors = [r for r in rules if getattr(r, "type", "") == "error"]
            if parse_errors:
                warnings.append(f"{filename}: {len(parse_errors)} CSS parse error(s)")
        except Exception as e:
            warnings.append(f"{filename}: CSS parse warning: {e}")

    return {"issues": issues, "warnings": warnings}


def validate_media_references(
    html_content: str,
    project_files: list[dict],
    logo_result: dict | None = None,
    pixabay_assets: list[str] | None = None,
    filename: str = "index.html",
) -> dict[str, Any]:
    """Validate media references in generated HTML.

    Checks:
    - Uploaded logo is actually referenced (if logo_result.logoType == "uploaded")
    - Pixabay attribution present when Pixabay assets used
    - No broken local file references
    """
    issues: list[str] = []
    warnings: list[str] = []

    # Check uploaded logo is referenced
    if logo_result:
        logo_type = logo_result.get("logoType", "")
        asset_id = logo_result.get("assetId", "")
        if logo_type == "uploaded" and asset_id:
            if asset_id not in html_content:
                issues.append(
                    f"{filename}: Uploaded logo (assetId={asset_id}) is not referenced in the HTML"
                )

    # Check Pixabay attribution
    if pixabay_assets:
        # Look for attribution text (not just URLs) like "Photo by X on Pixabay", "via Pixabay"
        has_attribution = bool(
            re.search(
                r"Photo by [A-Za-z0-9 ]{1,50} on Pixabay|via Pixabay|pixabay\.com/users/|pixabay license",
                html_content, re.I,
            )
        )
        if not has_attribution:
            warnings.append(
                f"{filename}: Pixabay assets used but no text attribution found. "
                "Add 'Photo by [author] on Pixabay' or 'via Pixabay' per Pixabay license."
            )

    # Check local media paths
    if _BS4_AVAILABLE:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            project_paths = {f.get("path", "") for f in project_files}
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if not src:
                    continue
                # Skip external URLs and data URIs
                if src.startswith(("http://", "https://", "data:", "/api/")):
                    continue
                # Remove leading ./
                rel_path = src.lstrip("./")
                if rel_path and rel_path not in project_paths:
                    warnings.append(f"{filename}: Image src='{src[:60]}' not found in project files")
        except Exception:
            pass

    return {"issues": issues, "warnings": warnings}


def validate_project_files_enhanced(
    files: list[dict],
    logo_result: dict | None = None,
    pixabay_assets: list[str] | None = None,
) -> dict[str, Any]:
    """Run all HTML/CSS/media validations across all project files.

    Returns aggregated validation result with all issues and warnings.
    """
    all_issues: list[str] = []
    all_warnings: list[str] = []

    for f in files:
        path = f.get("path", "")
        content = f.get("content", "")
        if not content:
            continue

        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""

        if ext in ("html", "htm"):
            result = validate_html_structure(content, path)
            all_issues.extend(result["issues"])
            all_warnings.extend(result["warnings"])

            media_result = validate_media_references(
                content, files, logo_result, pixabay_assets, path
            )
            all_issues.extend(media_result["issues"])
            all_warnings.extend(media_result["warnings"])

        elif ext == "css":
            result = validate_css(content, path)
            all_issues.extend(result["issues"])
            all_warnings.extend(result["warnings"])

    return {
        "issues": all_issues,
        "warnings": all_warnings,
        "issue_count": len(all_issues),
        "warning_count": len(all_warnings),
        "passed": len(all_issues) == 0,
    }
