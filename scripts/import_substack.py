#!/usr/bin/env python3
"""
scripts/import_substack.py
Phase 3 Substack Newsletter Importer.
Parses an exported Substack archive (posts.csv + HTML/text files),
chunks articles, and maps excerpts to relevant policy frameworks.
Outputs: assets/newsletter_excerpts.json
"""

import os
import sys
import csv
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

def clean_html(raw_html):
    """Strips HTML tags to extract clean prose text."""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

def chunk_text(text, max_words=120):
    """Splits an article into readable paragraphs/chunks."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current_chunk = []
    current_count = 0
    
    for p in paragraphs:
        words = p.split()
        if current_count + len(words) > max_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = words
            current_count = len(words)
        else:
            current_chunk.extend(words)
            current_count += len(words)
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def process_substack_export(export_dir_or_csv, frameworks_graph_path=None):
    export_path = Path(export_dir_or_csv)
    
    # Load existing framework keywords
    framework_keywords = {}
    if frameworks_graph_path and Path(frameworks_graph_path).exists():
        with open(frameworks_graph_path, "r", encoding="utf-8") as f:
            gdata = json.load(f)
            for node in gdata.get("nodes", []):
                framework_keywords[node["id"]] = [
                    node["id"].replace("-", " ").lower(),
                    node["title"].lower()
                ]
    
    posts = []
    
    # Check if a posts.csv exists
    csv_file = export_path if export_path.suffix == ".csv" else (export_path / "posts.csv")
    if csv_file.exists():
        with open(csv_file, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = row.get("title") or row.get("post_title") or "Untitled Post"
                author = row.get("author") or "Newsletter Author"
                post_date = row.get("post_date") or row.get("created_at") or ""
                url = row.get("canonical_url") or row.get("url") or "#"
                body = row.get("body_html") or row.get("content") or ""
                
                clean_body = clean_html(body)
                chunks = chunk_text(clean_body)
                
                # Match chunks to frameworks
                matched_frameworks = set()
                for chunk in chunks:
                    chunk_lower = chunk.lower()
                    for fid, keywords in framework_keywords.items():
                        if any(k in chunk_lower for k in keywords):
                            matched_frameworks.add(fid)
                            
                posts.append({
                    "title": title,
                    "author": author,
                    "date": post_date,
                    "url": url,
                    "excerpt": chunks[0] if chunks else clean_body[:200] + "...",
                    "matched_frameworks": list(matched_frameworks)
                })
    else:
        print(f"No posts.csv found at {csv_file}. Sample placeholder generated.")
        posts = [
            {
                "title": "Pricing the Air We Breathe",
                "author": "Policy Dispatch",
                "date": "2026-03-15",
                "url": "https://substack.com",
                "excerpt": "When market externalities spill over into communal waterways and atmospheric sinks, Pigouvian carbon taxes offer a dynamic incentive structure that command regulations fail to match.",
                "matched_frameworks": ["pigouvian-tax", "coase-theorem", "tragedy-of-the-commons"]
            },
            {
                "title": "The Ostrom Alternative to the Leviathan",
                "author": "Institutional Review",
                "date": "2026-02-01",
                "url": "https://substack.com",
                "excerpt": "Instead of ceding control to centralized ministries or auctioning off shared pasturelands to corporations, community governance demonstrates that local institutional design overcomes the tragedy of the commons.",
                "matched_frameworks": ["ostrom-polycentric-governance", "tragedy-of-the-commons", "subsidiarity"]
            }
        ]
        
    out_path = ASSETS_DIR / "newsletter_excerpts.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2)
    print(f"Processed {len(posts)} newsletter articles into {out_path}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(BASE_DIR)
    graph_file = ASSETS_DIR / "graph.json"
    process_substack_export(target, graph_file)
