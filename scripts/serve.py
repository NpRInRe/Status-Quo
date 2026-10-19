#!/usr/bin/env python3
"""
scripts/serve.py
Zero-dependency static site generator and live preview server.
Renders .qmd files into _site/ directory and serves at http://localhost:8000.
Allows instant testing on any machine without needing local Quarto installed.
"""

import os
import re
import json
import shutil
import http.server
import socketserver
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SITE_DIR = BASE_DIR / "_site"
ASSETS_DIR = BASE_DIR / "assets"
SCRIPTS_DIR = BASE_DIR / "scripts"

NAVBAR_HTML = """
<header class="navbar-header" style="background: #0f172a; color: #f8fafc; padding: 0.85rem 1.5rem; position: sticky; top: 0; z-index: 100; border-bottom: 1px solid #1e293b;">
  <div style="max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between;">
    <a href="/index.html" style="color: #ffffff; font-weight: 700; font-size: 1.15rem; text-decoration: none; display: flex; align-items: center; gap: 0.5rem;">
      <span style="font-size: 1.25rem;">⚖️</span> Status Quo
    </a>
    <nav style="display: flex; gap: 1.25rem; font-size: 0.95rem; align-items: center;">
      <a href="/index.html" style="color: #cbd5e1; text-decoration: none;">Home</a>
      <a href="/graph.html" style="color: #cbd5e1; text-decoration: none; font-weight: 600;">Graph View</a>
      <a href="/law/index.html" style="color: #cbd5e1; text-decoration: none;">Law</a>
      <a href="/society/index.html" style="color: #cbd5e1; text-decoration: none;">Society</a>
      <a href="/about.html" style="color: #94a3b8; text-decoration: none;">About</a>
      <a href="https://statusquotoday.substack.com" target="_blank" rel="noopener" style="color: #38bdf8; text-decoration: none; font-weight: 600;">Substack ↗</a>
    </nav>
  </div>
</header>
"""

FOOTER_HTML = """
<footer style="margin-top: 5rem; padding: 2.5rem 1.5rem; background: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center; color: #64748b; font-size: 0.9rem;">
  <div style="max-width: 900px; margin: 0 auto;">
    <p style="margin-bottom: 0.4rem; font-weight: 700; color: #0f172a; font-size: 1rem;">Status Quo</p>
    <p style="margin-bottom: 0.75rem; color: #64748b; font-size: 0.85rem;">Society’s existing states of affairs in law, policy, politics, and culture.</p>
    <p style="margin: 0; font-size: 0.8rem; color: #94a3b8;">© Neeraj Paulose Raj • An interconnected knowledge blog</p>
  </div>
</footer>
"""

