"""Render a project's files into a self-contained HTML doc for the live preview iframe."""
from __future__ import annotations

import html as _html
import re


def render_preview(files: list[dict]) -> str:
    """Inline the project's CSS/JS into its index.html so it works in an iframe via srcdoc."""
    by_path = {f["path"]: f for f in files}
    index = by_path.get("index.html")
    if not index:
        return _empty_state("No index.html found yet. Agents are still writing your app...")

    src = index["content"]

    # Inline <link rel="stylesheet" href="X.css"> tags whose target is a project file.
    def inline_css(match: re.Match) -> str:
        href = match.group("href")
        f = by_path.get(href)
        if not f:
            return match.group(0)
        return f"<style data-amarktai-inline=\"{_html.escape(href)}\">\n{f['content']}\n</style>"

    src = re.sub(
        r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*/?>',
        inline_css,
        src,
        flags=re.IGNORECASE,
    )

    # Inline <script src="X.js"></script> tags whose target is a project file.
    def inline_js(match: re.Match) -> str:
        s = match.group("src")
        f = by_path.get(s)
        if not f:
            return match.group(0)
        type_attr = match.group("typeattr") or ""
        return (
            f'<script data-amarktai-inline="{_html.escape(s)}"{type_attr}>\n'
            f'{f["content"]}\n</script>'
        )

    src = re.sub(
        r'<script(?P<typeattr>\s+type=["\'][^"\']+["\'])?\s+src=["\'](?P<src>[^"\']+)["\'][^>]*>\s*</script>',
        inline_js,
        src,
        flags=re.IGNORECASE,
    )

    return src


def _empty_state(msg: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Preview</title>
<style>
  html,body{{margin:0;height:100%;background:#09090B;color:#A1A1AA;
    font-family:'JetBrains Mono',ui-monospace,monospace;}}
  .wrap{{height:100%;display:flex;align-items:center;justify-content:center;}}
  .card{{padding:24px 28px;border:1px solid #27272A;border-radius:6px;
    background:#121215;max-width:480px;text-align:center;font-size:13px;}}
  .blink{{display:inline-block;width:8px;height:14px;background:#FAFAFA;
    vertical-align:middle;margin-left:6px;animation:b 1s steps(2) infinite;}}
  @keyframes b{{50%{{opacity:0;}}}}
</style></head>
<body><div class="wrap"><div class="card">[ {_html.escape(msg)} ]<span class="blink"></span></div></div></body></html>
"""