def md_to_html(md_text):
    """Converts common markdown constructs to HTML."""
    # Handle raw html blocks ```{=html} ... ```
    raw_blocks = []
    def save_raw(m):
        raw_blocks.append(m.group(1))
        return f"<!--RAW_BLOCK_{len(raw_blocks)-1}-->"
    
    text = re.sub(r"```\{=html\}\s*\n(.*?)\n```", save_raw, md_text, flags=re.DOTALL)
    
    # Standard code blocks
    code_blocks = []
    def save_code(m):
        code_blocks.append(f"<pre><code>{m.group(1)}</code></pre>")
        return f"<!--CODE_BLOCK_{len(code_blocks)-1}-->"
    text = re.sub(r"```\s*\n(.*?)\n```", save_code, text, flags=re.DOTALL)
    
    # Headers
    text = re.sub(r"^### (.*)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.*)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.*)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)
    
    # Bold and Italics
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    
    # Callout boxes / div wrappers ::: {.class} ... :::
    text = re.sub(r":::\s*\{\.([a-zA-Z0-9_\-]+)\}\s*\n", r'<div class="\1">\n', text)
    text = re.sub(r"\n:::", r"\n</div>", text)
    
    # Lists
    lines = text.split("\n")
    in_list = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("- "):
            if not in_list:
                new_lines.append("<ul>")
                in_list = True
            item_text = line.strip()[2:]
            new_lines.append(f"  <li>{item_text}</li>")
        else:
            if in_list:
                new_lines.append("</ul>")
                in_list = False
            new_lines.append(line)
    if in_list:
        new_lines.append("</ul>")
    text = "\n".join(new_lines)
    
    # Paragraphs (empty line separated)
    paras = text.split("\n\n")
    formatted_paras = []
    for p in paras:
        p_clean = p.strip()
        if not p_clean:
            continue
        if p_clean.startswith("<h") or p_clean.startswith("<div") or p_clean.startswith("</div") or p_clean.startswith("<ul") or p_clean.startswith("<!--RAW"):
            formatted_paras.append(p_clean)
        else:
            formatted_paras.append(f"<p>{p_clean}</p>")
    text = "\n\n".join(formatted_paras)
    
    # Restore raw blocks
    for idx, b in enumerate(raw_blocks):
        text = text.replace(f"<!--RAW_BLOCK_{idx}-->", b)
    for idx, b in enumerate(code_blocks):
        text = text.replace(f"<!--CODE_BLOCK_{idx}-->", b)
        
    return text

def render_page(title, body_html, root_prefix="./"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Frameworks Knowledge Graph</title>
  <link rel="stylesheet" href="{root_prefix}assets/styles.css">
  <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body style="margin: 0; background-color: #ffffff; color: #1e293b; line-height: 1.6;">
  {NAVBAR_HTML}
  <main style="max-width: 900px; margin: 2rem auto; padding: 0 1.5rem;">
    {body_html}
  </main>
  {FOOTER_HTML}
  <script src="{root_prefix}assets/frameworks-app.js"></script>
</body>
</html>"""

def build_site():
    print("Building knowledge graph...")
    import build_graph
    build_graph.main()
    
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy assets
    shutil.copytree(ASSETS_DIR, SITE_DIR / "assets", dirs_exist_ok=True)
    
    # Process all .qmd files
    for qmd in BASE_DIR.rglob("*.qmd"):
        if ".quarto" in str(qmd) or "_site" in str(qmd):
            continue
        rel_qmd = qmd.relative_to(BASE_DIR)
        target_html = SITE_DIR / rel_qmd.with_suffix(".html")
        target_html.parent.mkdir(parents=True, exist_ok=True)
        
        content = qmd.read_text(encoding="utf-8")
        
        # Frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        title = qmd.stem.replace("-", " ").title()
        subtitle = ""
        body = content
        
        if fm_match:
            fm_text, body = fm_match.group(1), fm_match.group(2)
            for line in fm_text.splitlines():
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"\'')
                elif line.startswith("subtitle:"):
                    subtitle = line.split(":", 1)[1].strip().strip('"\'')
                    
        # Check listing directive on category index
        if "listing:" in content and qmd.name == "index.qmd" and qmd.parent != BASE_DIR:
            cat_name = qmd.parent.name
            body += f"\n\n<!-- AUTOGENERATED_LISTING -->\n"
            # Read graph.json for items in this category
            graph_json_path = ASSETS_DIR / "graph.json"
            if graph_json_path.exists():
                gdata = json.loads(graph_json_path.read_text(encoding="utf-8"))
                cat_items = [n for n in gdata["nodes"] if n["category"].lower() == cat_name.lower() or cat_name.lower() in [c.lower() for c in n.get("categories", [])]]
                body += '<div class="start-here-grid" style="margin-top: 1.5rem;">\n'
                for item in cat_items:
                    body += f"""
<a href="{item['url']}" class="framework-card">
  <span class="card-category-badge badge-{cat_name.lower()}">{item['category']}</span>
  <h3 class="card-title">{item['title']}</h3>
  <p class="card-summary">{item['summary']}</p>
</a>
"""
                body += '</div>\n'
                
        body_html = md_to_html(body)
        
        # Calculate root prefix
        depth = len(rel_qmd.parts) - 1
        root_prefix = "../" * depth if depth > 0 else "./"
        
        header_html = f'<div style="margin-bottom: 2rem;"><h1 style="font-size: 2.25rem; font-weight: 800; margin-bottom: 0.5rem; color: #0f172a;">{title}</h1>'
        if subtitle:
            header_html += f'<p style="font-size: 1.1rem; color: #64748b; margin: 0;">{subtitle}</p>'
        header_html += '</div>'
        
        full_content = header_html + body_html
        html_out = render_page(title, full_content, root_prefix=root_prefix)
        target_html.write_text(html_out, encoding="utf-8")
        
    print(f"Site built successfully into {SITE_DIR}")

def serve():
    build_site()
    port = 8000
    os.chdir(str(SITE_DIR))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"\n=======================================================")
        print(f" Live Preview Server Running at http://localhost:{port}")
        print(f" Press Ctrl+C to stop.")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    serve()
